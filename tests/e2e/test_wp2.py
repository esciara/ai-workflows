"""WP2 acceptance test. Done when: a dummy PR gets one comment + one label; a new push updates the same comment.

Runs against the playground (AIWF_E2E=1) with the e2e slot (AIWF_E2E_SLOT=1): the PR comes from an `e2e/` branch, so
caller-e2e.yml reviews it with review.yml@e2e-target, which the slot points at the commit under test (ADR-0028/0029).
"""

from __future__ import annotations

import base64
import json
import re
import time

import playground as pg

E2E_WORKFLOW = "AI workflows (e2e)"  # the playground's caller-e2e.yml
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


def test_dummy_pr_gets_one_comment_and_one_label_and_a_push_updates_the_same_comment(e2e_target):
    with pg.throwaway_pr("[e2e] WP2 core review", e2e=True, wp="wp2", slug="core-review") as pr:
        number = pr["number"]
        sha1 = head_sha(number)
        review_run(sha1, after="1970-01-01T00:00:00Z")  # the branch and its SHA are new: any run for it is ours
        first = check_review(number, sha1, e2e_target)

        pushed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 5))
        content = base64.b64encode(f"second push {time.time_ns()}\n".encode()).decode()
        put = pg.api(f"repos/{pg.REPO}/contents/e2e/{pr['branch'].replace('/', '-')}-2.md",
                     "message=test: e2e second push", f"content={content}", f"branch={pr['branch']}", method="PUT")
        sha2 = put["commit"]["sha"]  # the pulls API can serve a stale head right after the PUT
        assert sha2 != sha1, "the push did not create a new commit"
        pg.poll(lambda: True if head_sha(number) == sha2 else None, f"PR #{number} head to move to {sha2[:7]}",
                timeout=300)
        review_run(sha2, after=pushed_at)
        second = check_review(number, sha2, e2e_target)

        assert second["id"] == first["id"], f"push created a new summary comment ({first['id']} -> {second['id']})"
        assert second["updated_at"] > first["updated_at"], "summary comment was not updated after the push"
        assert second["body"] != first["body"], "summary comment body unchanged after the push"
        assert "**Since last run:**" in second["body"], "rerun does not report findings since the last run"
