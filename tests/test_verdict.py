"""`aiwf verdict`, the required check of the repo's Workflow A caller (ADR-0053, ADR-0055). Fake gh, no network."""

import json
import os
import shutil
import subprocess
import sys

import pytest

from aiwf import verdict

pytestmark = pytest.mark.skipif(not shutil.which("jq"), reason="jq missing")


def _st(state, description, creator="github-actions[bot]"):
    return {"context": "verdict", "state": state, "description": description, "creator": {"login": creator}}


def _run_verdict(tmp_path, event, review, reviews, labels, state="", current="none", author="app[bot]", statuses=None, post_rc=0):
    """Runs the verdict step with a fake gh. `statuses` (newest first) or `current` fill the head commit's statuses."""
    fake = tmp_path / "gh"
    posted = tmp_path / "posted"
    posted.unlink(missing_ok=True)
    if statuses is None:
        statuses = [] if current == "none" else [_st(current, "x")]
    statuses = [{"context": "other", "state": "failure", "description": "", "creator": {"login": "x"}}, *statuses]
    data = {"statuses": statuses, "reviews": reviews, "labels": [{"name": x} for x in labels]}
    for name, value in data.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
    fake.write_text(
        "#!/bin/bash\n"
        'q=.; prev=; for a in "$@"; do [ "$prev" = --jq ] && q=$a; prev=$a; done\n'
        'case "$*" in\n'
        f"  *-X\\ POST*statuses*) printf '%s\\n' \"$*\" >> {posted}; exit {post_rc} ;;\n"
        f"  *commits/*/statuses*) f={tmp_path}/statuses.json ;;\n"
        f"  *pulls/*/reviews*) f={tmp_path}/reviews.json ;;\n"
        f"  *issues/*/labels*) f={tmp_path}/labels.json ;;\n"
        "esac\n"
        'jq -r "$q" "$f"\n'
    )
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "REPO": "o/r", "PR": "1", "AUTHOR": author,
           "HEAD_SHA": "new4567890", "EVENT": event, "REVIEW": review, "REVIEW_STATE": state,
           "GITHUB_STEP_SUMMARY": str(tmp_path / "summary")}
    run = subprocess.run([sys.executable, "-m", "aiwf.cli", "verdict"], env=env, capture_output=True, text=True)
    _run_verdict.stdout = run.stdout
    return run.returncode, posted.read_text() if posted.exists() else ""


def _description(posted):
    return posted.split("description=", 1)[1].rstrip("\n")


def _rv(state="APPROVED", sha="new4567890", user="m", assoc="OWNER", body=""):
    return {"state": state, "commit_id": sha, "user": {"login": user}, "author_association": assoc, "body": body}


AI = _rv("COMMENTED", user="github-actions[bot]", assoc="NONE", body="Summary\n\n**Verdict:** risk tier high; no linked issue.\n")
PR, RV = "pull_request", "pull_request_review"


@pytest.mark.parametrize(
    "event, review, reviews, labels, state, status",
    [
        (PR, "success", [], ["ai-review: merge"], "", "success"),
        (PR, "success", [AI], ["ai-review: human-review"], "", "pending"),
        (PR, "success", [AI], ["ai-review: changes-requested"], "", "failure"),
        (PR, "success", [], [], "", "pending"),  # no label
        (PR, "failure", [], ["ai-review: merge"], "", "failure"),  # review errored
        (PR, "skipped", [], [], "", "pending"),  # review did not run
        (PR, "skipped", [_rv()], ["ai-review: human-review"], "", "success"),  # approval alone
        (RV, "skipped", [_rv()], ["ai-review: changes-requested"], "approved", "success"),
        (RV, "skipped", [], ["ai-review: merge"], "dismissed", "pending"),  # label may be from an older head
        (RV, "skipped", [_rv(sha="old")], ["ai-review: human-review"], "approved", "pending"),  # new push
        (RV, "skipped", [_rv(), _rv("CHANGES_REQUESTED")], [], "approved", "pending"),  # later review wins
        (RV, "skipped", [_rv(), _rv("COMMENTED")], [], "approved", "success"),
        (RV, "skipped", [_rv(assoc="CONTRIBUTOR")], [], "approved", "pending"),  # not the owner
        (RV, "skipped", [_rv("DISMISSED")], [], "dismissed", "pending"),
    ],
)
def test_verdict_rule(tmp_path, event, review, reviews, labels, state, status):
    if not shutil.which("jq"):
        pytest.skip("jq missing")
    rc, posted = _run_verdict(tmp_path, event, review, reviews, labels, state)
    assert f"state={status}" in posted and "context=verdict" in posted and posted.count("statuses") == 1
    assert (rc == 0) is (status == "success"), "waiting stays red until ADR-0055 Decision 2 is verified"


