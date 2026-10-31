import json

import pytest

from aiwf import cli, review_gate
from aiwf.review_gate import Gate

REPO = "acme/app"
CFG = {"maintainers": ["Alice"], "fork_prs": "on-command"}


def pr(number=7, sha="a" * 40, head_repo=REPO, draft=False, state="open"):
    return {"number": number, "state": state, "draft": draft,
            "head": {"sha": sha, "repo": {"full_name": head_repo} if head_repo else None}}


def fake_gh(permission="write", pull=None):
    calls = []

    def gh(args):
        calls.append(args)
        if "/collaborators/" in args[1]:
            return permission
        if "/pulls/" in args[1]:
            return json.dumps(pull or pr())
        raise AssertionError(args)

    gh.calls = calls
    return gh


def comment_event(body="/review", login="alice", on_pr=True):
    issue = {"number": 7, **({"pull_request": {"url": "x"}} if on_pr else {})}
    return {"issue": issue, "comment": {"body": body, "user": {"login": login}}}


# --- pull_request ----------------------------------------------------------------------------------------------------


def test_same_repo_pr_is_reviewed():
    gate = review_gate.decide("pull_request", {"pull_request": pr()}, CFG, REPO, fake_gh())
    assert gate == Gate(True, "PR event", 7, "a" * 40)


def test_draft_pr_is_skipped():
    assert not review_gate.decide("pull_request", {"pull_request": pr(draft=True)}, CFG, REPO, fake_gh()).run


@pytest.mark.parametrize("head_repo", ["outsider/app", None, "acme/app-fork"])
def test_fork_pr_event_is_never_reviewed(head_repo):
    gh = fake_gh()
    gate = review_gate.decide("pull_request", {"pull_request": pr(head_repo=head_repo)}, CFG, REPO, gh)
    assert not gate.run and gate.fork
    assert gh.calls == []


def test_fork_detection_ignores_case():
    assert not review_gate.is_fork(pr(head_repo="ACME/App"), REPO)


# --- /review ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("login,permission,ok", [
    ("alice", "write", True),
    ("alice", "admin", True),
    ("ALICE", "write", True),
    ("alice", "read", False),
    ("alice", "none", False),
    ("mallory", "write", False),  # write access but not in maintainers
    ("mallory", "admin", False),
    ("mallory", "none", False),
])
def test_review_needs_maintainer_and_write_access(login, permission, ok):
    gh = fake_gh(permission, pr(head_repo="outsider/app", sha="b" * 40))
    gate = review_gate.decide("issue_comment", comment_event(login=login), CFG, REPO, gh)
    assert gate.run is ok
    if ok:
        assert gate == Gate(True, "/review", 7, "b" * 40, True)


def test_review_on_same_repo_pr_is_a_forced_run():
    gate = review_gate.decide("issue_comment", comment_event(), CFG, REPO, fake_gh(pull=pr(draft=True)))
    assert gate == Gate(True, "/review", 7, "a" * 40, False)


def test_fork_prs_off_refuses_a_fork_but_not_a_same_repo_pr():
    cfg = {**CFG, "fork_prs": "off"}
    fork = review_gate.decide("issue_comment", comment_event(), cfg, REPO, fake_gh(pull=pr(head_repo="o/app")))
    assert not fork.run and fork.fork
    assert review_gate.decide("issue_comment", comment_event(), cfg, REPO, fake_gh()).run


@pytest.mark.parametrize("body", ["/ping", "/fix", "please /review", "> /review", "review", "", None])
def test_other_comments_are_ignored(body):
    gh = fake_gh()
    assert not review_gate.decide("issue_comment", comment_event(body=body), CFG, REPO, gh).run
    assert not [c for c in gh.calls if "/pulls/" in c[1]]


def test_review_on_an_issue_is_ignored():
    gh = fake_gh()
    assert not review_gate.decide("issue_comment", comment_event(on_pr=False), CFG, REPO, gh).run
    assert gh.calls == []


def test_closed_pr_is_not_reviewed():
    assert not review_gate.decide("issue_comment", comment_event(), CFG, REPO, fake_gh(pull=pr(state="closed"))).run


@pytest.mark.parametrize("event", ["pull_request_target", "issues", "push", ""])
def test_other_events_start_nothing(event):
    assert not review_gate.decide(event, {"pull_request": pr()}, CFG, REPO, fake_gh()).run


# --- CLI ------------------------------------------------------------------------------------------------------------


def test_cli_reads_the_event_file_and_writes_outputs(tmp_path, monkeypatch):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": pr()}))
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("AIWF_CONFIG", json.dumps(CFG))
    assert cli.main(["review-gate", "--repo", REPO, "--github-output", str(out)]) == 0
    assert out.read_text().splitlines() == ["run=true", "pr=7", f"sha={'a' * 40}", "fork=false"]


def test_cli_skip_outputs(tmp_path, monkeypatch):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": pr(head_repo="o/app")}))
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    assert cli.main(["review-gate", "--repo", REPO, "--github-output", str(out)]) == 0
    assert out.read_text().splitlines() == ["run=false", "pr=", "sha=", "fork=true"]
