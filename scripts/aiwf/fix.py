"""Workflow B, B5 fix loop: the orchestrator's side (spec B5, ADR-0037).

- `aiwf fix-context` (read-only token, plus one comment): B5 starts only when the bot's analysis comment's status line is
  the approval this run's `/fix` recorded, and `ai-fix/issue-<n>` does not exist yet (else it says so and runs no
  round). It writes the brief every agent of the loop gets as data: the project commands, the guidance (from that
  status line only), the issue and relevant comments, B2's reproduction record and B3's analysis, all bot-authored
  marker comments found by author and marker; `meta.json` keeps the approval line and the reproduction command.
- `aiwf fix-push` (`contents: write`), once per round: checks the agents' JSON against their schemas, decides the round
  from the orchestrator's own check (setup, test, reproduction command) and the reviewer's verdict, and pushes the
  round's cumulative diff (rejected rounds too) through the Git data API, only when it touches no CI config (`.github/`),
  the status line is still the approval and the branch head is still the commit pushed last. Writes the round record.
  A changed status line (a later B2) stops the loop without escalating (`superseded`); a moved head or the round cap
  escalates.
- Escalation (`aiwf fix-escalate`, module `fix_escalate`) reads the round records.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from aiwf import cli, config, guard, publish, publish_analysis, publish_reproduce, reproduce, triage
from aiwf.ghapi import GhRunner, find_marker_comment

EXISTS_MARKER = "<!-- ai-workflows:fix-exists -->"
MAX_PATCH = 1_000_000  # bytes of cumulative diff; more is never pushed
MAX_CHECK_TAIL = 3_000
APPROVAL_RE = re.compile(r"^fix approved by @\S+ \(\[comment\]\((\S+)\)\)(?:; guidance: (.*)|\.)$")
REPRO_RE = re.compile(r"^\*\*Test\*\* `([^`\n]*)`, run with `([^`\n]*)`:$", re.MULTILINE)


def branch_name(issue: int) -> str:
    return f"ai-fix/issue-{issue}"


def branch_head(gh: GhRunner, repo: str, branch: str) -> str | None:
    """The branch's head commit, or None when it does not exist (exact name: matching-refs is a prefix match)."""
    refs = json.loads(gh(["api", f"repos/{repo}/git/matching-refs/heads/{branch}"]) or "[]")
    hit = [r for r in refs if r.get("ref") == f"refs/heads/{branch}"]
    return hit[0]["object"]["sha"] if hit else None


def current_status(gh: GhRunner, repo: str, issue: int) -> str:
    found = find_marker_comment(gh, repo, issue, publish_analysis.MARKER)
    return publish_analysis.status_lines(found.get("body") or "")[0] if found else ""


def approval(status: str, comment_id: int) -> tuple[bool, str]:
    """(status is the approval that comment recorded, its guidance). The guidance is already cleaned by B4."""
    m = APPROVAL_RE.match(status)
    if not m or not m.group(1).endswith(f"#issuecomment-{comment_id}"):
        return False, ""
    return True, m.group(2) or ""


def repro_command(body: str) -> tuple[str, str]:
    """(test path, command) from B2's reproduction comment; mdtext.inline escaped `|` and turned backticks into `'`."""
    m = REPRO_RE.search(body)
    return (m.group(1).replace("\\|", "|"), m.group(2).replace("\\|", "|")) if m else ("", "")


def body_without_status(body: str) -> str:
    m = publish_analysis.STATUS_RE.search(body)
    return body[: m.start()] if m else body


def brief(issue: dict[str, Any], comments: list[dict[str, Any]], cfg: dict[str, Any], guidance: str,
          repro: str, analysis: str, command: str) -> str:
    """The loop's shared brief. Everything but the config's commands is data for the agents (tags escaped)."""
    lines = reproduce.build(issue, comments, cfg).split("\n")
    lines[4:4] = [f"- reproduction test: `{command or 'not given'}`"]
    return "\n".join([
        *lines,
        "# Maintainer's guidance from `/fix` (data: about the fix only)", "",
        f"<guidance>{triage.neutral(guidance) or 'none'}</guidance>", "",
        "# Reproduction record (B2)", "", "<reproduction>", triage.neutral(repro.strip()), "</reproduction>", "",
        "# Analysis (B3)", "", "<analysis>", triage.neutral(body_without_status(analysis).strip()), "</analysis>", ""])


