"""WP12a acceptance test. Done when: `ai: off` stops a run; a forced crash gives `ai: error` + comment.

Runs against the playground (AIWF_E2E=1) with the e2e slot (AIWF_E2E_SLOT=1): every item routes to caller-e2e.yml
(an `e2e/` PR branch, or the `e2e-target` label), which runs the workflows at the commit under test (ADR-0043).

1. A draft PR with `ai: off` marked ready for review starts no review: config runs, the config gate skips every
   review job; no summary comment, no verdict label. (No cancel of runs in flight: ADR-0045, decision 3.)
2. An issue opened with `ai: off` gets no triage, and a maintainer's `/ping` on it gets no reply (config gate).
3. A forced crash (label `e2e-crash`, honoured only with the playground's e2e config, ADR-0045), on an issue (triage)
   and on a PR (review, started by a maintainer's `/review`): the run fails, the item gets `ai: error` and exactly one
   error comment linking that run; nothing retries it (run attempt stays 1, still one error comment after a grace).

The pre-write live-label re-check (a label added between the gate and a write) is unit-tested (tests/test_guard.py).
"""

from __future__ import annotations

import base64
import contextlib
import json
import time
from typing import Iterator

import pytest

import playground as pg

E2E_WORKFLOW = "AI workflows (e2e)"  # the playground's caller-e2e.yml
OFF = "ai: off"
ERROR = "ai: error"
CRASH = "e2e-crash"
PENDING = "ai-review: pending"
ERROR_MARKER = "<!-- ai-workflows:error -->"
REVIEW_MARKER = "<!-- ai-review:summary v1 -->"
TRIAGE_MARKER = "<!-- ai-workflows:triage -->"
VERDICTS = {"ai-review: merge", "ai-review: changes-requested", "ai-review: human-review"}
GRACE = 90  # seconds to wait for a retry that must not come
BUG = ("Steps:\n\n```python\nfrom minicart.cart import Cart\ncart = Cart()\ncart.add('A', '15.00')\n"
       "cart.remove('A')\nprint(cart.total())\n```\n\nExpected: 0.00. Actual: KeyError. minicart from main.")


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 5))


def labels(number: int) -> set[str]:
    return {lb["name"] for lb in pg.api(f"repos/{pg.REPO}/issues/{number}/labels?per_page=100")}


def bot_comments(number: int, marker: str) -> list[dict]:
    out = pg.gh(["api", "--paginate", f"repos/{pg.REPO}/issues/{number}/comments?per_page=100", "--jq", ".[]"])
    comments = [json.loads(line) for line in out.splitlines() if line.strip()]
    return [c for c in comments if c["user"]["login"] == pg.BOT and marker in (c["body"] or "")]


def runs(event: str, title: str, after: str) -> list[dict]:
    """The e2e caller's runs for this item (by display title) and event, created at or after `after`."""
    got = pg.api(f"repos/{pg.REPO}/actions/runs?event={event}&created=%3E%3D{after}&per_page=100")["workflow_runs"]
    return [r for r in got if r["name"] == E2E_WORKFLOW and r["display_title"] == title and r["created_at"] >= after]


def with_job(event: str, title: str, after: str, job: str) -> dict:
    """The first run (event, item) since `after` that has a job named `job`, once that job has a conclusion."""

    def find() -> dict | None:
        for r in sorted(runs(event, title, after), key=lambda r: (r["created_at"], r["id"])):
            if pg.jobs(r["id"]).get(job):
                return r
        return None

    return pg.poll(find, f"a {event} run of {title!r} whose job {job!r} has finished")


def settled(event: str, title: str, after: str) -> list[dict]:
    """All runs (event, item) since `after`, once at least one exists and every one has completed."""

    def done() -> list[dict] | None:
        got = runs(event, title, after)
        return got if got and all(r["status"] == "completed" for r in got) else None

    return pg.poll(done, f"the {event} runs of {title!r} to complete")


