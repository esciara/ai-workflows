"""Workflow A e2e helpers shared by test_wp2, test_wp14 and test_wp15 (moved out of test_wp2.py)."""

from __future__ import annotations

import json
import re

import playground as pg

E2E_WORKFLOW = pg.E2E_WORKFLOW  # the held slot's playground caller, caller-e2e-<n>.yml (ADR-0056)
MARKER = "<!-- ai-review:summary v1 -->"  # the spec's hidden marker (review comment template)
STATE_RE = re.compile(r"<!-- ai-review:state (\{.*?\}) -->", re.S)
VERDICTS = {  # verdict label -> heading of the review comment template
    "ai-review: merge": "## AI review — ✅ Merge",
    "ai-review: changes-requested": "## AI review — ❌ Changes requested",
    "ai-review: human-review": "## AI review — 👀 Human review needed",
}
PENDING = "ai-review: pending"
REVIEW_TIMEOUT = 1800  # CI wait + 4 passes + verify, on a cold runner


def review_run(sha: str, after: str) -> dict:
    """The completed pull_request run of the e2e caller for head `sha`, created at or after `after`."""

    def find() -> int | None:
        runs = pg.api(f"repos/{pg.REPO}/actions/runs?event=pull_request&head_sha={sha}&per_page=50")["workflow_runs"]
        hits = [r for r in runs if r["name"] == E2E_WORKFLOW and r["created_at"] >= after]
        return min(hits, key=lambda r: (r["created_at"], r["id"]))["id"] if hits else None

    run_id = pg.poll(find, f"the {E2E_WORKFLOW} pull_request run for {sha[:7]}", timeout=REVIEW_TIMEOUT)

    def done() -> dict | None:
        run = pg.api(f"repos/{pg.REPO}/actions/runs/{run_id}")
        return run if run["status"] == "completed" else None

    run = pg.poll(done, f"run {run_id} to complete", timeout=REVIEW_TIMEOUT)
    jobs = pg.jobs(run_id)
    print(f"review of {sha[:7]}: run {run_id} {run['html_url']} -> {run['conclusion']}, jobs {jobs}")
    assert run["conclusion"] == "success", jobs
    assert jobs.get("review / publish") == "success", jobs
    return run


def bot_comments(number: int) -> list[dict]:
    out = pg.gh(["api", "--paginate", f"repos/{pg.REPO}/issues/{number}/comments?per_page=100", "--jq", ".[]"])
    return [c for c in (json.loads(line) for line in out.splitlines() if line.strip()) if c["user"]["login"] == pg.BOT]


def labels(number: int) -> set[str]:
    return {lb["name"] for lb in pg.api(f"repos/{pg.REPO}/issues/{number}/labels?per_page=100")}


def head_sha(number: int) -> str:
    return pg.api(f"repos/{pg.REPO}/pulls/{number}")["head"]["sha"]


def check_review(number: int, sha: str, target: str) -> dict:
    """Exactly one bot comment on the PR (the summary, with the marker) and exactly one verdict label; returns it."""
    comments = bot_comments(number)
    assert len(comments) == 1, f"expected exactly one bot comment on #{number}, got {[c['html_url'] for c in comments]}"
    summary = comments[0]
    body = summary["body"] or ""
    assert body.startswith(MARKER), f"bot comment {summary['html_url']} lacks the summary marker"
    have = labels(number)
    verdicts = have & set(VERDICTS)
    assert len(verdicts) == 1, f"expected exactly one verdict label on #{number}, got {sorted(have)}"
    assert PENDING not in have, f"`{PENDING}` still set on #{number}: {sorted(have)}"
    (verdict,) = verdicts
    assert VERDICTS[verdict] in body, f"comment heading does not match label {verdict!r}"
    assert f"**Commit reviewed:** {sha[:7]}" in body, f"comment does not name the reviewed commit {sha[:7]}"
    m = STATE_RE.search(body)
    assert m, "comment has no state block"
    state = json.loads(m.group(1))
    assert state["sha"] == sha and state["verdict"] == verdict, state
    assert state["aiwf_sha"] == target, f"reviewed by ai-workflows@{state['aiwf_sha']}, not e2e-target {target}"
    print(f"#{number} @ {sha[:7]}: {verdict}, comment {summary['html_url']} (updated {summary['updated_at']})")
    return {"id": summary["id"], "updated_at": summary["updated_at"], "body": body, "verdict": verdict}
