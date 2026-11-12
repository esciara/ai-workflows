"""WP1 acceptance test. Done when: a command from a maintainer is accepted, from a non-maintainer is refused; all
labels exist.

Runs against the playground (AIWF_E2E=1, AIWF_E2E_SLOT=1): command items are labelled `e2e-target`, so their comments
run the playground's caller-e2e.yml at the ref under test. config.yml parses each comment once (ADR-0005); review.yml
and triage.yml run only on the command they handle. Accepted = the command's first job runs; refused = config ran and
every job of the workflow the command belongs to was skipped.
"""

import json
import os

import pytest
import yaml

import playground as pg

LABELS_FILE = pg.ROOT / "schema" / "labels.yml"
# Every label the spec names (its Labels table, plus `triage: no-response`, `stale`, `keep-open` from B2 and
# `ai: error` from Failure modes), written out here so the test does not trust the build's own labels.yml.
SPEC_LABELS = {
    "type: bug", "type: feature", "type: question",
    "triage: needs-info", "triage: no-response", "triage: reproduced", "triage: awaiting-maintainer",
    "triage: needs-human", "triage: duplicate",
    "fix: declined", "fix: needs-maintainer", "ai-fix",
    "ai-review: pending", "ai-review: merge", "ai-review: changes-requested", "ai-review: human-review",
    "ai: off", "ai: error", "stale", "keep-open",
}
FIXTURE_TITLE = "[e2e] WP1 command fixture"


@pytest.fixture
def command_issue(request, e2e_target) -> dict:
    """A reusable e2e test-fixture issue per test (found by title, created once, never deleted): one per test, since
    the caller serialises runs per issue."""
    return pg.reusable_issue(f"{FIXTURE_TITLE} ({request.node.originalname})",
                             "Reusable fixture for tests/e2e/test_wp1.py in esciara/ai-workflows: slash commands are "
                             "posted here. Not a real report.", e2e=True)


@pytest.fixture
def command_pr(e2e_target):
    """A draft e2e PR (its own events start no review); branch deleted, PR closed on exit."""
    with pg.throwaway_pr("[e2e] WP1 command on a PR", e2e=True, wp="wp1", slug="command", draft=True) as pr:
        yield pr


def command_run(item: dict, body: str, as_tester: bool = False) -> tuple[dict, dict[str, str]]:
    if as_tester and not os.environ.get("AI_WORKFLOWS_TESTER_APP_ID"):
        pytest.fail("AI_WORKFLOWS_TESTER_APP_ID is not set; cannot post as the tester App (not a pass)", pytrace=False)
    cmt = pg.comment(item["number"], body, as_tester=as_tester)
    if as_tester:
        assert cmt["user"].endswith("[bot]") and cmt["user"] != pg.BOT, cmt
    run = pg.completed(pg.run_for(cmt, item["title"], pg.E2E_WORKFLOW))
    jobs = pg.jobs(run["id"])
    print(f"{body} by {cmt['user']} on #{item['number']}: run {run['id']} {run['html_url']} -> {run['conclusion']}, "
          f"jobs {jobs}")
    assert jobs.get("config / load") == "success", jobs  # the comment was parsed, not crashed
    return run, jobs


def ran(jobs: dict[str, str], workflow: str) -> dict[str, str]:
    return {j: c for j, c in jobs.items() if j.startswith(f"{workflow} / ")}


def test_maintainer_retriage_on_issue_is_accepted(command_issue):
    run, jobs = command_run(command_issue, "/retriage")
    assert run["conclusion"] == "success", jobs
    assert jobs.get("triage / context") == "success", jobs
    assert jobs.get("triage / publish") == "success", jobs


def test_maintainer_review_on_pr_is_accepted(command_pr):
    run, jobs = command_run(command_pr, "/review")
    assert run["conclusion"] == "success", jobs
    assert jobs.get("review / gate") == "success" and jobs.get("review / start") == "success", jobs
    assert jobs.get("review / publish") == "success", jobs


def test_non_maintainer_retriage_is_refused(command_issue):
    run, jobs = command_run(command_issue, "/retriage", as_tester=True)
    assert run["conclusion"] == "success", jobs
    triage = ran(jobs, "triage")
    assert triage and all(c == "skipped" for c in triage.values()), jobs


def test_non_maintainer_review_is_refused(command_pr):
    run, jobs = command_run(command_pr, "/review", as_tester=True)
    assert run["conclusion"] == "success", jobs
    review = ran(jobs, "review")
    assert review and all(c == "skipped" for c in review.values()), jobs


def test_all_spec_labels_exist_and_match_schema():
    # Labels sync runs only on workflow_dispatch and schedule (ADR-0023): run it, then check.
    run_id = pg.dispatch()
    run = pg.completed(run_id)
    print(f"labels sync dispatch: run {run_id} {run['html_url']} -> {run['conclusion']}")
    assert run["conclusion"] == "success", pg.jobs(run_id)
    assert pg.jobs(run_id).get("labels / sync") == "success", pg.jobs(run_id)
    wanted = {
        (str(l["name"]), str(l["color"]).lower(), str(l["description"]))
        for l in yaml.safe_load(LABELS_FILE.read_text())["labels"]
    }
    out = pg.gh(["api", "--paginate", f"repos/{pg.REPO}/labels?per_page=100", "--jq", ".[]"])
    repo = [json.loads(line) for line in out.splitlines() if line.strip()]
    names = {n for n, _, _ in wanted}
    have = {(l["name"], l["color"].lower(), l["description"] or "") for l in repo if l["name"] in names}
    print(f"{len(have)} of {len(wanted)} managed labels present and identical")
    assert have == wanted, {"missing or different": sorted(wanted - have), "unexpected": sorted(have - wanted)}
    missing_from_repo = SPEC_LABELS - {l["name"] for l in repo}
    assert not missing_from_repo, f"spec labels missing on {pg.REPO}: {sorted(missing_from_repo)}"
    assert SPEC_LABELS <= names, f"spec labels missing from {LABELS_FILE.name}: {sorted(SPEC_LABELS - names)}"
