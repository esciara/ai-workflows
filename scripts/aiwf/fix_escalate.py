"""Workflow B, B5 escalation: the loop ended without an approved fix (spec B5).

The orchestrator opens the last pushed work as a draft PR (none when nothing was pushed), posts one comment (marker
`<!-- ai-workflows:fix -->`, updated in place) that mentions each maintainer and gives every round's findings, labels
`fix: needs-maintainer`, assigns the maintainers the issue and the draft PR and requests their review on it. Opening
the PR can be refused (the repo setting "Allow GitHub Actions to create and approve pull requests" off): the comment
then says so, and the label and the issue assignment still happen. Findings are untrusted text: cleaned, and check
output only inside a fenced block.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from aiwf import config, guard, publish, publish_analysis
from aiwf.fix import branch_name, post_json
from aiwf.ghapi import GhRunner, upsert_marker_comment
from aiwf.mdtext import run_link
from aiwf.publish_reproduce import fence

MARKER = "<!-- ai-workflows:fix -->"
NEEDS_MAINTAINER = "fix: needs-maintainer"


def maintainers(cfg: dict[str, Any]) -> list[str]:
    return [m for m in cfg.get("maintainers", []) if publish_analysis.LOGIN_RE.fullmatch(m)]


def records(folder: Path) -> list[dict[str, Any]]:
    """Round records (round.json from each round's artifact), by round."""
    found = [json.loads(p.read_text(encoding="utf-8")) for p in folder.rglob("round.json")]
    return sorted(found, key=lambda r: r["round"])


def draft_pr(gh: GhRunner, repo: str, issue: int, run_url: str) -> tuple[dict[str, Any] | None, str]:
    """(the open draft PR from the fix branch, '') or (None, why it could not be opened). An existing one is reused."""
    branch = branch_name(issue)
    owner = repo.split("/")[0]
    try:
        found = json.loads(gh(["api", f"repos/{repo}/pulls?head={owner}:{branch}&state=open&per_page=10"]) or "[]")
        if found:
            return found[0], ""
        base = json.loads(gh(["api", f"repos/{repo}"]) or "{}").get("default_branch") or "main"
        body = (f"Draft from the ai-workflows fix loop for #{issue}: no round was approved, so a maintainer takes over. "
                f"Each round's findings are on the issue. {run_link(run_url, '')}").strip()
        pr = post_json(gh, "POST", f"repos/{repo}/pulls", {"title": f"Draft fix for #{issue} (needs a maintainer)",
                                                           "head": branch, "base": base, "body": body, "draft": True})
        return pr, ""
    except RuntimeError as exc:
        why = (str(exc).splitlines() or ["refused"])[0][:200]
        print(f"::error title=Draft PR not opened::{publish.clean(why, 200)}")
        return None, why


def round_lines(r: dict[str, Any]) -> list[str]:
    lines = [f"### Round {r['round']}: {r['outcome']}", ""]
    lines += [f"- {publish.clean(f, 1000)}" for f in r["findings"]] or ["- No findings recorded."]
    if r.get("check_output"):
        lines += ["", "Check output (end):", "", fence(r["check_output"])]
    if r.get("suspicious_instructions"):
        lines += ["", publish.injection_line(r["suspicious_instructions"])]
    return lines + [""]


def body(logins: list[str], rounds: list[dict[str, Any]], pr: dict[str, Any] | None, why: str, pushed: bool,
         run_url: str) -> str:
    mention = " ".join(f"@{m}" for m in logins)
    if pr:
        where = f"The last round's work is in draft PR #{pr['number']} ({pr['html_url']})."
    elif pushed:
        where = f"The draft PR could not be opened ({publish.clean(why, 200)}); the work is on its branch."
    else:
        where = "Nothing was pushed, so there is no branch and no draft PR."
    lines = [MARKER, f"**Fix needs a maintainer.** {mention}: the fix loop ended after {len(rounds)} round(s) without an "
             f"approved fix; labelled `{NEEDS_MAINTAINER}`. {where} {run_link(run_url, '')}".rstrip(), ""]
    for r in rounds:
        lines += round_lines(r)
    return "\n".join(lines)


def escalate(gh: GhRunner, repo: str, issue: int, cfg: dict[str, Any], rounds: list[dict[str, Any]], head: str,
             run_url: str) -> str:
    logins = maintainers(cfg)
    pr, why = draft_pr(gh, repo, issue, run_url) if head else (None, "")
    upsert_marker_comment(gh, repo, issue, MARKER, body(logins, rounds, pr, why, bool(head), run_url))
    publish.add_labels(gh, repo, issue, NEEDS_MAINTAINER)
    people = [a for m in logins for a in ("-f", f"assignees[]={m}")]
    calls = [("assign the issue", f"#{issue}", ["api", "-X", "POST", f"repos/{repo}/issues/{issue}/assignees", *people])]
    if pr:
        calls += [(what, f"#{pr['number']}", call) for what, call in (("assign the draft PR", ["api", "-X", "POST", f"repos/{repo}/issues/{pr['number']}/assignees",
                                                     *people]),
                           ("request review", ["api", "-X", "POST", f"repos/{repo}/pulls/{pr['number']}/requested_reviewers",
                                               *[a for m in logins for a in ("-f", f"reviewers[]={m}")]]))]
    for what, where, call in calls if logins else []:
        try:
            gh(call)
        except RuntimeError as exc:  # the comment already mentions them; a failure here only shows in the log
            print(f"::warning::could not {what} on {where}: {str(exc)[:200]}")
    return f"escalated #{issue}: draft PR {('#' + str(pr['number'])) if pr else 'none'}"


def cmd_escalate(args: argparse.Namespace) -> int:
    if guard.item_off(config.run_gh, args.repo, args.issue):
        print(f"::notice title=ai: off::#{args.issue} has '{guard.OFF_LABEL}': not escalated")
        return 0
    cfg = json.loads(os.environ.get("AIWF_CONFIG") or "{}")
    print(escalate(config.run_gh, args.repo, args.issue, cfg, records(Path(args.records)),
                   os.environ.get("FIX_HEAD", ""), os.environ.get("RUN_URL", "")))
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("fix-escalate", help="B5: draft PR, findings comment, label and assignment after a failed loop")
    p.add_argument("--repo", required=True)
    p.add_argument("--issue", required=True, type=int)
    p.add_argument("--records", required=True, help="folder holding each round's round.json")
    p.set_defaults(func=cmd_escalate)