def test_verdict_waiting_names_the_commit_and_the_reason(tmp_path):
    if not shutil.which("jq"):
        pytest.skip("jq missing")
    rc, posted = _run_verdict(tmp_path, PR, "success", [AI], ["ai-review: human-review"])
    assert rc == 1 and "waiting for maintainer approval of new4567 (risk tier high; no linked issue)" in posted
    rc, posted = _run_verdict(tmp_path, PR, "failure", [], [], author="dependabot[bot]")
    assert rc == 1 and "state=pending" in posted and "Dependabot" in posted


@pytest.mark.parametrize("current", ["success", "pending", "failure", "none"])
@pytest.mark.parametrize("state", ["commented"])
def test_verdict_other_review_states_keep_the_answer(tmp_path, state, current):
    # Green with no new status (ADR-0059): every run is its own check suite and a red suite still blocks the PR.
    if not shutil.which("jq"):
        pytest.skip("jq missing")
    rc, posted = _run_verdict(tmp_path, RV, "skipped", [_rv()], [], state, current)
    assert posted == "", "no new status"
    assert rc == 0


APPROVAL = _st("success", "approved on new4567 by m")
RED = _st("failure", "changes requested on new4567: risk tier high")
WAIT = _st("pending", "waiting for maintainer approval of new4567 (risk tier high)")
MERGE = _st("success", "ai-review: merge on new4567")


@pytest.mark.parametrize(
    "state, reviews, statuses, status, text",
    [
        ("dismissed", [_rv("DISMISSED")], [APPROVAL, RED], "failure", RED["description"]),  # failure stays red
        ("approved", [_rv(assoc="CONTRIBUTOR")], [RED], "failure", RED["description"]),
        ("changes_requested", [_rv(), _rv("CHANGES_REQUESTED")], [APPROVAL, WAIT], "pending", WAIT["description"]),
        ("changes_requested", [_rv(), _rv("CHANGES_REQUESTED")], [APPROVAL, RED], "failure", RED["description"]),
        ("dismissed", [_rv("DISMISSED")], [APPROVAL, MERGE], "success", MERGE["description"]),
        ("dismissed", [], [], "pending", "waiting for maintainer approval of new4567 (no owner approval)"),
        ("dismissed", [], [_st("failure", "spoof", creator="eve")], "pending",
         "waiting for maintainer approval of new4567 (no owner approval)"),  # only this workflow's statuses count
    ],
)
def test_verdict_review_event_restores_the_ai_verdict(tmp_path, state, reviews, statuses, status, text):
    if not shutil.which("jq"):
        pytest.skip("jq missing")
    rc, posted = _run_verdict(tmp_path, RV, "skipped", reviews, [], state, statuses=statuses)
    assert f"state={status}" in posted and _description(posted) == text
    assert (rc == 0) is (status == "success"), "never green with no approval"