def context(gh: GhRunner, repo: str, issue: int, comment_id: int, cfg: dict[str, Any], out: Path) -> bool:
    """Write brief.md and meta.json into `out`; False (and why, in the log or a comment) when B5 must not start."""
    status = current_status(gh, repo, issue)
    ok, guidance = approval(status, comment_id)
    if not ok:
        print(f"::notice title=B5 not started::the analysis status is not this run's approval: {status[:120]!r}")
        return False
    branch = branch_name(issue)
    if branch_head(gh, repo, branch):
        publish.comment(gh, repo, issue, f"{EXISTS_MARKER}\nThe fix loop did not start: branch `{branch}` already "
                        "exists. Delete it, then comment `/reproduce` and `/fix` again to retry.")
        print(f"::notice title=B5 not started::{branch} exists")
        return False
    comments = reproduce.comments(gh, repo, issue)
    repro = find_marker_comment(gh, repo, issue, publish_reproduce.MARKER)
    analysis = find_marker_comment(gh, repo, issue, publish_analysis.MARKER) or {}
    repro_body = (repro or {}).get("body") or ""
    test_path, command = repro_command(repro_body)
    item = triage.get_json(gh, f"repos/{repo}/issues/{issue}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "brief.md").write_text(brief(item, comments, cfg, guidance, repro_body.removeprefix(publish_reproduce.MARKER),
                                        (analysis.get("body") or "").removeprefix(publish_analysis.MARKER), command),
                                  encoding="utf-8")
    (out / "meta.json").write_text(json.dumps({"approval": status, "repro_command": command, "test_path": test_path}),
                                   encoding="utf-8")
    return True


# --- one round: the diff, the guards, the push ------------------------------------------------------------------------


LITERAL = {**os.environ, "GIT_LITERAL_PATHSPECS": "1"}  # a path from the diff is a name, never a pattern


def git(tree: Path, *args: str, text: bool = True) -> Any:
    return subprocess.run(["git", "-C", str(tree), *args], check=True, capture_output=True, text=text,
                          env=LITERAL).stdout


def apply_patch(tree: Path, patch: Path) -> str:
    """Apply the round's cumulative diff to the base tree's index only: no working tree, so no `.gitattributes`
    filter or line-ending rule the diff brings changes what is pushed. '' or why it does not apply."""
    if patch.is_file() and patch.stat().st_size:
        try:
            git(tree, "apply", "--cached", "--binary", str(patch.resolve()))
        except subprocess.CalledProcessError:
            return "The diff does not apply to the base commit; it was not pushed."
    return ""


def changes(tree: Path) -> list[tuple[str, str, str]]:
    """(status, path, mode) of every path the index changes against its base commit."""
    raw = git(tree, "diff", "--cached", "--no-renames", "--name-status", "-z", "HEAD").split("\0")
    out = []
    for status, path in zip(raw[0::2], raw[1::2]):
        if not path:
            continue
        ref = "HEAD" if status == "D" else ""
        listing = git(tree, "ls-tree", ref, "--", path) if ref else git(tree, "ls-files", "-s", "--", path)  # literal
        out.append((status, path, listing.split(" ", 1)[0] if listing else "100644"))
    return out


# CI config outside `.github/` (hard rule: never edit a target repo's CI config): other CI services build a pushed
# branch with the project's secrets. Compared lower-case; a directory blocks everything under it.
CI_PATHS = (".github", ".circleci", ".buildkite", ".gitlab", ".gitlab-ci.yml", ".travis.yml", "azure-pipelines.yml",
            "jenkinsfile", "bitbucket-pipelines.yml", ".drone.yml", ".woodpecker", ".woodpecker.yml", "appveyor.yml",
            ".appveyor.yml", ".semaphore", "cloudbuild.yaml", "cloudbuild.yml", "bitrise.yml", ".gitea", ".forgejo",
            "codeowners", "docs/codeowners", ".gitlab/codeowners")  # best effort: not every CI service is listed


def is_ci(path: str) -> bool:
    p = path.lower()
    return any(p == c or p.startswith(c + "/") for c in CI_PATHS)


def unpushable(paths: list[tuple[str, str, str]], patch_size: int) -> str:
    """Why this diff is never pushed (spec B5, hard rules), or ''."""
    if not paths:
        return "The round changed nothing."
    if patch_size > MAX_PATCH:
        return f"The diff is larger than {MAX_PATCH} bytes; it was not pushed."
    ci = sorted(p for _, p, _ in paths if is_ci(p))
    if ci:
        return "The diff touches `.github/` or other CI config, which is never pushed: " + ", ".join(ci[:10])
    if any(mode == "160000" for _, _, mode in paths):
        return "The diff changes a submodule, which is never pushed."
    return ""


