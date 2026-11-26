"""Workflow B, B3 and B4: the analysis comment, and the maintainer's `/fix` or `/no-fix` (spec B3, B4).

- B3 publish (kind `analyst`): one comment found by its marker, updated in place; the risk tier comes from the files to
  change with A's path rules, and file links are built here, at the analysed commit, only for a path in the list of
  tree files that passed the path check (`analyse.safe_file`) and a whole-number line. Label `triage: awaiting-maintainer`.
- B4 (`aiwf decide`): only while the issue has `triage: awaiting-maintainer`, read live (`/no-fix` also while the status is a
  `/fix` approval: it stops a running B5); removes it first, then sets the
  comment's status line to who decided, a link to their comment and the command's text (cleaned, one line, capped).
  `/no-fix` also labels `fix: declined`. A recorded `/fix` starts B5 (job output `fix=true`), which reads the guidance
  only from this status line.
- A later B2 that does not reproduce marks the comment superseded (`supersede`). Each new status keeps an earlier
  decision under it as "Previously:"; B5 reads only the `**Status:**` line.

Agent and command text is untrusted: it goes through `publish.clean` (no mentions, HTML, markers, links or images).
"""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from aiwf import cli, config, guard, notify, publish
from aiwf.ghapi import GhRunner, find_marker_comment, remove_label
from aiwf.mdtext import inline, run_link
from aiwf.review import risk_tier

MARKER = "<!-- ai-workflows:analysis -->"
AWAITING = "triage: awaiting-maintainer"
DECLINED = "fix: declined"
WAITING = "waiting for `/fix` or `/no-fix`."
STATUS_RE = re.compile(r"^\*\*Status:\*\* (.*)$", re.MULTILINE)
PREVIOUSLY_RE = re.compile(r"^Previously: (.*)$", re.MULTILINE)
DECISION_RE = re.compile(r"fix (approved|declined) by ")
LOGIN_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})(?:\[bot\])?")
SHA_RE = re.compile(r"[0-9a-f]{40}")
COMMAND_TEXT = 300
FILES_ENV = "AIWF_ANALYSIS_FILES"  # JSON list written by `aiwf analyse-context`
SHA_ENV = "AIWF_ANALYSIS_SHA"


def server() -> str:
    return os.environ.get("GITHUB_SERVER_URL", "https://github.com")


def file_ref(repo: str, sha: str, path: str, line: int, files: set[str]) -> str:
    """A link at the analysed commit for a checked path (to the line when whole-number, 0 = whole file), else inline code."""
    if path in files and SHA_RE.fullmatch(sha) and type(line) is int and line >= 0:
        url = f"{server()}/{repo}/blob/{sha}/{quote(path, safe='/')}" + (f"#L{line}" if line else "")
        return f"[{publish.clean(f'{path}#L{line}' if line else path, 320)}]({url})"
    return inline(f"{path}:{line}" if line else path, 320)


def status_lines(body: str) -> tuple[str, str]:
    """(current status, earlier decision kept as "Previously") of an analysis comment; '' when absent."""
    cur, prev = STATUS_RE.search(body), PREVIOUSLY_RE.search(body)
    return (cur.group(1) if cur else ""), (prev.group(1) if prev else "")


def earlier_decision(body: str) -> str:
    """The decision to keep under a new status: the current status if it is one, else the one already kept."""
    cur, prev = status_lines(body)
    return cur if DECISION_RE.match(cur) else prev


def with_status(body: str, status: str, previously: str) -> str:
    """`body` up to its status line, then the new status and the earlier decision (if any)."""
    head = body[: m.start()] if (m := STATUS_RE.search(body)) else body.rstrip("\n") + "\n\n"
    return head + f"**Status:** {status}" + (f"\nPreviously: {previously}" if previously else "")


def tier_path(path: str) -> str:
    """A path as A's risk rules expect it; one still leaving the root or absolute maps to `.github/` (high by default)."""
    p = posixpath.normpath(re.sub(r"^(?:\./|/)+", "", path))
    return ".github/escape" if p.startswith("../") or p == ".." or p.startswith("/") else p


