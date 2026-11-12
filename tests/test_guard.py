import json

import pytest

from aiwf import cli, config, ghapi, guard
from aiwf import publish_review as pr

BOT = ghapi.BOT


class FakeGh:
    """Item labels and issue comments; records every call."""

    def __init__(self, labels=(), comments=()):
        self.labels = list(labels)
        self.comments = list(comments)
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        method = args[args.index("-X") + 1] if "-X" in args else "GET"
        url = next(a for a in args[1:] if a.startswith("repos/"))
        if method == "GET" and "/labels" in url:
            return json.dumps([{"name": n} for n in self.labels])
        if method == "GET" and url.endswith("/comments?per_page=100"):
            return "\n".join(json.dumps(c) for c in self.comments)
        return "{}"

    def writes(self):
        return [c for c in self.calls if "-X" in c and c[c.index("-X") + 1] != "GET"]


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
