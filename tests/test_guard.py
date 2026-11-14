import json
from pathlib import Path

import pytest
import yaml

from aiwf import cli, config, ghapi, guard
from aiwf import publish_review as pr
from ghfake import RecordingGh

BOT = ghapi.BOT


class FakeGh(RecordingGh):
    """Item labels and issue comments; records every call."""

    def __init__(self, labels=(), comments=(), head=None, head_repo="o/r", draft=False):
        super().__init__()
        self.labels = list(labels)
        self.comments = list(comments)
        self.head, self.head_repo, self.draft = head, head_repo, draft

    def respond(self, args):
        method, url = self.method(args), self.url(args)
        if method == "GET" and "/pulls/" in url:
            if self.head is None:
                raise RuntimeError("404")
            return json.dumps({"draft": self.draft, "head": {"sha": self.head, "repo": {"full_name": self.head_repo}}})
        if method == "GET" and "/labels" in url:
            return json.dumps([{"name": n} for n in self.labels])
        if method == "GET" and url.endswith("/comments?per_page=100"):
            return "\n".join(json.dumps(c) for c in self.comments)
        return "{}"


def test_event_labels_from_issue_or_pr():
    assert guard.event_labels({"issue": {"labels": [{"name": "ai: off"}, {"name": "x"}]}}) == {"ai: off", "x"}
    assert guard.event_labels({"pull_request": {"labels": [{"name": "ai: off"}]}}) == {"ai: off"}
    assert guard.event_labels({}) == set() and guard.event_labels({"issue": {"labels": None}}) == set()


def test_item_off_reads_live_labels():
    assert guard.item_off(FakeGh(labels=["ai: off"]), "o/r", 3)
    assert not guard.item_off(FakeGh(labels=["type: bug"]), "o/r", 3)


def test_report_error_labels_and_posts_one_comment():
    gh = FakeGh()
    assert guard.report_error(gh, "o/r", 3, "https://run/9", "failed job: context")
    posts = [c for c in gh.writes() if c[2] == "POST"]
    assert ["api", "-X", "POST", "repos/o/r/issues/3/labels", "-f", "labels[]=ai: error"] in posts
    body = next(c for c in posts if c[3].endswith("/comments"))[-1].removeprefix("body=")
    assert body.startswith(guard.ERROR_MARKER) and "https://run/9" in body and "failed job: context" in body
    assert ["api", "-X", "DELETE", "repos/o/r/issues/3/labels/ai-review%3A%20pending"] in gh.calls


def test_report_error_updates_its_own_comment_only():
    forged = {"id": 5, "user": {"login": "mallory"}, "body": guard.ERROR_MARKER + " fake"}
    own = {"id": 6, "user": {"login": BOT}, "body": guard.ERROR_MARKER + " old"}
    gh = FakeGh(comments=[forged, own])
    guard.report_error(gh, "o/r", 3, "https://run/10", "a job failed")
    assert [c[3] for c in gh.writes() if "comments" in c[3]] == ["repos/o/r/issues/comments/6"]


def test_report_error_writes_nothing_but_pending_removal_when_off():
    gh = FakeGh(labels=["ai: off"])
    assert not guard.report_error(gh, "o/r", 3, "https://run/9", "a job failed")
    assert [c[2] for c in gh.writes()] == ["DELETE"]


def test_failed_jobs_names_only():
    needs = {"context": {"result": "failure", "outputs": {"x": "@evil"}}, "gate": {"result": "success"},
             "publish": {"result": "failure"}, "pass": {"result": "skipped"}}
    assert guard.failed_jobs(needs) == ["context", "publish"]