def maintainers_line(cfg: dict[str, Any]) -> str:
    logins = [m for m in cfg.get("maintainers", []) if LOGIN_RE.fullmatch(m)]
    return " ".join(f"@{m}" for m in logins) + ": reply `/fix`, `/fix <guidance>` or `/no-fix <reason>`."


def analysis_body(data: dict[str, Any], repo: str, sha: str, files: set[str], cfg: dict[str, Any], run_url: str) -> str:
    rc, fix = data["root_cause"], data["proposed_fix"]
    paths = [tier_path(p) for p in [*fix["files_to_change"], rc["file"]] if p]
    tier = "high" if any(p == ".github/escape" for p in paths) else risk_tier(paths, cfg.get("risk_paths") or {})
    to_change = ", ".join(inline(p, 300) for p in fix["files_to_change"]) or "none named"
    run = run_link(run_url, "unknown")
    lines = [MARKER, "## Bug analysis", maintainers_line(cfg),
             f"**Risk tier:** {tier} · **Confidence:** {data['confidence']} · **Size:** {data['size']} · **Run:** {run}", "",
             f"**Root cause** — {file_ref(repo, sha, rc['file'], rc['line'], files)}: "
             f"{publish.clean(rc['explanation'], 1500)}",
             f"**Blast radius** — {publish.clean(data['blast_radius'], 1500)}",
             f"**Proposed fix** — {publish.clean(fix['approach'], 1500)}; files to change: {to_change}; "
             f"regression test: {publish.clean(fix['regression_test'] or 'the reproduction test', 600)}; "
             f"alternatives rejected: {publish.clean(fix['alternatives_rejected'] or 'none', 1000)}"]
    if data["suspicious_instructions"]:
        lines += ["", publish.injection_line(data["suspicious_instructions"])]
    return "\n".join(lines) + "\n\n"


def alert(data: dict[str, Any], repo: str, issue: int) -> tuple[str, str]:
    """The "B4 analysis posted" chat alert (spec: Chat notifications): the root cause in one line (agent text, so
    `notify.plain`: no clickable link, capped) and where to answer; links to the issue."""
    cause = notify.plain(data["root_cause"]["explanation"])
    return (f"[{repo}] Bug #{issue} analysed: {cause}; reply /fix or /no-fix on GitHub",
            f"{server()}/{repo}/issues/{issue}")


def publish_analyst(data: dict[str, Any], repo: str, issue: int, run_url: str, gh: GhRunner) -> None:
    cfg = json.loads(os.environ.get("AIWF_CONFIG") or "{}")
    sha = os.environ.get(SHA_ENV, "")
    files_path = os.environ.get(FILES_ENV, "")
    files = set(json.loads(Path(files_path).read_text(encoding="utf-8"))) if files_path else set()
    found = find_marker_comment(gh, repo, issue, MARKER)
    body = with_status(analysis_body(data, repo, sha, files, cfg, run_url), WAITING,
                       earlier_decision(found.get("body") or "") if found else "")
    if found is None:
        publish.comment(gh, repo, issue, body)
    else:
        patch_comment(gh, repo, found["id"], body)
    publish.add_labels(gh, repo, issue, AWAITING)
    print(f"analysis posted on {repo}#{issue}")
    notify.write_alert(*alert(data, repo, issue))


def patch_comment(gh: GhRunner, repo: str, cid: int, body: str) -> None:
    gh(["api", "-X", "PATCH", f"repos/{repo}/issues/comments/{cid}", "-f", f"body={body}"])


def set_status(gh: GhRunner, repo: str, issue: int, status: str) -> bool:
    """Set the bot's analysis comment's status, keeping an earlier decision; False when there is no such comment."""
    found = find_marker_comment(gh, repo, issue, MARKER)
    if found is None:
        return False
    body = found.get("body") or ""
    patch_comment(gh, repo, found["id"], with_status(body, status, earlier_decision(body)))
    return True


