"""Helpers for end-to-end acceptance tests against the playground repo (network, real GitHub)."""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar

import pytest

ROOT = Path(__file__).resolve().parents[2]
REPO = os.environ.get("AIWF_E2E_REPO", "esciara/ai-workflows-playground")
WORKFLOW = "AI workflows"  # name of the caller workflow in the target repo
BOT = "github-actions[bot]"
PING_MARKER = "<!-- ai-workflows:ping -->"
FIXTURE_LABEL = "test-fixture"
E2E_LABEL = "e2e-target"  # routes an item to the playground's caller-e2e.yml (@e2e-target) instead of the normal one
RUN_TIMEOUT = int(os.environ.get("AIWF_E2E_TIMEOUT", "600"))
POLL_INTERVAL = int(os.environ.get("AIWF_E2E_POLL", "5"))

T = TypeVar("T")


def gh(args: list[str], as_tester: bool = False, as_agent: bool = False, as_maintainer: bool = False) -> str:
    """Run gh: reads with the local gh login; writes as the agent App (ADR-0031), the tester App, or the maintainer
    through scripts/dev/as-maintainer (comments, reviews, dispatch on the playground only). API failures fail the test."""
    wrapper = "as-tester" if as_tester else "as-maintainer" if as_maintainer else "as-agent" if as_agent else None
    cmd = [str(ROOT / "scripts" / "dev" / wrapper), *args] if wrapper else ["gh", *args]
    if wrapper == "as-agent":
        cmd.insert(1, "gh")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        pytest.fail(f"GitHub call failed (not a pass): {' '.join(args[:3])}: {proc.stderr.strip()[:300]}", pytrace=False)
    return proc.stdout


def api(path: str, *fields: str, method: str = "GET", as_tester: bool = False, as_maintainer: bool = False) -> Any:
    """GETs read with the local gh login; other methods run as the tester, the maintainer, or else the agent App."""
    args = ["api", "-X", method, path]
    for f in fields:
        args += ["-f", f]
    out = gh(args, as_tester=as_tester, as_maintainer=as_maintainer, as_agent=method != "GET")
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
    """Post a comment as the maintainer (or the tester); returns its id, created_at and author."""
    c = api(f"repos/{REPO}/issues/{number}/comments", f"body={body}", method="POST", as_tester=as_tester,
            as_maintainer=not as_tester)
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
              "-f", f"ref={ref}", "-F", "return_run_details=true"], as_maintainer=True)  # the App has no actions write
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


def ensure_label(name: str = E2E_LABEL, color: str = "5319e7", description: str = "e2e: runs ai-workflows@e2e-target") -> None:
    if not any(lb["name"] == name for lb in api(f"repos/{REPO}/labels?per_page=100")):
        api(f"repos/{REPO}/labels", f"name={name}", f"color={color}", f"description={description}", method="POST")


def _labels(e2e: bool) -> list[str]:
    if e2e:
        ensure_label()
    return [FIXTURE_LABEL, E2E_LABEL] if e2e else [FIXTURE_LABEL]


def open_issue(title: str, body: str, *, e2e: bool, as_tester: bool = False) -> dict[str, Any]:
    """New issue, labels set at creation (so the `opened` event already carries `e2e-target` when `e2e`)."""
    want = _labels(e2e)
    issue = api(f"repos/{REPO}/issues", f"title={title}", f"body={body}", *[f"labels[]={lb}" for lb in want],
                method="POST", as_tester=as_tester)
    got = {lb["name"] for lb in issue["labels"]}
    if not set(want) <= got:  # GitHub silently drops labels an author may not set
        pytest.fail(f"issue #{issue['number']} created without labels {sorted(set(want) - got)} (not a pass)", pytrace=False)
    return {"number": issue["number"], "title": issue["title"]}


def reusable_issue(title: str, body: str, *, e2e: bool) -> dict[str, Any]:
    """The open test-fixture issue with this exact title, created once and reused (never deleted)."""
    found = api(f"repos/{REPO}/issues?labels={FIXTURE_LABEL}&state=open&per_page=100")
    for issue in found:
        if issue["title"] == title and "pull_request" not in issue:
            return {"number": issue["number"], "title": issue["title"]}
    return open_issue(title, body, e2e=e2e)


def pr_branch(*, e2e: bool, wp: str = "", slug: str = "") -> str:
    """Unique head branch for a test PR. e2e PRs use `e2e/<wp>-<slug>-<ns>`: the playground routes PRs whose head ref
    starts with `e2e/` to caller-e2e.yml from the first `opened` event on (labels cannot be set at creation)."""
    if not e2e:
        return f"test-pr-{time.time_ns()}"  # never `e2e/`: the normal caller handles it
    if not re.fullmatch(r"wp\d+", wp) or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
        raise ValueError(f"e2e PR branch needs wp like 'wp2' and a lowercase slug, got {wp!r}, {slug!r}")
    return f"e2e/{wp}-{slug}-{time.time_ns()}"


@contextlib.contextmanager
def throwaway_pr(title: str, *, e2e: bool, wp: str = "", slug: str = "", base: str | None = None) -> Iterator[dict[str, Any]]:
    """A test-fixture PR on its own branch from `base` (default branch if None); branch deleted, PR closed on exit.

    e2e PRs come from an `e2e/<wp>-<slug>-…` branch, so every PR event routes to the e2e caller, `opened` included.
    Labels (`test-fixture`, plus `e2e-target` when e2e) are added right after creation, since the pulls API cannot
    set them; comment events on the PR carry no head ref and route by that label.
    """
    branch = pr_branch(e2e=e2e, wp=wp, slug=slug)
    base = base or api(f"repos/{REPO}")["default_branch"]
    sha = api(f"repos/{REPO}/git/ref/heads/{base}")["object"]["sha"]
    api(f"repos/{REPO}/git/refs", f"ref=refs/heads/{branch}", f"sha={sha}", method="POST")
    pr = None
    try:
        api(f"repos/{REPO}/contents/e2e/{branch.replace('/', '-')}.md", f"message=test: e2e throwaway {branch}",
            "content=dGhyb3dhd2F5Cg==", f"branch={branch}", method="PUT")  # "throwaway\n"
        title = f"{title} ({branch})"
        pr = api(f"repos/{REPO}/pulls", f"title={title}", f"head={branch}", f"base={base}",
                 "body=Throwaway e2e PR from esciara/ai-workflows tests; closed by its teardown.", method="POST")
        api(f"repos/{REPO}/issues/{pr['number']}/labels", *[f"labels[]={lb}" for lb in _labels(e2e)], method="POST")
        yield {"number": pr["number"], "title": title, "branch": branch}
    finally:
        api(f"repos/{REPO}/git/refs/heads/{branch}", method="DELETE")
        if pr and api(f"repos/{REPO}/pulls/{pr['number']}")["state"] == "open":
            api(f"repos/{REPO}/pulls/{pr['number']}", "state=closed", method="PATCH")
