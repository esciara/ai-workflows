"""Workflow A, read side (steps 2-4 and 7): PR context for the agents, CI gate, risk tier, verdict rubric.

Runs in the `context` job with a read-only token. PR text and code are untrusted: they go into the agent's context file
between tags, never onto a command line. Agents get the code inline and no file tools (ADR-0034).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from aiwf import config

GhRunner = Callable[[list[str]], str]
CI_BUDGET = 20 * 60  # seconds; then the verdict is human-review (ADR-0034); a config key comes with WP12 budgets
CI_POLL = 20
CI_GRACE = 90  # with no check run at all, wait this long for CI to register before calling it "none"
LOCKFILES = {"package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "bun.lock", "poetry.lock",
             "uv.lock", "pdm.lock", "Pipfile.lock", "Cargo.lock", "Gemfile.lock", "composer.lock", "go.sum", "Podfile.lock",
             "packages.lock.json", "gradle.lockfile", "mix.lock", "pubspec.lock", "flake.lock"}
GENERATED_RE = re.compile(r"(\.min\.(js|css)|\.map|_pb2(_grpc)?\.pyi?|\.pb\.go|\.generated\.\w+)$")
MAX_GENERATED = 20  # names kept in the facts and shown in the summary
CONTEXT_CAP = 120_000  # characters of diff + files + callers handed to an agent
GREEN = {"success", "neutral", "skipped"}
PASSES = ("correctness", "security", "maintainability", "tests")  # step 5; must match the matrix in review.yml
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
MAX_COMMENTABLE = 300  # files whose diff lines are passed on for inline comments; the others get general comments only
DEF_RE = re.compile(r"\b(?:def|function|func|fn|class)\s+([A-Za-z_][A-Za-z0-9_]{2,})")
# Tags that frame the agents' context (here and in review.yml's verifier prompt). Untrusted text that opens or closes
# one of them could end `<diff>` early and forge e.g. `<previous_findings>` (checkpoint item 6).
CONTEXT_TAGS = ("pr_description", "linked_issues", "diff", "touched_files", "callers", "file", "candidates",
                "previous_findings")
TAG_RE = re.compile(r"<(\s*/?\s*(?:" + "|".join(CONTEXT_TAGS) + r")\b)", re.IGNORECASE)
# A check run is ours when GitHub Actions ran it in a workflow run that calls one of our reusable workflows (the run's
# `referenced_workflows`): earlier runs of ours on the same head (an `ai: error` run, a `/review` re-run, this repo's
# `verdict` job) are not the repo's CI, so they never make it red (checkpoint item 2). Known by the run, never by the
# check's name: a repo's own `release / publish` stays CI. Reading runs needs `actions: read` on the `context` job.
OWN_WORKFLOWS_PREFIX = "esciara/ai-workflows/.github/workflows/"
RUN_URL_RE = re.compile(r"/actions/runs/(\d+)(?:/|\Z)")
# `linked_issue: issue-or-plan-ref` (ADR-0053): a WP id or a plan reference in the PR text counts as a linked issue.
PLAN_REF_RE = re.compile(r"\bWP\d+[a-z]?\b|docs/plan\.md")
WP_BRANCH_RE = re.compile(r"wp\d+[a-z]?-", re.IGNORECASE)  # CLAUDE.md: branch `wp<N>-<slug>`
RUN_ID_RE = re.compile(r"/actions/runs/\d+|\brun[ _-]?ids?\b\W{0,12}\d{6,}", re.IGNORECASE)  # e2e evidence, not verified


def glob_re(pattern: str) -> re.Pattern[str]:
    """`**` spans directories, `*` and `?` stay within one path segment."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def risk_tier(paths: list[str], risk_paths: dict[str, list[str]]) -> str:
    for tier in ("high", "medium"):
        pats = [glob_re(p) for p in risk_paths.get(tier, [])]
        if any(p.match(path) for p in pats for path in paths):
            return tier
    return "low"


def run_id_of(check_run: dict[str, Any]) -> str | None:
    """The workflow run id of a GitHub Actions check run, else None (another app's check is never ours)."""
    if (check_run.get("app") or {}).get("slug") != "github-actions":
        return None
    for url in (check_run.get("details_url") or "", check_run.get("html_url") or ""):
        if m := RUN_URL_RE.search(url):
            return m.group(1)
    return None


