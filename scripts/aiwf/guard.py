"""Guardrails (WP12a, ADR-0045): the `ai: off` kill switch on an item, and `ai: error` reporting when a run fails.

- `item_off`: the live re-check before a write; a label added after the config gate still stops every write.
- `report_error`: label `ai: error` plus one sticky error comment with the run link and a reason built from job names
  only (never agent text). Nothing re-runs: the maintainer reads the log, removes the label and re-runs if wanted.
- `cancel_runs`: the caller's `off` job cancels this workflow's in-flight runs for the item.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Callable
from urllib.parse import quote

OFF_LABEL = "ai: off"
ERROR_LABEL = "ai: error"
PENDING = "ai-review: pending"
ERROR_MARKER = "<!-- ai-workflows:error -->"
BOT = "github-actions[bot]"  # only the GITHUB_TOKEN identity's marker comment is ours (ADR-0021)
ITEM_EVENTS = ("issues", "issue_comment")  # runs matched by display title; pull_request runs by PR number

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


def remove_label(gh: GhRunner, repo: str, number: int, label: str) -> None:
    try:
        gh(["api", "-X", "DELETE", f"repos/{repo}/issues/{number}/labels/{quote(label, safe='')}"])
    except RuntimeError as exc:
        if "404" not in str(exc) and "Not Found" not in str(exc):
            raise


def failed_jobs(needs: dict[str, Any]) -> list[str]:
    """Names of the needed jobs that failed (`toJSON(needs)`); job names are ours, never agent text."""
    return sorted(name for name, job in needs.items() if isinstance(job, dict) and job.get("result") == "failure")


def error_body(run_url: str, reason: str) -> str:
    return (f"{ERROR_MARKER}\n⚠️ **ai-workflows stopped with an error** ({reason}). [Run log]({run_url})\n\n"
            "Nothing is retried. Check the run log, then remove `ai: error` and re-run the workflow, or comment "
            "`/review` (PR) or `/retriage` (issue).")


def find_error_comment(gh: GhRunner, repo: str, number: int) -> int | None:
    out = gh(["api", "--paginate", f"repos/{repo}/issues/{number}/comments?per_page=100", "--jq", ".[]"])
    for line in out.splitlines():
        if line.strip():
            c = json.loads(line)
            if c["user"]["login"] == BOT and (c.get("body") or "").startswith(ERROR_MARKER):
                return c["id"]
    return None


def report_error(gh: GhRunner, repo: str, number: int, run_url: str, reason: str) -> bool:
    """`ai: error` and one sticky error comment; nothing when the item now has `ai: off`. Idempotent."""
    remove_label(gh, repo, number, PENDING)
    if item_off(gh, repo, number):
        print(f"{repo}#{number} has '{OFF_LABEL}': error not reported")
        return False
    gh(["api", "-X", "POST", f"repos/{repo}/issues/{number}/labels", "-f", f"labels[]={ERROR_LABEL}"])
    body = error_body(run_url, reason)
    cid = find_error_comment(gh, repo, number)
    if cid is None:
        gh(["api", "-X", "POST", f"repos/{repo}/issues/{number}/comments", "-f", f"body={body}"])
    else:
        gh(["api", "-X", "PATCH", f"repos/{repo}/issues/comments/{cid}", "-f", f"body={body}"])
    print(f"{repo}#{number}: {ERROR_LABEL} ({reason})")
    return True


def is_item_run(run: dict[str, Any], number: int, title: str) -> bool:
    if run.get("event") == "pull_request":
        return number in [p.get("number") for p in run.get("pull_requests") or []]
    return run.get("event") in ITEM_EVENTS and bool(title) and run.get("display_title") == title


def cancel_runs(gh: GhRunner, repo: str, run_id: int, number: int, title: str) -> list[int]:
    """Cancel the in-flight runs of this run's workflow for item `number`; returns their ids."""
    own = json.loads(gh(["api", f"repos/{repo}/actions/runs/{run_id}"]))
    got = json.loads(gh(["api", f"repos/{repo}/actions/workflows/{own['workflow_id']}/runs?per_page=100"]))
    cancelled = []
    for run in got.get("workflow_runs") or []:
        if run["id"] == run_id or run.get("status") == "completed" or not is_item_run(run, number, title):
            continue
        try:
            gh(["api", "-X", "POST", f"repos/{repo}/actions/runs/{run['id']}/cancel"])
        except RuntimeError as exc:  # finished meanwhile (409)
            print(f"::warning::run {run['id']} not cancelled: {exc}")
            continue
        cancelled.append(run["id"])
    print(f"{repo}#{number}: '{OFF_LABEL}' cancelled runs {cancelled or 'none'}")
    return cancelled


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


def cmd_cancel_runs(args: argparse.Namespace) -> int:
    from aiwf import config

    cancel_runs(config.run_gh, args.repo, args.run_id, args.item, os.environ.get("ITEM_TITLE", ""))
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("report-error", help="label `ai: error` and post the error comment (env AIWF_NEEDS)")
    p.add_argument("--repo", required=True)
    p.add_argument("--issue", required=True, type=int)
    p.add_argument("--run-url", required=True)
    p.set_defaults(func=cmd_report_error)
    p = sub.add_parser("cancel-runs", help="`ai: off`: cancel this workflow's in-flight runs for an item "
                                           "(env ITEM_TITLE)")
    p.add_argument("--repo", required=True)
    p.add_argument("--run-id", required=True, type=int)
    p.add_argument("--item", required=True, type=int)
    p.set_defaults(func=cmd_cancel_runs)
