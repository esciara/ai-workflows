"""Guardrails (WP12a, ADR-0045): the `ai: off` kill switch on an item, and `ai: error` reporting when a run fails.

- `item_off`: the live re-check before a write; a label added after the config gate still stops every write.
- `report_error`: label `ai: error` plus one sticky error comment with the run link and a reason built from job names
  only (never agent text). Nothing re-runs: the maintainer reads the log, removes the label and re-runs if wanted.
- An agent that hits its time or turn limit (ADR-0050) fails its job, so it goes through `report_error` too.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Callable

from aiwf.ghapi import remove_label, upsert_marker_comment

OFF_LABEL = "ai: off"
ERROR_LABEL = "ai: error"
PENDING = "ai-review: pending"
ERROR_MARKER = "<!-- ai-workflows:error -->"

GhRunner = Callable[[list[str]], str]


def event_labels(payload: dict[str, Any]) -> set[str]:
    """Label names on the event's issue or PR, as the event saw them."""
    names = set()
    for key in ("issue", "pull_request"):
        for lb in (payload.get(key) or {}).get("labels") or []:
            if isinstance(lb, dict) and isinstance(lb.get("name"), str):
                names.add(lb["name"])
    return names


def item_labels(gh: GhRunner, repo: str, number: int) -> set[str]:
    got = json.loads(gh(["api", f"repos/{repo}/issues/{number}/labels?per_page=100"]) or "[]")
    return {lb["name"] for lb in got if isinstance(lb, dict) and "name" in lb} if isinstance(got, list) else set()


def item_off(gh: GhRunner, repo: str, number: int) -> bool:
    return OFF_LABEL in item_labels(gh, repo, number)


def failed_jobs(needs: dict[str, Any]) -> list[str]:
    """Names of the needed jobs that failed (`toJSON(needs)`); job names are ours, never agent text."""
    return sorted(name for name, job in needs.items() if isinstance(job, dict) and job.get("result") == "failure")


def error_body(run_url: str, reason: str) -> str:
    return (f"{ERROR_MARKER}\n⚠️ **ai-workflows stopped with an error** ({reason}). [Run log]({run_url})\n\n"
            "Nothing is retried. Check the run log, then remove `ai: error` and re-run the workflow, or comment "
            "`/review` (PR) or `/retriage` (issue).")


def report_error(gh: GhRunner, repo: str, number: int, run_url: str, reason: str) -> bool:
    """`ai: error` and one sticky error comment; nothing when the item now has `ai: off`. Idempotent."""
    remove_label(gh, repo, number, PENDING)
    if item_off(gh, repo, number):
        print(f"{repo}#{number} has '{OFF_LABEL}': error not reported")
        return False
    gh(["api", "-X", "POST", f"repos/{repo}/issues/{number}/labels", "-f", f"labels[]={ERROR_LABEL}"])
    upsert_marker_comment(gh, repo, number, ERROR_MARKER, error_body(run_url, reason))
    print(f"{repo}#{number}: {ERROR_LABEL} ({reason})")
    return True


def cmd_report_error(args: argparse.Namespace) -> int:
    from aiwf import config

    try:
        needs = json.loads(os.environ.get("AIWF_NEEDS") or "{}")
    except json.JSONDecodeError:
        needs = {}
    jobs = failed_jobs(needs if isinstance(needs, dict) else {})
    reason = f"failed job: {', '.join(jobs)}" if jobs else "a job failed"
    report_error(config.run_gh, args.repo, args.issue, args.run_url, reason)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("report-error", help="label `ai: error` and post the error comment (env AIWF_NEEDS)")
    p.add_argument("--repo", required=True)
    p.add_argument("--issue", required=True, type=int)
    p.add_argument("--run-url", required=True)
    p.set_defaults(func=cmd_report_error)