def add_label(number: int, name: str) -> None:
    pg.api(f"repos/{pg.REPO}/issues/{number}/labels", f"labels[]={name}", method="POST")


def put_file(branch: str, path: str) -> None:
    pg.api(f"repos/{pg.REPO}/contents/{path}", f"message=test: e2e WP12a {path}",
           f"content={base64.b64encode(path.encode()).decode()}", f"branch={branch}", method="PUT")


@pytest.fixture
def tag(testrun_uid: str) -> str:
    return testrun_uid[:8]


@pytest.fixture
def issue_factory(tag: str) -> Iterator:
    """Opens test issues routed to the e2e caller, labels set at creation; closes them as not planned at teardown."""
    opened: list[int] = []

    def make(what: str, extra: list[str]) -> dict:
        pg.ensure_label()
        want = [pg.FIXTURE_LABEL, pg.E2E_LABEL, *extra]
        got = pg.api(f"repos/{pg.REPO}/issues", f"title=[e2e] WP12a {what} {tag}", f"body={BUG}",
                     *[f"labels[]={lb}" for lb in want], method="POST")
        opened.append(got["number"])
        assert set(want) <= {lb["name"] for lb in got["labels"]}, got["labels"]
        return {"number": got["number"], "title": got["title"]}

    yield make
    for n in opened:
        pg.api(f"repos/{pg.REPO}/issues/{n}", "state=closed", "state_reason=not_planned", method="PATCH")


@contextlib.contextmanager
def draft_pr(title: str, extra: list[str]) -> Iterator[dict]:
    """A draft e2e PR (its `opened` event starts no review), labelled right after creation; closed on exit."""
    branch = pg.pr_branch(e2e=True, wp="wp12", slug="crash")
    base = pg.api(f"repos/{pg.REPO}")["default_branch"]
    sha = pg.api(f"repos/{pg.REPO}/git/ref/heads/{base}")["object"]["sha"]
    pg.api(f"repos/{pg.REPO}/git/refs", f"ref=refs/heads/{branch}", f"sha={sha}", method="POST")
    pr = None
    try:
        put_file(branch, f"e2e/{branch.replace('/', '-')}.md")
        title = f"{title} ({branch})"
        pr = json.loads(pg.gh(["api", "-X", "POST", f"repos/{pg.REPO}/pulls", "-f", f"title={title}", "-f",
                               f"head={branch}", "-f", f"base={base}", "-f", "body=Throwaway e2e PR (WP12a).",
                               "-F", "draft=true"], as_agent=True))
        pg.ensure_label()
        pg.api(f"repos/{pg.REPO}/issues/{pr['number']}/labels",
               *[f"labels[]={lb}" for lb in (pg.FIXTURE_LABEL, pg.E2E_LABEL, *extra)], method="POST")
        yield {"number": pr["number"], "title": title, "branch": branch}
    finally:
        pg.api(f"repos/{pg.REPO}/git/refs/heads/{branch}", method="DELETE")
        if pr and pg.api(f"repos/{pg.REPO}/pulls/{pr['number']}")["state"] == "open":
            pg.api(f"repos/{pg.REPO}/pulls/{pr['number']}", "state=closed", method="PATCH")


def assert_crash_reported(number: int, run: dict, crashed: str, failed: str) -> None:
    run = pg.completed(run["id"])
    jobs = pg.jobs(run["id"])
    print(f"crash run {run['id']} {run['html_url']} -> {run['conclusion']}, jobs {jobs}")
    assert run["conclusion"] == "failure", jobs
    assert jobs.get(crashed) == "failure", jobs
    assert jobs.get(failed) == "success", jobs
    got = labels(number)
    assert ERROR in got and PENDING not in got, sorted(got)
    errors = bot_comments(number, ERROR_MARKER)
    assert len(errors) == 1, [c["html_url"] for c in errors]
    print(errors[0]["body"])
    assert run["html_url"] in errors[0]["body"]
    time.sleep(GRACE)  # no retry: the run is not re-attempted and no second error comment appears
    assert pg.api(f"repos/{pg.REPO}/actions/runs/{run['id']}")["run_attempt"] == 1
    assert len(bot_comments(number, ERROR_MARKER)) == 1


