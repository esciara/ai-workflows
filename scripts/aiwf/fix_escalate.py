"""Workflow B, B5 escalation: the loop ended without an approved fix (spec B5, ADR-0061).

The orchestrator opens no PR. It posts one comment (marker `<!-- ai-workflows:fix -->`, updated in place) that mentions
each maintainer, gives every round's findings and, when `ai-fix/issue-<n>` exists, the compare link from the default
branch to it; it labels `fix: needs-maintainer` and assigns the maintainers the issue. When the status guard stopped the
loop (a later B2, `/no-fix` or another `/fix` changed the analysis status), it does not escalate: the same comment gets
one line saying so, with the compare link of the kept branch to delete before the next `/fix`; no label, no assignment.
Findings are untrusted text: cleaned, and check output only inside a fenced block."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from aiwf import config, guard, publish, publish_analysis
from aiwf.fix import branch_head, branch_name
from aiwf.ghapi import GhRunner, default_branch, upsert_marker_comment
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


def compare_link(gh: GhRunner, repo: str, issue: int) -> str:
    """The compare link from the default branch to the fix branch, or '' when the branch does not exist."""
    branch = branch_name(issue)
    try:
        if not branch_head(gh, repo, branch):
            return ""
        base = default_branch(gh, repo)
    except RuntimeError as exc:  # the comment, label and assignment still matter more than the link
        print(f"::warning::no compare link for {branch}: {str(exc)[:200]}")
        return ""
    server = os.environ.get("GITHUB_SERVER_URL") or "https://github.com"
    return f"{server}/{repo}/compare/{base}...{branch}"


def round_lines(r: dict[str, Any]) -> list[str]:
    lines = [f"### Round {r['round']}: {r['outcome']}", ""]
    lines += [f"- {publish.clean(f, 1000)}" for f in r["findings"]] or ["- No findings recorded."]
    if r.get("check_output"):
        lines += ["", "Check output (end):", "", fence(r["check_output"])]
    if r.get("suspicious_instructions"):
        lines += ["", publish.injection_line(r["suspicious_instructions"])]
    return lines + [""]


def body(logins: list[str], rounds: list[dict[str, Any]], link: str, run_url: str) -> str:
    mention = " ".join(f"@{m}" for m in logins)
    pushed = any(r.get("pushed") for r in rounds)
    if link and pushed:
        where = f"The last pushed work is on the branch, to open a PR from (none was opened): {link}."
    elif link:
        where = f"Someone else pushed to the branch, which is theirs: {link}."
    elif pushed:
        where = "The branch was pushed, then deleted."
    else:
        where = "Nothing was pushed, so there is no branch."
    lines = [MARKER, f"**Fix needs a maintainer.** {mention}: the fix loop ended after {len(rounds)} round(s) without an "
             f"approved fix; labelled `{NEEDS_MAINTAINER}`. {where} {run_link(run_url, '')}".rstrip(), ""]
    for r in rounds:
        lines += round_lines(r)
    return "\n".join(lines)


def superseded(rounds: list[dict[str, Any]]) -> bool:
    """The loop stopped because the analysis comment's status changed while it ran: no escalation (spec B5)."""
    return bool(rounds) and bool(rounds[-1].get("superseded"))


def superseded_body(link: str, run_url: str) -> str:
    where = f"branch kept: {link}; delete it before the next `/fix`" if link else "no branch left"
    why = "the analysis status changed while this ran (newer analysis, `/no-fix` or another `/fix`)"
    return f"{MARKER}\nFix loop stopped: {why}; {where}. {run_link(run_url, '')}".rstrip()


def escalate(gh: GhRunner, repo: str, issue: int, cfg: dict[str, Any], rounds: list[dict[str, Any]],
             run_url: str) -> str:
    link = compare_link(gh, repo, issue)
    if superseded(rounds):
        upsert_marker_comment(gh, repo, issue, MARKER, superseded_body(link, run_url))
        return f"#{issue}: analysis status changed, not escalated"
    logins = maintainers(cfg)
    upsert_marker_comment(gh, repo, issue, MARKER, body(logins, rounds, link, run_url))
    publish.add_labels(gh, repo, issue, NEEDS_MAINTAINER)
    if logins:
        people = [a for m in logins for a in ("-f", f"assignees[]={m}")]
        try:
            gh(["api", "-X", "POST", f"repos/{repo}/issues/{issue}/assignees", *people])
        except RuntimeError as exc:  # the comment already mentions them; a failure here only shows in the log
            print(f"::warning::could not assign the issue #{issue}: {str(exc)[:200]}")
    return f"escalated #{issue}: compare link {link or 'none'}"


def cmd_escalate(args: argparse.Namespace) -> int:
    if guard.item_off(config.run_gh, args.repo, args.issue):
        print(f"::notice title=ai: off::#{args.issue} has '{guard.OFF_LABEL}': not escalated")
        return 0
    cfg = json.loads(os.environ.get("AIWF_CONFIG") or "{}")
    print(escalate(config.run_gh, args.repo, args.issue, cfg, records(Path(args.records)), os.environ.get("RUN_URL", "")))
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("fix-escalate", help="B5: findings comment, compare link, label and assignment after a failed loop")
    p.add_argument("--repo", required=True)
    p.add_argument("--issue", required=True, type=int)
    p.add_argument("--records", required=True, help="folder holding each round's round.json")
    p.set_defaults(func=cmd_escalate)
