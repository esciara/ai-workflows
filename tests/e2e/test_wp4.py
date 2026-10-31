"""WP4 acceptance test. Done when: a fork PR is not reviewed until a maintainer comments `/review`.

Runs against the playground (AIWF_E2E=1) with the e2e slot (AIWF_E2E_SLOT=1): the PR comes from the outsider fork
(pg.FORK), opened by the tester App, and is labelled `e2e-target` right after creation, so its later events (the
second push, the comments) go to caller-e2e.yml, which runs review.yml@e2e-target = the commit under test (ADR-0028).

1. A fork push (`synchronize`, after the label) starts no review: the run's gate lets every review job skip (or the
   run waits for a first-time contributor's approval, which is not a review either); no verdict label, no summary.
2. `/review` from a non-maintainer (the tester App) is refused by the gate: still no label, no summary.
3. `/review` from the maintainer reviews the fork's head, read as text: one summary comment whose reviewed commit is
   the fork head, exactly one verdict label, `review / publish` succeeds.
"""

from __future__ import annotations

import json
import re
import time

import playground as pg

E2E_WORKFLOW = "AI workflows (e2e)"  # the playground's caller-e2e.yml
MARKER = "<!-- ai-review:summary v1 -->"
STATE_RE = re.compile(r"<!-- ai-review:state (\{.*?\}) -->", re.S)
VERDICTS = {"ai-review: merge", "ai-review: changes-requested", "ai-review: human-review"}
REVIEW_JOBS = ("review / start", "review / context", "review / publish")
REVIEW_TIMEOUT = 1800  # CI wait + 4 passes + verify, on a cold runner

SEED = "src/minicart/bulk.py"
SEED_V1 = '''"""Bulk pricing (e2e fork PR seed)."""

from decimal import Decimal


def bulk_price(unit: Decimal, qty: int, percent_off: Decimal) -> Decimal:
    """Total for `qty` units at `unit` each, with `percent_off` % off."""
    return unit * qty * (1 - percent_off)
'''
SEED_V2 = SEED_V1.replace("(e2e fork PR seed)", "(e2e fork PR seed, second push)")


def labels(number: int) -> set[str]:
    return {lb["name"] for lb in pg.api(f"repos/{pg.REPO}/issues/{number}/labels?per_page=100")}


def summaries(number: int) -> list[dict]:
    out = pg.gh(["api", "--paginate", f"repos/{pg.REPO}/issues/{number}/comments?per_page=100", "--jq", ".[]"])
    comments = [json.loads(line) for line in out.splitlines() if line.strip()]
    return [c for c in comments if c["user"]["login"] == pg.BOT and (c["body"] or "").startswith(MARKER)]


def head_sha(number: int) -> str:
    return pg.api(f"repos/{pg.REPO}/pulls/{number}")["head"]["sha"]


def assert_not_reviewed(number: int, when: str) -> None:
    got = labels(number)
    assert not {lb for lb in got if lb.startswith("ai-review:")}, f"{when}: review labels {sorted(got)} on fork PR"
    assert not summaries(number), f"{when}: a review summary was posted on fork PR #{number}"


def finished(run_id: int) -> dict:
    def done() -> dict | None:
        run = pg.api(f"repos/{pg.REPO}/actions/runs/{run_id}")
        return run if run["status"] in ("completed", "action_required") or run["conclusion"] == "action_required" \
            else None

    return pg.poll(done, f"run {run_id} to finish", timeout=REVIEW_TIMEOUT)


def push_run(sha: str, after: str) -> dict:
    """The e2e caller's pull_request run for fork head `sha`, finished (completed, or held for approval)."""

    def find() -> int | None:
        runs = pg.api(f"repos/{pg.REPO}/actions/runs?event=pull_request&head_sha={sha}&per_page=50")["workflow_runs"]
        hits = [r for r in runs if r["name"] == E2E_WORKFLOW and r["created_at"] >= after]
        return min(hits, key=lambda r: (r["created_at"], r["id"]))["id"] if hits else None

    return finished(pg.poll(find, f"the {E2E_WORKFLOW} pull_request run for {sha[:7]}"))


def comment_run(cmt: dict, title: str) -> tuple[dict, dict[str, str]]:
    """The e2e caller's issue_comment run for this comment, completed, with its jobs."""

    def find() -> int | None:
        runs = pg.api(f"repos/{pg.REPO}/actions/runs?event=issue_comment&created=%3E%3D{cmt['created_at']}"
                      "&per_page=50")["workflow_runs"]
        hits = [r for r in runs if r["name"] == E2E_WORKFLOW and r["display_title"] == title
                and r["created_at"] >= cmt["created_at"]]
        return min(hits, key=lambda r: (r["created_at"], r["id"]))["id"] if hits else None

    run = finished(pg.poll(find, f"the {E2E_WORKFLOW} issue_comment run for comment {cmt['id']}"))
    jobs = pg.jobs(run["id"])
    print(f"/review by {cmt['user']}: run {run['id']} {run['html_url']} -> {run['conclusion']}, jobs {jobs}")
    return run, jobs


def test_fork_pr_is_not_reviewed_until_a_maintainer_comments_review(e2e_target):
    with pg.fork_pr("[e2e] WP4 bulk pricing from a fork", [(SEED, SEED_V1)], wp="wp4", slug="fork") as pr:
        number, title = pr["number"], pr["title"]
        assert pg.api(f"repos/{pg.REPO}/pulls/{number}")["head"]["repo"]["full_name"] == pg.FORK

        # 1. A fork push, routed to the e2e caller by the label: no review.
        pushed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 5))
        sha2 = pg.fork_put(SEED, pr["branch"], SEED_V2, "test: e2e fork PR second push")
        pg.poll(lambda: True if head_sha(number) == sha2 else None, f"PR #{number} head to move to {sha2[:7]}",
                timeout=300)
        run = push_run(sha2, after=pushed_at)
        print(f"fork push {sha2[:7]}: run {run['id']} {run['html_url']} -> {run['status']}/{run['conclusion']}")
        if run["conclusion"] != "action_required":  # held for approval = nothing ran
            jobs = pg.jobs(run["id"])
            print("jobs:", jobs)
            assert run["conclusion"] == "success", jobs
            assert jobs.get("review / gate") == "success", jobs
            assert all(jobs.get(j) in (None, "skipped") for j in REVIEW_JOBS), jobs
        assert_not_reviewed(number, "after a fork push")

        # 2. `/review` from a non-maintainer: refused.
        run, jobs = comment_run(pg.comment(number, "/review", as_tester=True), title)
        assert run["conclusion"] == "success", jobs
        assert jobs.get("review / gate") == "success", jobs
        assert all(jobs.get(j) in (None, "skipped") for j in REVIEW_JOBS), jobs
        assert_not_reviewed(number, "after a non-maintainer's /review")

        # 3. `/review` from the maintainer: reviewed, at the fork's head.
        run, jobs = comment_run(pg.comment(number, "/review"), title)
        assert run["conclusion"] == "success", jobs
        assert jobs.get("review / publish") == "success", jobs
        own = summaries(number)
        assert len(own) == 1, f"expected one summary comment, got {[c['html_url'] for c in own]}"
        body = own[0]["body"]
        print(body)
        state = json.loads(STATE_RE.search(body).group(1))
        assert state["sha"] == sha2 and state["aiwf_sha"] == e2e_target, state
        assert f"**Commit reviewed:** {sha2[:7]}" in body
        verdicts = labels(number) & VERDICTS
        assert len(verdicts) == 1, f"expected exactly one verdict label, got {sorted(labels(number))}"