def test_ai_off_pr_marked_ready_gets_no_review(e2e_target):
    pg.ensure_label(OFF, "000000", "Kill switch: no AI run on this issue or PR")
    with draft_pr("[e2e] WP12a ai: off on a PR", [OFF]) as pr:
        number, title = pr["number"], pr["title"]
        node = pg.api(f"repos/{pg.REPO}/pulls/{number}")["node_id"]
        t_ready = now()
        pg.gh(["api", "graphql", "-f", f'query=mutation {{ markPullRequestReadyForReview(input: {{pullRequestId: "{node}"}}) '
               "{ pullRequest { isDraft } } }"], as_agent=True)
        ready = pg.completed(with_job("pull_request", title, t_ready, "config / load")["id"])
        jobs = pg.jobs(ready["id"])
        print(f"ready run {ready['id']} {ready['html_url']} -> {ready['conclusion']}, jobs {jobs}")
        assert ready["conclusion"] == "success" and jobs["config / load"] == "success", jobs
        assert all(c == "skipped" for j, c in jobs.items() if j.startswith("review")), jobs
        assert not bot_comments(number, REVIEW_MARKER)
        assert not labels(number) & VERDICTS


def test_ai_off_issue_gets_no_triage_and_no_command_reply(e2e_target, issue_factory):
    pg.ensure_label(OFF, "000000", "Kill switch: no AI run on this issue or PR")
    t0 = now()
    issue = issue_factory("ai: off issue", [OFF])
    number, title = issue["number"], issue["title"]
    for r in settled("issues", title, t0):
        print(f"issues run {r['id']} {r['html_url']} -> {r['conclusion']}, jobs {pg.jobs(r['id'])}")
    assert not bot_comments(number, TRIAGE_MARKER), "triaged despite ai: off"
    assert not {lb for lb in labels(number) if lb.startswith(("type:", "triage:"))}, sorted(labels(number))

    cmt = pg.comment(number, "/ping")
    run = pg.completed(with_job("issue_comment", title, cmt["created_at"], "config / load")["id"])
    jobs = pg.jobs(run["id"])
    print(f"/ping run {run['id']} {run['html_url']} -> {run['conclusion']}, jobs {jobs}")
    assert run["conclusion"] == "success" and jobs["config / load"] == "success", jobs
    assert all(c == "skipped" for j, c in jobs.items() if j.startswith("commands")), jobs
    assert not pg.bot_pings_after(number, cmt["id"]), "replied to /ping despite ai: off"


def test_forced_crash_on_triage_gives_ai_error_and_one_comment(e2e_target, issue_factory):
    pg.ensure_label(CRASH, "d93f0b", "e2e only: forces a crash (honoured with the playground e2e config only)")
    t0 = now()
    issue = issue_factory("forced crash", [CRASH])
    run = with_job("issues", issue["title"], t0, "triage / failed")
    assert_crash_reported(issue["number"], run, "triage / context", "triage / failed")
    assert not bot_comments(issue["number"], TRIAGE_MARKER)


def test_forced_crash_on_review_gives_ai_error_and_one_comment(e2e_target):
    pg.ensure_label(CRASH, "d93f0b", "e2e only: forces a crash (honoured with the playground e2e config only)")
    with draft_pr("[e2e] WP12a forced crash on review", [CRASH]) as pr:
        cmt = pg.comment(pr["number"], "/review")
        run = with_job("issue_comment", pr["title"], cmt["created_at"], "review / failed")
        assert_crash_reported(pr["number"], run, "review / context", "review / failed")
        assert not bot_comments(pr["number"], REVIEW_MARKER)
        assert not labels(pr["number"]) & VERDICTS
