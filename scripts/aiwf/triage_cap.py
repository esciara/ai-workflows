"""Workflow B, B1: daily triage caps for issues from outside authors (ADR-0058).

Runs in triage's `context` job, before any agent, with a read-only token. It lists the repo's issues created in the 24
hours up to the current issue's creation (REST issue list, `state=all`, pull requests dropped), keeps those whose
author is not in `maintainers`, and counts only issues numbered at or below the current one, so a burst is cut the same
way whatever order its runs finish in. Every issue opened counts, triaged or not. The issue is capped when that count
is above `limits.triage_per_day`, or its author's count is above `limits.triage_per_author_per_day`; 0 means outsiders
are never triaged automatically. Maintainers' issues and a maintainer's `/retriage` (any event but `issues`) are never
capped. A capped issue is not retried later: the maintainer runs `/retriage`.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from aiwf import config, guard, publish_triage
from aiwf.ghapi import GhRunner, get_json

WINDOW = timedelta(hours=24)


def parse_time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def is_maintainer(login: str, maintainers: list[str]) -> bool:
    return login.lower() in {m.lower() for m in maintainers}


def recent_issues(gh: GhRunner, repo: str, until: datetime) -> list[dict[str, Any]]:
    """Issues (not PRs) created in the WINDOW up to `until`. `since` filters on update time, a superset."""
    since = quote((until - WINDOW).strftime("%Y-%m-%dT%H:%M:%SZ"), safe="")
    out = gh(["api", "--paginate", "--jq", ".[]",
              f"repos/{repo}/issues?state=all&since={since}&sort=created&direction=desc&per_page=100"])
    items = [json.loads(line) for line in out.splitlines() if line.strip()]
    return [i for i in items if "pull_request" not in i and until - WINDOW <= parse_time(i["created_at"]) <= until]


def cap_reason(issues: list[dict[str, Any]], number: int, author: str, maintainers: list[str],
               limits: dict[str, int]) -> str:
    """Why issue `number` by `author` is capped, or '' when it is not. `issues`: those of the window."""
    if is_maintainer(author, maintainers):
        return ""
    counted = [i for i in issues if i["number"] <= number and not is_maintainer(i["user"]["login"], maintainers)]
    counted_numbers = {i["number"] for i in counted} | {number}  # the current issue always counts
    total = len(counted_numbers)
    mine = len({i["number"] for i in counted if i["user"]["login"].lower() == author.lower()} | {number})
    if total > limits["triage_per_day"]:
        return f"{total} issues from outside authors in 24 hours, above triage_per_day={limits['triage_per_day']}"
    if mine > limits["triage_per_author_per_day"]:
        return f"{mine} issues from this author in 24 hours, above " \
               f"triage_per_author_per_day={limits['triage_per_author_per_day']}"
    return ""


def check(gh: GhRunner, repo: str, number: int, cfg: dict[str, Any], event: str) -> str:
    """The cap reason for this run, or '' (not capped). Only a new issue (`issues` event) is ever capped."""
    if event != "issues":
        return ""
    issue = get_json(gh, f"repos/{repo}/issues/{number}")
    author = (issue.get("user") or {}).get("login", "")
    if is_maintainer(author, cfg["maintainers"]):
        return ""
    issues = recent_issues(gh, repo, parse_time(issue["created_at"]))
    return cap_reason(issues, number, author, cfg["maintainers"], cfg["limits"])


def cmd_cap(args: argparse.Namespace) -> int:
    cfg = json.loads(os.environ.get("AIWF_CONFIG") or "{}")
    reason = check(config.run_gh, args.repo, args.issue, cfg, os.environ.get("GITHUB_EVENT_NAME", ""))
    if reason:
        print(f"::notice title=Triage capped (ADR-0058)::{args.repo}#{args.issue}: {reason}")
    else:
        print(f"triage cap: {args.repo}#{args.issue} not capped")
    out = args.github_output or os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"capped={json.dumps(bool(reason))}\n")
    return 0


def cmd_capped(args: argparse.Namespace) -> int:
    if guard.item_off(config.run_gh, args.repo, args.issue):  # set after the config gate: write nothing (ADR-0045)
        print(f"::notice title=ai: off::#{args.issue} has '{guard.OFF_LABEL}': nothing published")
        return 0
    publish_triage.publish_capped(args.repo, args.issue, config.run_gh)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("triage-cap", help="B1: is this new issue over the daily triage caps? (env AIWF_CONFIG)")
    p.add_argument("--repo", required=True)
    p.add_argument("--issue", required=True, type=int)
    p.add_argument("--github-output", default=None)
    p.set_defaults(func=cmd_cap)
    p = sub.add_parser("triage-capped", help="B1 publish for a capped issue: label and fixed comment, no agent output")
    p.add_argument("--repo", required=True)
    p.add_argument("--issue", required=True, type=int)
    p.set_defaults(func=cmd_capped)