def calls_our_workflows(run: dict[str, Any]) -> bool:
    return any((w.get("path") or "").startswith(OWN_WORKFLOWS_PREFIX) for w in run.get("referenced_workflows") or [])


def own_runs(gh: GhRunner, repo: str, check_runs: list[dict[str, Any]], known: dict[str, bool]) -> set[str]:
    """Ids of the workflow runs behind `check_runs` that call our reusable workflows. `known` caches answers across
    polls. A run that cannot be read is not cached and counts as not ours: its failed checks stay red CI (fail safe)."""
    for rid in {i for r in check_runs if (i := run_id_of(r))} - set(known):
        try:
            known[rid] = calls_our_workflows(json.loads(gh(["api", f"repos/{repo}/actions/runs/{rid}"])))
        except (RuntimeError, ValueError) as e:
            print(f"::warning::cannot read workflow run {rid} ({type(e).__name__}); its checks count as CI")
    return {rid for rid, ours in known.items() if ours}


def ci_state(check_runs: list[dict[str, Any]], own_run_id: str, required: list[str] | None,
             own: set[str] = frozenset()) -> str:
    """`pending`, `green`, `red` or `none` for the head SHA's check runs, ours excluded (ADR-0007, ADR-0034): this run's
    and those of the workflow runs in `own` (runs that call our reusable workflows, from `own_runs`)."""
    skip = set(own) | {own_run_id}
    runs = [r for r in check_runs if run_id_of(r) not in skip]
    if required:
        runs = [r for r in runs if r["name"] in required]
        if {r["name"] for r in runs} != set(required):
            return "pending"
    if not runs:
        return "none"
    if any(r["status"] != "completed" for r in runs):
        return "pending"
    return "green" if all(r["conclusion"] in GREEN for r in runs) else "red"


def wait_ci(gh: GhRunner, repo: str, sha: str, own_run_id: str, required: list[str] | None,
            budget: float = CI_BUDGET, poll: float = CI_POLL, sleep: Callable[[float], None] = time.sleep) -> str:
    """Final CI state, or `timeout` when checks are still running after `budget` seconds."""
    waited, known = 0.0, {}
    while True:
        pages = json.loads(gh(["api", "--paginate", "--slurp", f"repos/{repo}/commits/{sha}/check-runs?per_page=100"]))
        checks = [r for page in pages for r in page["check_runs"]]
        state = ci_state(checks, own_run_id, required, own_runs(gh, repo, checks, known))
        if state in ("green", "red") or (state == "none" and waited >= CI_GRACE):
            return state
        if waited >= budget:
            return "timeout"
        sleep(poll)
        waited += poll


def verdict(findings: list[dict[str, Any]], facts: dict[str, Any]) -> tuple[str, list[str]]:
    """The spec's rubric, first matching row wins; returns (label, reasons)."""
    blocking = sum(f["severity"] == "blocking" for f in findings)
    if blocking or facts["ci"] == "red":
        return "ai-review: changes-requested", [r for r in (
            f"{blocking} blocking finding(s)" if blocking else "", "a CI check is red" if facts["ci"] == "red" else "") if r]
    reasons = [r for r in (
        "risk tier high" if facts["tier"] == "high" else "",
        "no linked issue" if not facts["linked_issues"] and not facts.get("plan_ref") else "",
        "WP PR without e2e run IDs in its description" if facts.get("wp_no_run_ids") else "",
        f"{facts['changed_lines']} changed lines (> {facts['human_review_lines']})"
        if facts["changed_lines"] > facts["human_review_lines"] else "",
        f"CI still running after {CI_BUDGET // 60} min" if facts["ci"] == "timeout" else "",
        f"context cut (cap of {CONTEXT_CAP} characters, or a file of 200 KB or more left out): the review saw part of the change" if facts["truncated"] else "",
    ) if r]
    if reasons:
        return "ai-review: human-review", reasons
    return "ai-review: merge", ["no blocking findings, CI green, tier " + facts["tier"]]


def commentable(diff: str) -> dict[str, list[list[int]]]:
    """path -> [first, last] head-side line ranges of each hunk: the lines GitHub accepts inline comments on."""
    out: dict[str, list[list[int]]] = {}
    path = None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            path = None
        elif line.startswith("+++ "):
            target = line[4:]
            path = target[2:] if target.startswith("b/") and "\t" not in target else None  # /dev/null or quoted: skip
        elif path and (m := HUNK_RE.match(line)):
            start, count = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            if count:
                out.setdefault(path, []).append([start, start + count - 1])
    return dict(list(out.items())[:MAX_COMMENTABLE])