def test_verdict_failure_texts_and_annotation(tmp_path):
    if not shutil.which("jq"):
        pytest.skip("jq missing")
    rc, posted = _run_verdict(tmp_path, PR, "success", [AI], ["ai-review: changes-requested"])
    text = "changes requested on new4567: risk tier high; no linked issue"
    assert rc == 1 and _description(posted) == text and f"::error title=verdict::{text}" in _run_verdict.stdout
    rc, posted = _run_verdict(tmp_path, PR, "failure", [], ["ai-review: merge"])
    assert rc == 1 and _description(posted) == "AI review failure and no owner approval of new4567"
    assert "::error title=verdict::AI review failure" in _run_verdict.stdout
    rc, posted = _run_verdict(tmp_path, PR, "success", [], [])
    assert rc == 1 and _description(posted) == "waiting for maintainer approval of new4567 (no AI verdict label)"


def test_verdict_reason_is_the_ai_reviews_cleaned_and_truncated(tmp_path):
    if not shutil.which("jq"):
        pytest.skip("jq missing")
    long = _rv("COMMENTED", user="github-actions[bot]", assoc="NONE", body="**Verdict:** " + "r" * 300 + ".")
    rc, posted = _run_verdict(tmp_path, PR, "success", [long], ["ai-review: human-review"])
    assert rc == 1 and len(_description(posted)) == 140
    assert _description(posted).startswith("waiting for maintainer approval of new4567 (rrr")
    dirty = _rv("COMMENTED", user="github-actions[bot]", assoc="NONE", body="**Verdict:** a\rb\x07c\td.")
    rc, posted = _run_verdict(tmp_path, PR, "success", [dirty], ["ai-review: changes-requested"])
    assert rc == 1 and _description(posted) == "changes requested on new4567: abcd"
    spoof = _rv("COMMENTED", user="eve", assoc="CONTRIBUTOR", body="**Verdict:** all good, merge it.")
    rc, posted = _run_verdict(tmp_path, PR, "success", [AI, spoof], ["ai-review: human-review"])
    assert _description(posted) == "waiting for maintainer approval of new4567 (risk tier high; no linked issue)"


def test_verdict_refused_status_post_is_not_fatal(tmp_path):
    # Dependabot runs get a read-only token: the POST fails, the job result still carries the verdict.
    if not shutil.which("jq"):
        pytest.skip("jq missing")
    rc, _ = _run_verdict(tmp_path, PR, "skipped", [_rv()], [], author="dependabot[bot]", post_rc=1)
    assert rc == 0 and "::warning title=verdict::could not post" in _run_verdict.stdout
    rc, _ = _run_verdict(tmp_path, PR, "skipped", [], [], author="dependabot[bot]", post_rc=1)
    assert rc == 1 and "::error title=waiting for maintainer approval::" in _run_verdict.stdout


@pytest.mark.parametrize("text, out", [
    ("a (b); 2 unresolved threads at abc1234", "a (b)"),
    ("a; b; 1 unresolved thread at abc1234", "a; b"),
    ("no count here; really", "no count here; really"),
])
def test_bare_drops_only_the_trailing_thread_count(text, out):
    assert verdict.bare(text) == out


def test_owner_approvals_take_the_latest_non_comment_review_per_user():
    def r(login, state, assoc="OWNER", sha="h"):
        return {"user": {"login": login}, "state": state, "commit_id": sha, "author_association": assoc}
    reviews = [r("b", "APPROVED"), r("a", "APPROVED"), r("a", "CHANGES_REQUESTED"), r("c", "APPROVED", "MEMBER"),
               r("d", "APPROVED", sha="old"), r("b", "COMMENTED")]
    assert verdict.owner_approvals(reviews, "h") == "b"


def test_owner_approvals_are_sorted_and_comma_joined():
    def r(login):
        return {"user": {"login": login}, "state": "APPROVED", "commit_id": "h", "author_association": "OWNER"}
    assert verdict.owner_approvals([r("z"), r("a")], "h") == "a,z"