def reanalyse(gh: GhRunner, repo: str, issue: int, run_url: str) -> None:
    """A B2 that reproduced again: any earlier decision no longer stands until B3 posts the new analysis."""
    set_status(gh, repo, issue, f"re-analysing in {run_link(run_url)}; if that run fails, `/reproduce` to analyse again.")


def supersede(gh: GhRunner, repo: str, issue: int, run_url: str) -> None:
    """A B2 that did not reproduce: the analysis no longer stands."""
    set_status(gh, repo, issue, f"superseded by {run_link(run_url)}; `/reproduce` to analyse again.")


def decision_status(name: str, login: str, comment_url: str, text: str) -> str:
    verb, what = ("approved", "guidance") if name == "fix" else ("declined", "reason")
    said = publish.clean(text, COMMAND_TEXT)
    return f"fix {verb} by @{login} ([comment]({comment_url}))" + (f"; {what}: {said}" if said else ".")


def fix_approved(gh: GhRunner, repo: str, issue: int) -> bool:
    """The analysis comment's current status is a `/fix` approval: B5 may be running, and `/no-fix` stops it (spec B4)."""
    found = find_marker_comment(gh, repo, issue, MARKER)
    return bool(found) and status_lines(found.get("body") or "")[0].startswith("fix approved by ")


def decide(gh: GhRunner, repo: str, issue: int, name: str, text: str, event: dict[str, Any]) -> str:
    """Apply an accepted `/fix` or `/no-fix` (config.yml already checked the author, ADR-0005); returns what it did."""
    awaiting = AWAITING in guard.item_labels(gh, repo, issue)
    if not awaiting and not (name == "no-fix" and fix_approved(gh, repo, issue)):
        return f"no '{AWAITING}' on #{issue}: /{name} changes nothing"
    c = event.get("comment") or {}
    login, cid = (c.get("user") or {}).get("login", ""), c.get("id")
    if not LOGIN_RE.fullmatch(login) or not isinstance(cid, int):
        raise RuntimeError("the event has no usable comment author or id")
    remove_label(gh, repo, issue, AWAITING)  # first, so a second command finds nothing to act on
    url = f"{server()}/{repo}/issues/{issue}#issuecomment-{cid}"
    try:
        if name == "no-fix":
            publish.add_labels(gh, repo, issue, DECLINED)
        recorded = set_status(gh, repo, issue, decision_status(name, login, url, text))
    except Exception:
        undo = [lambda: publish.add_labels(gh, repo, issue, AWAITING)] if awaiting else []  # not recorded: resend
        if name == "no-fix":
            undo.append(lambda: remove_label(gh, repo, issue, DECLINED))
        for step in undo:  # each on its own, so one failing call does not skip the other
            try:
                step()
            except Exception as exc:
                print(f"::warning::could not undo a label change on #{issue}: {exc}")
        raise
    if not recorded:
        return f"/{name} by {login} recorded on #{issue}; no analysis comment to update"
    return f"/{name} by {login} recorded on #{issue}"


def cmd_decide(args: argparse.Namespace) -> int:
    cfg = json.loads(os.environ.get("AIWF_CONFIG") or "{}")
    name = cfg.get("command", "")
    if name not in ("fix", "no-fix"):
        print(f"::error::not a /fix or /no-fix run: {name!r}")
        return 1
    if guard.item_off(config.run_gh, args.repo, args.issue):
        print(f"::notice title=ai: off::#{args.issue} has '{guard.OFF_LABEL}': nothing changed")
        return 0
    text = json.loads(cfg.get("command_args") or '""')
    done = decide(config.run_gh, args.repo, args.issue, name, text if isinstance(text, str) else "", cli.read_event())
    print(done)
    out = os.environ.get("GITHUB_OUTPUT")
    if out and name == "fix" and done.endswith(f" recorded on #{args.issue}"):  # recorded in the status line: B5 starts
        cli.write_outputs(out, {"fix": "true"})
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("decide", help="apply a maintainer's /fix or /no-fix (B4) to the analysis comment and labels")
    p.add_argument("--repo", required=True)
    p.add_argument("--issue", required=True, type=int)
    p.set_defaults(func=cmd_decide)


PUBLISHERS = {"analyst": publish_analyst}
