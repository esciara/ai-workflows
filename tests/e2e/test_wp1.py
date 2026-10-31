"""WP1 acceptance test. Done when: `/ping` from a maintainer gets a reply; from a non-maintainer is ignored; all labels exist.

Runs against the playground (AIWF_E2E=1), whose caller must call commands.yml at the ref under test.
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


def ping_as_maintainer(item: dict) -> None:
    cmt = pg.comment(item["number"], "/ping")
    run_id = pg.run_for(cmt, item["title"])
    run = pg.completed(run_id)
    print(f"maintainer /ping on #{item['number']}: run {run_id} {run['html_url']} -> {run['conclusion']}")
    assert run["conclusion"] == "success", pg.jobs(run_id)
    jobs = pg.jobs(run_id)
    assert jobs.get("commands / agent") == "success" and jobs.get("commands / publish") == "success", jobs
    replies = pg.bot_pings_after(item["number"], cmt["id"])
    assert len(replies) == 1, f"expected exactly one ping reply after comment {cmt['id']}, got {len(replies)}"
    print(f"reply: {replies[0]['html_url']}")


def test_maintainer_ping_on_issue_gets_one_reply(fixture_issue):
    ping_as_maintainer(fixture_issue)


def test_maintainer_ping_on_pr_gets_one_reply(throwaway_pr):
    ping_as_maintainer(throwaway_pr)


def test_non_maintainer_ping_is_ignored(fixture_issue):
    if not os.environ.get("AI_WORKFLOWS_TESTER_APP_ID"):
        pytest.fail("AI_WORKFLOWS_TESTER_APP_ID is not set; cannot post as the tester App (not a pass)", pytrace=False)
    cmt = pg.comment(fixture_issue["number"], "/ping", as_tester=True)
    assert cmt["user"].endswith("[bot]") and cmt["user"] != pg.BOT, cmt
    run_id = pg.run_for(cmt, fixture_issue["title"])
    run = pg.completed(run_id)
    jobs = pg.jobs(run_id)
    print(f"tester /ping by {cmt['user']}: run {run_id} {run['html_url']} -> {run['conclusion']}, jobs {jobs}")
    assert jobs.get("commands / parse") == "success", jobs  # the command was seen and refused, not crashed
    assert jobs.get("commands / agent") == "skipped", jobs
    assert jobs.get("commands / publish") == "skipped", jobs
    # The wait window is the whole run: publish, the only job that replies, is skipped and the run is over.
    assert pg.bot_pings_after(fixture_issue["number"], cmt["id"]) == []


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
