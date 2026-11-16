"""Workflow B, B6: hand over the PR after an approved B5 round (spec B6, ADR-0061).

The orchestrator opens no PR. It posts one comment (marker `<!-- ai-workflows:fix-pr -->`, updated in place on a rerun)
that mentions each maintainer and gives the compare link from the default branch to `ai-fix/issue-<n>`, with the PR
title and the label `ai-fix` pre-filled, and the PR body to paste in a fenced block: `Fixes #<n>`, root cause, what
changed, the repro test and a round-by-round log. The maintainer opens the PR as themselves, so the target's CI and
Workflow A run on it. Every text from the issue, the agents or the analysis is untrusted: cleaned (no mention, HTML or
link survives), length-capped and, in the link, URL-encoded."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

from aiwf import config, guard, publish, publish_analysis, publish_reproduce, triage
from aiwf.fix import repro_command
from aiwf.fix_escalate import compare_link, maintainers, records
from aiwf.ghapi import GhRunner, find_marker_comment, upsert_marker_comment
from aiwf.mdtext import run_link
from aiwf.publish_reproduce import fence

MARKER = "<!-- ai-workflows:fix-pr -->"
LABEL = "ai-fix"
MAX_TITLE = 100
MAX_FINDING = 300
ROOT_CAUSE = "**Root cause** — "


def pr_title(issue: int, title: str) -> str:
    """`Fix #<n>: <issue title>`, one line, length-capped. Plain text: a PR title renders no Markdown."""
    return f"Fix #{issue}: {' '.join(str(title).split())}"[:MAX_TITLE].rstrip()


def form_link(link: str, title: str) -> str:
    """The compare link opening the PR form with the title and the label `ai-fix` filled in; every value URL-encoded."""
    return f"{link}?expand=1&title={quote(title, safe='')}&labels={quote(LABEL, safe='')}"


def root_cause(analysis: str) -> str:
    """B3's root-cause paragraph (already cleaned when B4 published it), as one capped line; '' when absent."""
    for line in analysis.splitlines():
        if line.startswith(ROOT_CAUSE):
            return " ".join(line.removeprefix(ROOT_CAUSE).split())[:1500]
    return ""


def round_log(rounds: list[dict[str, Any]]) -> list[str]:
    lines = []
    for r in rounds:
        notes = [f"  - {publish.clean(f, MAX_FINDING)}" for f in r.get("findings", [])[:5]]
        lines += [f"- Round {int(r['round'])}: {publish.clean(r['outcome'], 20)}", *notes]
    return lines


def code(text: str) -> str:
    """Inline code for a line of the pasted text: one line, no backtick (the text is not in a table, so `|` stays)."""
    return "`" + " ".join(str(text).split())[:300].replace("`", "'") + "`"


def pr_body(issue: int, cause: str, rounds: list[dict[str, Any]], test: tuple[str, str]) -> str:
    final = rounds[-1]
    path, command = test
    repro = f"{code(path)}, run with {code(command)}" if path and command else "see the reproduction comment"
    lines = [f"Fixes #{issue}", "", f"**Root cause:** {cause or 'see the analysis comment on the issue'}", "",
             f"**What changed:** {publish.clean(final.get('summary') or 'see the diff', 1000)}", "",
             f"**Reproduction test:** {repro}", "", f"**Fix loop ({len(rounds)} round(s)):**", *round_log(rounds)]
    if final.get("suspicious_instructions"):
        lines += ["", publish.injection_line(final["suspicious_instructions"])]
    return "\n".join(lines)


def body(logins: list[str], link: str, text: str, run_url: str) -> str:
    mention = " ".join(f"@{m}" for m in logins) or "Maintainers"
    return "\n".join([
        MARKER,
        f"**Fix ready.** {mention}: the fix loop approved a fix and pushed it to its branch. Workflow B opens no PR: "
        f"[open one from the branch]({link}) (title and the label `{LABEL}` are filled in), then paste the text below "
        f"as its description. Workflow A reviews the PR once it is open. {run_link(run_url, '')}".rstrip(), "",
        "PR description to paste:", "", fence(text, "markdown")])


def handover(gh: GhRunner, repo: str, issue: int, cfg: dict[str, Any], rounds: list[dict[str, Any]], run_url: str) -> str:
    if not rounds or rounds[-1].get("outcome") != "approved":
        return f"#{issue}: no approved round, nothing to hand over"
    link = compare_link(gh, repo, issue)
    if not link:  # the branch was deleted since the push: the approved work is gone, so say nothing misleading
        return f"#{issue}: the fix branch no longer exists, nothing to hand over"
    item = triage.get_json(gh, f"repos/{repo}/issues/{issue}")
    analysis = find_marker_comment(gh, repo, issue, publish_analysis.MARKER) or {}
    repro = find_marker_comment(gh, repo, issue, publish_reproduce.MARKER) or {}
    cause = root_cause(analysis.get("body") or "")
    text = pr_body(issue, cause, rounds, repro_command(repro.get("body") or ""))
    upsert_marker_comment(gh, repo, issue, MARKER,
                          body(maintainers(cfg), form_link(link, pr_title(issue, item.get("title") or "")), text, run_url))
    return f"handed over #{issue}: compare link {link}"


def cmd_handover(args: argparse.Namespace) -> int:
    if guard.item_off(config.run_gh, args.repo, args.issue):
        print(f"::notice title=ai: off::#{args.issue} has '{guard.OFF_LABEL}': not handed over")
        return 0
    cfg = json.loads(os.environ.get("AIWF_CONFIG") or "{}")
    print(handover(config.run_gh, args.repo, args.issue, cfg, records(Path(args.records)), os.environ.get("RUN_URL", "")))
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("fix-handover", help="B6: compare-link comment with the PR text after an approved fix")
    p.add_argument("--repo", required=True)
    p.add_argument("--issue", required=True, type=int)
    p.add_argument("--records", required=True, help="folder holding each round's round.json")
    p.set_defaults(func=cmd_handover)