def changed_names(diff: str) -> list[str]:
    """Function and class names defined on changed lines or in hunk headers of `diff`."""
    names: list[str] = []
    for line in diff.splitlines():
        if line.startswith(("+++", "---")) or not line.startswith(("+", "-", "@@")):
            continue
        names += [n for n in DEF_RE.findall(line) if n not in names]
    return names[:20]


def callers(names: list[str], workdir: Path, limit: int = 15) -> str:
    out = []
    for name in names:
        proc = subprocess.run(["git", "grep", "-n", "-w", "-I", "-e", name], cwd=workdir, capture_output=True, text=True)
        hits = [h for h in proc.stdout.splitlines() if not DEF_RE.search(h.split(":", 2)[-1])][:limit]
        if hits:
            out.append(f"### {name}\n" + "\n".join(hits))
    return "\n\n".join(out)


def is_generated(path: str) -> bool:
    """Lockfiles and generated files: nobody reviews them by hand, so they are not sent to the model nor counted as
    human-review lines (spec: "Not reviewed: generated files, lockfiles")."""
    return path.rsplit("/", 1)[-1] in LOCKFILES or bool(GENERATED_RE.search(path))


def without_generated(diff: str) -> str:
    """`diff` (git format) minus the file sections of lockfiles and generated files."""
    sections = re.split(r"(?m)^(?=diff --git )", diff)
    keep = []
    for sec in sections:
        m = re.match(r"diff --git a/(.*?) b/(.*)", sec)
        if m and is_generated(m.group(1)) and is_generated(m.group(2)):
            continue
        keep.append(sec)
    return "".join(keep)


def fence(text: str) -> str:
    """Untrusted text with every opening or closing context tag defused (`<diff>` -> `&lt;diff>`), so it cannot close
    or fake the tags that frame it. Same escape as triage.neutral (ADR-0018), but only before our tag names: the
    agents quote code from the context in suggested fixes, so the rest of it must stay as written."""
    return TAG_RE.sub(r"&lt;\1", text)


def capped(parts: list[tuple[str, str]], cap: int = CONTEXT_CAP) -> tuple[str, bool]:
    """(tagged context, whether any part was cut at the cap)."""
    out, left, truncated = [], cap, False
    for tag, text in parts:
        if len(text) > left:
            text, truncated = text[: max(left, 0)] + f"\n[... truncated: context cap of {cap} characters reached]", True
        left -= len(text)
        out.append(f"<{tag}>\n{text}\n</{tag}>")  # text is fenced or built from fenced parts by the caller
    return "\n\n".join(out), truncated


