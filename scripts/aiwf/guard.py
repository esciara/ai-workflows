"""Guardrails (WP12a, ADR-0045): the `ai: off` kill switch on an item, and `ai: error` reporting when a run fails.

- `item_off`: the live re-check before a write; a label added after the config gate still stops every write.
- `report_error`: label `ai: error` plus one sticky error comment with the run link and a reason built from job names
  only (never agent text). Nothing re-runs: the maintainer reads the log, removes the label and re-runs if wanted.
- `budget_hit` / `report_budget` (WP12b): an agent stopped by its cost or time budget, or a run total over budget,
  escalates (`ai: budget` plus the workflow's hand-over label, one sticky note with the run link); not an error.
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
BUDGET_LABEL = "ai: budget"
BUDGET_MARKER = "<!-- ai-workflows:budget -->"
BUDGET_SUBTYPE = "error_max_budget_usd"  # Claude Code's result subtype when --max-budget-usd stops the agent
BOT = "github-actions[bot]"  # only the GITHUB_TOKEN identity's marker comment is ours (ADR-0021)

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


def find_marker_comment(gh: GhRunner, repo: str, number: int, marker: str) -> int | None:
    out = gh(["api", "--paginate", f"repos/{repo}/issues/{number}/comments?per_page=100", "--jq", ".[]"])
    for line in out.splitlines():
        if line.strip():
            c = json.loads(line)
            if c["user"]["login"] == BOT and (c.get("body") or "").startswith(marker):
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
    cid = find_marker_comment(gh, repo, number, ERROR_MARKER)
    if cid is None:
        gh(["api", "-X", "POST", f"repos/{repo}/issues/{number}/comments", "-f", f"body={body}"])
    else:
        gh(["api", "-X", "PATCH", f"repos/{repo}/issues/comments/{cid}", "-f", f"body={body}"])
    print(f"{repo}#{number}: {ERROR_LABEL} ({reason})")
    return True


def budget_hit(usage: dict[str, Any], limits: dict[str, Any]) -> str:
    """Why the run is over budget, or "": an agent stopped by `--max-budget-usd` or by its step timeout, or the sum of
    the agents' cost over `run_budget_usd`. `usage` maps agent name to its usage record (scripts/agent-usage.sh)."""
    agents = {k: v for k, v in usage.items() if isinstance(v, dict)}
    for name in sorted(agents):
        if agents[name].get("subtype") == BUDGET_SUBTYPE:
            return f"agent `{name}` hit its cost budget (${limits.get('agent_budget_usd')})"
        if agents[name].get("timed_out") is True:
            return f"agent `{name}` hit its time budget ({limits.get('agent_minutes')} min)"
    total = sum(v["cost_usd"] for v in agents.values() if isinstance(v.get("cost_usd"), (int, float)))
    cap = limits.get("run_budget_usd")
    if isinstance(cap, (int, float)) and total > cap:
        return f"the run's agents cost ${total:.2f}, over the run budget (${cap})"
    return ""


def budget_body(run_url: str, reason: str, escalate: str) -> str:
    return (f"{BUDGET_MARKER}\n⏱️ **ai-workflows stopped: budget reached** ({reason}). [Run log]({run_url})\n\n"
            f"Nothing was published and nothing is retried. Labelled `{escalate}`: a person takes over. To run it "
            "again, raise the limits in `.github/ai-workflows.yml` if needed, remove `ai: budget` and re-run.")


def report_budget(gh: GhRunner, repo: str, number: int, run_url: str, reason: str, escalate: str) -> bool:
    """`ai: budget` + `escalate` and one sticky budget note; nothing but pending removal under `ai: off`."""
    remove_label(gh, repo, number, PENDING)
    if item_off(gh, repo, number):
        print(f"{repo}#{number} has '{OFF_LABEL}': budget hit not reported")
        return False
    gh(["api", "-X", "POST", f"repos/{repo}/issues/{number}/labels", "-f", f"labels[]={BUDGET_LABEL}",
        "-f", f"labels[]={escalate}"])
    body = budget_body(run_url, reason, escalate)
    cid = find_marker_comment(gh, repo, number, BUDGET_MARKER)
    if cid is None:
        gh(["api", "-X", "POST", f"repos/{repo}/issues/{number}/comments", "-f", f"body={body}"])
    else:
        gh(["api", "-X", "PATCH", f"repos/{repo}/issues/comments/{cid}", "-f", f"body={body}"])
    print(f"::warning title=Budget reached::{repo}#{number}: {reason}")
    return True


def check_budget(gh: GhRunner, repo: str, number: int, run_url: str, escalate: str,
                 usage: dict[str, Any] | None = None) -> bool:
    """`usage` (agent -> usage; default env AIWF_USAGE) against the limits in env AIWF_CONFIG: report a budget hit and
    set the step output `budget=true`."""
    try:
        if usage is None:
            usage = json.loads(os.environ.get("AIWF_USAGE") or "{}")
        limits = json.loads(os.environ.get("AIWF_CONFIG") or "{}").get("limits") or {}
    except (json.JSONDecodeError, AttributeError):
        return False
    reason = budget_hit(usage if isinstance(usage, dict) else {}, limits)
    if not reason:
        return False
    report_budget(gh, repo, number, run_url, reason, escalate)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
            fh.write("budget=true\n")
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
