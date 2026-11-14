"""Guardrails (WP12a, ADR-0045): the `ai: off` kill switch on an item, and `ai: error` reporting when a run fails.

- `item_off`: the live re-check before a write; a label added after the config gate still stops every write.
- `report_error`: label `ai: error` plus one sticky error comment with the run link and a reason built from job names
  only (never agent text). Nothing re-runs: the maintainer reads the log, removes the label and re-runs if wanted.
- An agent that hits its time or turn limit (ADR-0050) fails its job, so it goes through `report_error` too.
- `clear_error`: a later run that publishes its result marks the sticky error comment as cleared (aiwf-3ci), so an
  old error no longer reads as current; the marker stays, so a new error updates the same comment.
- A stale PR run reports nothing (aiwf-3ci): with `--head-sha`, when the PR's head is no longer that commit (a push
  after the gate chose it, e.g. "PR head moved"), the run for the new head owns the labels and reports its own result.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from aiwf import labels
from aiwf.ghapi import GhRunner, find_marker_comment, get_or_none, remove_label, upsert_marker_comment

OFF_LABEL = "ai: off"
ERROR_LABEL = labels.ERROR
PENDING = labels.PENDING
ERROR_MARKER = "<!-- ai-workflows:error -->"


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


CLEARED = "✅ **An earlier ai-workflows error is cleared:** a later run finished."


def clear_error(gh: GhRunner, repo: str, number: int, run_url: str) -> None:
    """Mark our sticky error comment as cleared, when there is one not yet cleared; fixed text only."""
    found = find_marker_comment(gh, repo, number, ERROR_MARKER)
    if found and not found["body"].startswith(f"{ERROR_MARKER}\n{CLEARED}"):
        body = f"{ERROR_MARKER}\n{CLEARED}" + (f" [Run log]({run_url})" if run_url else "")
        gh(["api", "-X", "PATCH", f"repos/{repo}/issues/comments/{found['id']}", "-f", f"body={body}"])


def head_moved(gh: GhRunner, repo: str, number: int, sha: str) -> bool:
    """The PR's head is now another commit than `sha` and that push starts its own review: a same-repo PR, not a
    draft (a fork PR or a draft gets no automatic review, so this run still reports). An unreadable PR: not moved."""
    pr = get_or_none(gh, f"repos/{repo}/pulls/{number}")
    if not isinstance(pr, dict) or pr.get("draft"):
        return False
    head = pr.get("head") or {}
    same_repo = (head.get("repo") or {}).get("full_name") == repo
    return bool(head.get("sha")) and head["sha"] != sha and same_repo


def cmd_report_error(args: argparse.Namespace) -> int:
    from aiwf import config

    if args.head_sha and head_moved(config.run_gh, args.repo, args.issue, args.head_sha):
        print(f"{args.repo}#{args.issue}: head moved from {args.head_sha}; the newer run reports, not this one")
        return 0
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
    p.add_argument("--head-sha", default="", help="PR runs: the head the run reviewed; skip when the PR moved on")
    p.set_defaults(func=cmd_report_error)