def gather(gh: GhRunner, repo: str, number: int, sha: str, workdir: Path, cfg: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """(agent context text, facts) for PR `number` at head `sha`; `workdir` is a checkout of that head."""
    pr = json.loads(gh(["api", f"repos/{repo}/pulls/{number}"]))
    files = json.loads(gh(["api", "--paginate", "--slurp", f"repos/{repo}/pulls/{number}/files?per_page=100"]))
    files = [f for page in files for f in page]
    paths = sorted({f["filename"] for f in files} | {f["previous_filename"] for f in files if f.get("previous_filename")})
    diff = gh(["api", f"repos/{repo}/pulls/{number}", "-H", "Accept: application/vnd.github.diff"])
    skipped = [f for f in files if is_generated(f["filename"]) and (not f.get("previous_filename") or is_generated(f["previous_filename"]))]
    diff = without_generated(diff)
    files = [f for f in files if f not in skipped]
    owner, name = repo.split("/")
    q = ("query($o:String!,$n:String!,$p:Int!){repository(owner:$o,name:$n){pullRequest(number:$p){"
         "closingIssuesReferences(first:5){nodes{number title body}}}}}")
    gql = json.loads(gh(["api", "graphql", "-f", f"query={q}", "-f", f"o={owner}", "-f", f"n={name}", "-F", f"p={number}"]))
    issues = gql["data"]["repository"]["pullRequest"]["closingIssuesReferences"]["nodes"]
    touched, too_big = [], False
    for f in files:
        p = workdir / f["filename"]
        if f["status"] != "removed" and p.is_file() and p.stat().st_size >= 200_000:
            too_big = True  # left out of touched_files: counts as truncated, like the context cap
        elif f["status"] != "removed" and p.is_file():
            path = fence(f["filename"]).replace('"', "&quot;")
            touched.append(f'<file path="{path}">\n{fence(p.read_text(errors="replace"))}\n</file>')
    pr_text = fence(f"Title: {pr['title']}\n\n{pr.get('body') or ''}")
    issue_text = fence("\n\n".join(f"Issue #{i['number']}: {i['title']}\n\n{i.get('body') or ''}" for i in issues)) or "(none)"
    context, truncated = capped([("pr_description", pr_text), ("linked_issues", issue_text), ("diff", fence(diff)),
                                 ("touched_files", "\n".join(touched)),
                                 ("callers", fence(callers(changed_names(diff), workdir)))])
    plan_mode = cfg.get("linked_issue", "issue") == "issue-or-plan-ref"
    branch = (pr.get("head") or {}).get("ref") or ""
    facts = {
        "sha": sha,
        "tier": risk_tier(paths, cfg["risk_paths"]),
        "high_paths": [p for p in paths if risk_tier([p], cfg["risk_paths"]) == "high"][:MAX_COMMENTABLE],  # inline even for nits (WP3)
        "commentable": commentable(diff),
        "changed_lines": pr["additions"] + pr["deletions"] - sum(f.get("additions", 0) + f.get("deletions", 0) for f in skipped),
        "generated": sorted(f["filename"] for f in skipped)[:MAX_GENERATED],  # skipped: lockfiles and generated files
        "human_review_lines": cfg["limits"]["human_review_lines"],
        "linked_issues": [i["number"] for i in issues],
        "plan_ref": plan_mode and bool(PLAN_REF_RE.search(f"{pr['title']}\n{pr.get('body') or ''}")),
        "wp_no_run_ids": plan_mode and bool(WP_BRANCH_RE.match(branch)) and not RUN_ID_RE.search(pr.get("body") or ""),
        "truncated": truncated or too_big,  # the agents saw part of the context only: they lack context to judge (spec)
    }
    return context, facts


def candidates(passes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The passes' findings as one list for the verifier, each with id `<pass>-<n>` (n from 1, in the pass's order).

    review.yml builds the same ids with jq for the verifier's prompt; the publisher rebuilds them here to join the
    verifier's decisions back to the findings, so the verifier can only judge findings, never add one."""
    return [{**f, "id": f"{name}-{i}", "pass": name}
            for name in PASSES for i, f in enumerate(passes.get(name, {}).get("findings", []), 1)]


def cmd_review_context(args: argparse.Namespace) -> int:
    from aiwf.publish_review import find_summary  # write side owns the comment format; this only reads it

    cfg = json.loads(os.environ["AIWF_CONFIG"])
    context, facts = gather(config.run_gh, args.repo, args.pr, args.sha, Path(args.workdir), cfg)
    _, prev = find_summary(config.run_gh, args.repo, args.pr)
    facts["ci"] = wait_ci(config.run_gh, args.repo, args.sha, os.environ.get("GITHUB_RUN_ID", ""), cfg.get("required_checks"))
    Path(args.out).write_text(context, encoding="utf-8")
    # Step 9: the last run's open findings, for the verifier to mark resolved or still open.
    # `<` as \u003c: same JSON, but agent-written titles cannot close `<previous_findings>` in the verifier's prompt.
    previous = json.dumps(prev["open"] if prev else [], indent=1).replace("<", "\\u003c")
    Path(args.previous).write_text(previous, encoding="utf-8")
    print(f"context: {len(context)} chars; facts: {json.dumps(facts)}")
    if os.environ.get("GITHUB_OUTPUT"):
        from aiwf.cli import write_outputs
        write_outputs(os.environ["GITHUB_OUTPUT"], {"facts": json.dumps(facts, separators=(",", ":"))})
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("review-context", help="Workflow A: gather PR context, wait for CI, risk tier (env AIWF_CONFIG)")
    p.add_argument("--repo", required=True)
    p.add_argument("--pr", required=True, type=int)
    p.add_argument("--sha", required=True)
    p.add_argument("--workdir", required=True, help="checkout of the PR head (read as text, never executed)")
    p.add_argument("--out", required=True, help="file for the agents' context")
    p.add_argument("--previous", required=True, help="file for the last run's open findings (JSON list)")
    p.set_defaults(func=cmd_review_context)
