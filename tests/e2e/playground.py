"""Helpers for end-to-end acceptance tests against the playground repo (network, real GitHub)."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

import pytest

ROOT = Path(__file__).resolve().parents[2]
REPO = os.environ.get("AIWF_E2E_REPO", "esciara/ai-workflows-playground")
WORKFLOW = "AI workflows"  # name of the caller workflow in the target repo
BOT = "github-actions[bot]"
PING_MARKER = "<!-- ai-workflows:ping -->"
FIXTURE_LABEL = "test-fixture"
RUN_TIMEOUT = int(os.environ.get("AIWF_E2E_TIMEOUT", "600"))
POLL_INTERVAL = int(os.environ.get("AIWF_E2E_POLL", "5"))

T = TypeVar("T")


def gh(args: list[str], as_tester: bool = False) -> str:
    """Run gh as the maintainer (local gh auth) or as the tester App. API failures fail the test."""
    cmd = [str(ROOT / "scripts" / "dev" / "as-tester"), *args] if as_tester else ["gh", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        pytest.fail(f"GitHub call failed (not a pass): {' '.join(args[:3])}: {proc.stderr.strip()[:300]}", pytrace=False)
    return proc.stdout


def api(path: str, *fields: str, method: str = "GET", as_tester: bool = False) -> Any:
    args = ["api", "-X", method, path]
    for f in fields:
        args += ["-f", f]
    out = gh(args, as_tester=as_tester)
    return json.loads(out) if out.strip() else None


def poll(check: Callable[[], T | None], what: str, timeout: int = RUN_TIMEOUT) -> T:
    """Call `check` until it returns something other than None; time out as a failure, never a pass."""
    deadline = time.monotonic() + timeout
    while True:
        value = check()
        if value is not None:
            return value
        if time.monotonic() > deadline:
            pytest.fail(f"timed out after {timeout}s waiting for {what} (not a pass)", pytrace=False)
        time.sleep(POLL_INTERVAL)


def comment(number: int, body: str, as_tester: bool = False) -> dict[str, Any]:
    """Post a comment; returns its id, created_at and author."""
    c = api(f"repos/{REPO}/issues/{number}/comments", f"body={body}", method="POST", as_tester=as_tester)
    return {"id": c["id"], "created_at": c["created_at"], "user": c["user"]["login"]}


def run_for(cmt: dict[str, Any], title: str) -> int:
    """ID of the issue_comment run of the caller workflow created at or after the comment, for this item."""

    def find() -> int | None:
        runs = api(f"repos/{REPO}/actions/runs?event=issue_comment&created=%3E%3D{cmt['created_at']}&per_page=50")
        hits = [
            r for r in runs["workflow_runs"]
            if r["name"] == WORKFLOW and r["display_title"] == title and r["created_at"] >= cmt["created_at"]
        ]
        return min(hits, key=lambda r: (r["created_at"], r["id"]))["id"] if hits else None

    return poll(find, f"the issue_comment run for comment {cmt['id']}")


def dispatch(ref: str = "main") -> int:
    """Start the caller workflow by workflow_dispatch on `ref`; returns the new run's ID."""
    wf = next(w for w in api(f"repos/{REPO}/actions/workflows")["workflows"] if w["name"] == WORKFLOW)
    out = gh(["api", "-X", "POST", f"repos/{REPO}/actions/workflows/{wf['id']}/dispatches",
              "-f", f"ref={ref}", "-F", "return_run_details=true"])
    return json.loads(out)["workflow_run_id"]


def completed(run_id: int) -> dict[str, Any]:
    def done() -> dict[str, Any] | None:
        run = api(f"repos/{REPO}/actions/runs/{run_id}")
        return run if run["status"] == "completed" else None

    return poll(done, f"run {run_id} to complete")


def jobs(run_id: int) -> dict[str, str]:
    """Job name -> conclusion, e.g. {'commands / agent': 'skipped'}."""
    data = api(f"repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100")
    return {j["name"]: j["conclusion"] for j in data["jobs"]}


def bot_pings_after(number: int, comment_id: int) -> list[dict[str, Any]]:
    out = gh(["api", "--paginate", f"repos/{REPO}/issues/{number}/comments?per_page=100", "--jq", ".[]"])
    comments = [json.loads(line) for line in out.splitlines() if line.strip()]
    return [
        c for c in comments
        if c["id"] > comment_id and c["user"]["login"] == BOT and PING_MARKER in (c["body"] or "")
    ]
