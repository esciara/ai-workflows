"""Workflow B e2e helpers shared by test_wp6 to test_wp10 (moved out of test_wp6.py and test_wp7.py)."""

from __future__ import annotations

import base64
import json
from typing import Any

import yaml

import playground as pg

E2E_WORKFLOW = pg.E2E_WORKFLOW  # the held slot's playground caller, caller-e2e-<n>.yml (ADR-0056)
NEEDS_INFO_MARKER = "<!-- ai-workflows:needs-info -->"
REPRODUCED = "triage: reproduced"
NEEDS_INFO = "triage: needs-info"
NEEDS_HUMAN = "triage: needs-human"
ERROR = "ai: error"
REPRODUCE_JOB = "triage / reproduce"
REPRO_TIMEOUT = 1500  # B1 or a comment run, then setup + tests in the sandbox, on a cold runner


def item_run(event: str, title: str, after: str, timeout: int = REPRO_TIMEOUT) -> dict[str, Any]:
    """The first completed run of the e2e caller for this item (by display title) and event, created since `after`."""

    def find() -> int | None:
        got = pg.api(f"repos/{pg.REPO}/actions/runs?event={event}&created=%3E%3D{after}&per_page=100")
        hits = [r for r in got["workflow_runs"]
                if r["name"] == E2E_WORKFLOW and r["display_title"] == title and r["created_at"] >= after]
        return min(hits, key=lambda r: (r["created_at"], r["id"]))["id"] if hits else None

    run_id = pg.poll(find, f"the e2e {event} run of {title!r}", timeout=timeout)

    def done() -> dict | None:
        run = pg.api(f"repos/{pg.REPO}/actions/runs/{run_id}")
        return run if run["status"] == "completed" else None

    run = pg.poll(done, f"run {run_id} to complete", timeout=timeout)
    run["jobs"] = pg.jobs(run_id)
    print(f"{title}: run {run_id} {run['html_url']} -> {run['conclusion']}, jobs {run['jobs']}")
    return run


def comment_run(issue: dict[str, Any], body: str, *, as_tester: bool) -> dict[str, Any]:
    """Post a comment (maintainer or reporter) and return that comment's completed run."""
    c = pg.comment(issue["number"], body, as_tester=as_tester)
    return item_run("issue_comment", issue["title"], c["created_at"])


def labels(number: int) -> set[str]:
    return {lb["name"] for lb in pg.api(f"repos/{pg.REPO}/issues/{number}/labels?per_page=100")}


def bot_comments(number: int, marker: str) -> list[dict]:
    out = pg.gh(["api", "--paginate", f"repos/{pg.REPO}/issues/{number}/comments?per_page=100", "--jq", ".[]"])
    comments = [json.loads(line) for line in out.splitlines() if line.strip()]
    return [c for c in comments if c["user"]["login"] == pg.BOT and (c["body"] or "").startswith(marker)]


E2E_CONFIG = ".github/ai-workflows-e2e.yml"  # the slot callers' config (ADR-0050)


def e2e_config() -> dict[str, Any]:
    raw = pg.api(f"repos/{pg.REPO}/contents/{E2E_CONFIG}")
    return yaml.safe_load(base64.b64decode(raw["content"]))