def test_cmd_report_error_reason(monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(config, "run_gh", gh)
    monkeypatch.setenv("AIWF_NEEDS", json.dumps({"context": {"result": "failure"}}))
    assert cli.main(["report-error", "--repo", "o/r", "--issue", "3", "--run-url", "https://run/1"]) == 0
    body = next(c for c in gh.writes() if c[3].endswith("/comments"))[-1]
    assert "(failed job: context)" in body


def report(monkeypatch, gh, *extra):
    monkeypatch.setattr(config, "run_gh", gh)
    monkeypatch.setenv("AIWF_NEEDS", json.dumps({"context": {"result": "failure"}}))
    return cli.main(["report-error", "--repo", "o/r", "--issue", "3", "--run-url", "https://run/1", *extra])


def test_report_error_skips_a_run_whose_pr_head_moved(monkeypatch):
    gh = FakeGh(head="new")
    assert report(monkeypatch, gh, "--head-sha", "old") == 0
    assert gh.writes() == [["api", "-X", "DELETE", "repos/o/r/issues/3/labels/ai-review%3A%20pending"]]


@pytest.mark.parametrize("head", ["same", None])  # unchanged head; unreadable PR reports as usual
def test_report_error_reports_when_the_head_did_not_move(monkeypatch, head):
    gh = FakeGh(head=head)
    assert report(monkeypatch, gh, "--head-sha", "same") == 0
    assert ["api", "-X", "POST", "repos/o/r/issues/3/labels", "-f", "labels[]=ai: error"] in gh.writes()


@pytest.mark.parametrize("pr", [{"head_repo": "fork/r"}, {"draft": True}])
def test_report_error_still_reports_when_the_push_starts_no_review(monkeypatch, pr):
    # A fork PR (reviewed only on /review) or a draft gets no new review run, so this run still reports.
    gh = FakeGh(head="new", **pr)
    assert report(monkeypatch, gh, "--head-sha", "old") == 0
    assert ["api", "-X", "POST", "repos/o/r/issues/3/labels", "-f", "labels[]=ai: error"] in gh.writes()


def test_report_error_without_head_sha_does_not_look_up_the_pr(monkeypatch):
    gh = FakeGh(head="new")
    assert report(monkeypatch, gh) == 0
    assert not any("/pulls/" in a for c in gh.calls for a in c)
    assert ["api", "-X", "POST", "repos/o/r/issues/3/labels", "-f", "labels[]=ai: error"] in gh.writes()


def test_review_failed_job_passes_the_gate_sha():
    wf = yaml.safe_load((Path(__file__).resolve().parents[1] / ".github/workflows/review.yml").read_text())
    step = wf["jobs"]["failed"]["steps"][-1]
    assert step["env"]["HEAD_SHA"] == "${{ needs.gate.outputs.sha }}" and '--head-sha "$HEAD_SHA"' in step["run"]


@pytest.mark.parametrize("item_off", [False, True])
def test_config_outputs_item_off(item_off):
    cfg = config.load("maintainers: [me]\nworkflows: {review: true, triage: true}\n", "t")
    out = config.github_outputs(cfg, item_off=item_off)
    assert out["review"] == out["triage"] == out["enabled"] == json.dumps(not item_off)
    assert out["item_off"] == json.dumps(item_off)


def test_cli_config_reads_ai_off_from_the_event(tmp_path, monkeypatch):
    (tmp_path / "c.yml").write_text("maintainers: [me]\n")
    (tmp_path / "event.json").write_text(json.dumps({"issue": {"labels": [{"name": "ai: off"}]}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "event.json"))
    out = tmp_path / "out"
    assert cli.main(["config", "--file", str(tmp_path / "c.yml"), "--github-output", str(out)]) == 0
    got = dict(line.split("=", 1) for line in out.read_text().splitlines())
    assert got["enabled"] == "false" and got["review"] == "false" and got["item_off"] == "true"


def test_publish_writes_nothing_when_off(monkeypatch):
    gh = FakeGh(labels=["ai: off"])
    monkeypatch.setattr(config, "run_gh", gh)
    monkeypatch.setenv("AGENT_JSON", "{}")
    assert cli.main(["publish", "--kind", "classifier", "--repo", "o/r", "--issue", "3"]) == 0
    assert gh.writes() == []


def test_review_publish_only_removes_pending_when_off(monkeypatch, tmp_path):
    gh = FakeGh(labels=["ai: off", "ai-review: pending"])
    monkeypatch.setattr(pr.config, "run_gh", gh)
    args = type("A", (), {"repo": "o/r", "pr": 5, "run_url": "", "passes_dir": str(tmp_path)})
    assert pr.cmd_review_publish(args) == 0
    assert gh.writes() == [["api", "-X", "DELETE", "repos/o/r/issues/5/labels/ai-review%3A%20pending"]]


def test_clear_error_marks_our_comment_cleared_once():
    own = {"id": 6, "user": {"login": BOT}, "body": guard.ERROR_MARKER + "\n⚠️ old error"}
    forged = {"id": 5, "user": {"login": "mallory"}, "body": guard.ERROR_MARKER + " fake"}
    gh = FakeGh(comments=[forged, own])
    guard.clear_error(gh, "o/r", 3, "https://run/2")
    [patch] = gh.writes()
    assert patch[3] == "repos/o/r/issues/comments/6"
    body = patch[-1].removeprefix("body=")
    assert body.startswith(f"{guard.ERROR_MARKER}\n{guard.CLEARED}") and "https://run/2" in body
    own["body"] = body
    guard.clear_error(gh, "o/r", 3, "https://run/3")
    assert len(gh.writes()) == 1  # already cleared: no second edit


def test_clear_error_without_an_error_comment_writes_nothing():
    gh = FakeGh(comments=[{"id": 5, "user": {"login": "mallory"}, "body": guard.ERROR_MARKER}])
    guard.clear_error(gh, "o/r", 3, "")
    assert gh.writes() == []


def test_clear_error_failure_is_only_a_warning(capsys):
    def broken(args):
        raise RuntimeError("HTTP 502")
    guard.clear_error(broken, "o/r", 3, "")
    assert "::warning title=Error comment not cleared::o/r#3: HTTP 502" in capsys.readouterr().out


def publish_without_facts(monkeypatch, gh, head_sha):
    monkeypatch.setattr(pr.config, "run_gh", gh)
    monkeypatch.delenv("FACTS", raising=False)
    args = type("A", (), {"repo": "o/r", "pr": 3, "run_url": "", "passes_dir": "x", "head_sha": head_sha})
    return pr.cmd_review_publish(args)


def test_review_publish_without_context_on_a_moved_head_sets_no_error(monkeypatch):
    gh = FakeGh(head="new")
    assert publish_without_facts(monkeypatch, gh, "old") == 0
    assert gh.writes() == [["api", "-X", "DELETE", "repos/o/r/issues/3/labels/ai-review%3A%20pending"]]


@pytest.mark.parametrize("head,sha", [("same", "same"), ("new", ""), (None, "old")])
def test_review_publish_without_context_otherwise_sets_ai_error(monkeypatch, head, sha):
    gh = FakeGh(head=head)
    assert publish_without_facts(monkeypatch, gh, sha) == 1
    assert any(c[3] == "repos/o/r/issues/3/labels" and "labels[]=ai: error" in c for c in gh.writes())


def test_review_publish_passes_the_gate_sha():
    wf = yaml.safe_load((Path(__file__).resolve().parents[1] / ".github/workflows/review.yml").read_text())
    step = next(s for s in wf["jobs"]["publish"]["steps"] if s.get("id") == "publish")
    assert step["env"]["HEAD_SHA"] == "${{ needs.gate.outputs.sha }}" and '--head-sha "$HEAD_SHA"' in step["run"]