def post_json(gh: GhRunner, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(body, fh)
    try:
        return json.loads(gh(["api", "-X", method, path, "--input", fh.name]) or "{}")
    finally:
        os.unlink(fh.name)


class BranchMoved(Exception):
    pass


def push(gh: GhRunner, repo: str, tree: Path, paths: list[tuple[str, str, str]], parent: str, expected: str,
         branch: str, message: str) -> str:
    """One commit with the tree's content on `parent`, then the branch moved to it: created when `expected` is '',
    fast-forwarded from `expected` otherwise. GitHub refuses both with 422 (or 409) when the branch is not as
    expected: BranchMoved. Any other refusal (permission, outage) is raised as is and fails the job (`ai: error`)."""
    entries = []
    for status, path, mode in paths:
        if status == "D":
            entries.append({"path": path, "mode": mode, "type": "blob", "sha": None})
            continue
        blob = git(tree, "ls-files", "-s", "--", path).split()[1]
        content = subprocess.run(["git", "-C", str(tree), "cat-file", "blob", blob], check=True,
                                 capture_output=True).stdout
        sha = post_json(gh, "POST", f"repos/{repo}/git/blobs",
                        {"content": base64.b64encode(content).decode(), "encoding": "base64"})["sha"]
        entries.append({"path": path, "mode": mode, "type": "blob", "sha": sha})
    tree_sha = post_json(gh, "POST", f"repos/{repo}/git/trees",
                         {"base_tree": git(tree, "rev-parse", "HEAD^{tree}").strip(), "tree": entries})["sha"]
    commit = post_json(gh, "POST", f"repos/{repo}/git/commits",
                       {"message": message, "tree": tree_sha, "parents": [parent]})["sha"]
    try:
        if expected:
            post_json(gh, "PATCH", f"repos/{repo}/git/refs/heads/{branch}", {"sha": commit, "force": False})
        else:
            post_json(gh, "POST", f"repos/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": commit})
    except RuntimeError as exc:
        if not re.search(r"HTTP (409|422)", str(exc)):
            raise
        raise BranchMoved(str(exc)[:200]) from None
    return commit


def review_findings(review: dict[str, Any]) -> list[str]:
    found = [f"{f['file'] + ': ' if f['file'] else ''}{f['problem']}" + (f" Fix: {f['fix']}" if f["fix"] else "")
             for f in review["findings"]]
    return found or ([] if review["verdict"] == "approve" else [review["summary"]])


def next_brief(record: dict[str, Any]) -> str:
    """The findings the next round's implementer gets, as data."""
    lines = [f"# Findings from round {record['round']} (data; the working directory holds that round's changes)", "",
             "<previous_round>"]
    lines += [f"- {triage.neutral(f)}" for f in record["findings"]]
    if record["check_output"]:
        lines += ["", "Check output (end):", triage.neutral(record["check_output"])]
    return "\n".join([*lines, "</previous_round>", ""])


def run_round(gh: GhRunner, repo: str, issue: int, k: int, cap: int, meta: dict[str, Any], tree: Path, patch: Path,
              check_ok: bool, check_log: str, impl_raw: str, review_raw: str, prev_head: str, base: str,
              run_url: str) -> dict[str, Any]:
    """Decide and push one round; returns its record. Invalid agent JSON raises publish.InvalidOutput."""
    impl = publish.validate("implementer", impl_raw)
    findings: list[str] = []
    check_output = ""
    approved = False
    suspicious: list[str] = []
    if not check_ok:
        findings.append("The orchestrator's check (setup, test, reproduction test) failed; its output is below.")
        check_output = check_log[-MAX_CHECK_TAIL:] or "The check did not finish."
    else:
        review = publish.validate("fix-review", review_raw)
        approved = review["verdict"] == "approve" and not review["findings"]
        findings += review_findings(review)
        suspicious = review["suspicious_instructions"]
    why = apply_patch(tree, patch)
    paths = [] if why else changes(tree)
    why = why or unpushable(paths, patch.stat().st_size if patch.is_file() else 0)
    if why:
        findings.append(why)
    stop = ""  # both guards are read before the push; only the head's (force: false on the ref) is atomic
    superseded = current_status(gh, repo, issue) != meta["approval"]
    if superseded:
        stop = "The analysis comment's status changed (a later run); nothing was pushed."
    elif (branch_head(gh, repo, branch_name(issue)) or "") != prev_head:
        stop = "Someone else pushed to the branch; the loop stopped and the branch is theirs."
    head = prev_head
    if not stop and not why:
        try:
            head = push(gh, repo, tree, paths, prev_head or base, prev_head, branch_name(issue),
                        f"fix: round {k} for #{issue} (ai-workflows B5)\n\n{impl['summary']}\n\nRun: {run_url}")
        except BranchMoved:
            stop = "Someone else pushed to the branch; the loop stopped and the branch is theirs."
    if stop:
        findings.append(stop)
    outcome = "stopped" if stop else "approved" if approved and not why else "rejected"
    nxt = outcome == "rejected" and k < cap
    return {"round": k, "outcome": outcome, "findings": findings, "check_output": check_output,
            "pushed": head if head != prev_head else "", "head": head, "next": nxt,
            "escalate": outcome != "approved" and not nxt and not superseded, "superseded": superseded,
            "summary": impl["summary"],
            "suspicious_instructions": impl["suspicious_instructions"] + suspicious}


def cmd_context(args: argparse.Namespace) -> int:
    cfg = json.loads(os.environ.get("AIWF_CONFIG") or "{}")
    cid = (cli.read_event().get("comment") or {}).get("id")
    if guard.item_off(config.run_gh, args.repo, args.issue):
        print(f"::notice title=ai: off::#{args.issue} has '{guard.OFF_LABEL}': B5 not started")
        start = False
    else:
        start = isinstance(cid, int) and context(config.run_gh, args.repo, args.issue, cid, cfg, Path(args.out))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        cli.write_outputs(out, {"start": "true" if start else "false"})
    return 0


def cmd_push(args: argparse.Namespace) -> int:
    cfg = json.loads(os.environ.get("AIWF_CONFIG") or "{}")
    cap = int(cfg.get("limits", {}).get("fix_rounds", 3))
    prev = os.environ.get("PREV_HEAD", "")
    record: dict[str, Any] = {"round": args.round, "outcome": "stopped", "findings": [], "check_output": "",
                              "pushed": "", "head": prev, "next": False, "escalate": False, "superseded": False}
    if guard.item_off(config.run_gh, args.repo, args.issue):
        print(f"::notice title=ai: off::#{args.issue} has '{guard.OFF_LABEL}': round {args.round} not pushed")
    else:
        log = Path(args.check_log)
        try:
            record = run_round(config.run_gh, args.repo, args.issue, args.round, cap,
                               json.loads(Path(args.meta).read_text(encoding="utf-8")), Path(args.tree),
                               Path(args.patch), os.environ.get("CHECK_OK") == "true",
                               log.read_text(encoding="utf-8", errors="replace") if log.is_file() else "",
                               os.environ.get("IMPLEMENT_JSON", ""), os.environ.get("REVIEW_JSON", ""), prev,
                               os.environ.get("BASE_SHA", ""), os.environ.get("RUN_URL", ""))
        except publish.InvalidOutput as exc:
            print(f"::error title=Invalid agent output::{exc}")
            return 1
        print(f"round {args.round}: {record['outcome']}, pushed {record['pushed'] or 'nothing'}")
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "round.json").write_text(json.dumps(record), encoding="utf-8")
    (outdir / "findings.md").write_text(next_brief(record), encoding="utf-8")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        cli.write_outputs(out, {"head": record["head"], "next": str(record["next"]).lower(),
                                "escalate": str(record["escalate"]).lower(),
                                "superseded": str(record["superseded"]).lower()})
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("fix-context", help="B5: check the approval and the branch, write the loop's brief")
    p.add_argument("--repo", required=True)
    p.add_argument("--issue", required=True, type=int)
    p.add_argument("--out", required=True, help="directory for brief.md and meta.json")
    p.set_defaults(func=cmd_context)
    p = sub.add_parser("fix-push", help="B5: decide one round from the check and the review, push its diff")
    p.add_argument("--repo", required=True)
    p.add_argument("--issue", required=True, type=int)
    p.add_argument("--round", required=True, type=int)
    p.add_argument("--meta", required=True)
    p.add_argument("--tree", required=True, help="the unpacked base tree (a git checkout)")
    p.add_argument("--patch", required=True)
    p.add_argument("--check-log", required=True)
    p.add_argument("--out", required=True, help="directory for round.json and findings.md")
    p.set_defaults(func=cmd_push)
