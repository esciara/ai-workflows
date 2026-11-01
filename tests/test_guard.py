import argparse
import json

import pytest

from aiwf import cli, config, guard
from aiwf import publish_review as pr

BOT = guard.BOT


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


@pytest.mark.parametrize("item_off,e2e", [(False, False), (True, False), (False, True)])
def test_config_outputs_item_off_and_e2e(item_off, e2e):
    cfg = config.load("maintainers: [me]\nworkflows: {review: true, triage: true}\n", "t")
    out = config.github_outputs(cfg, item_off=item_off, e2e=e2e)
    assert out["review"] == out["triage"] == out["enabled"] == json.dumps(not item_off)
    assert out["item_off"] == json.dumps(item_off)
    assert json.loads(out["config"]).get("e2e") is (True if e2e else None)


def test_cli_config_reads_ai_off_from_the_event(tmp_path, monkeypatch):
    (tmp_path / "c.yml").write_text("maintainers: [me]\n")
    (tmp_path / "event.json").write_text(json.dumps({"issue": {"labels": [{"name": "ai: off"}]}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "event.json"))
    out = tmp_path / "out"
    assert cli.main(["config", "--file", str(tmp_path / "c.yml"), "--github-output", str(out)]) == 0
    got = dict(line.split("=", 1) for line in out.read_text().splitlines())
    assert got["enabled"] == "false" and got["review"] == "false" and got["item_off"] == "true"
    assert "e2e" not in json.loads(got["config"])


def test_publish_writes_nothing_when_off(monkeypatch):
    gh = FakeGh(labels=["ai: off"])
    monkeypatch.setattr(config, "run_gh", gh)
    monkeypatch.setenv("AGENT_JSON", '{"reply": "fine"}')
    assert cli.main(["publish", "--kind", "ping", "--repo", "o/r", "--issue", "3"]) == 0
    assert gh.writes() == []


def test_review_publish_only_removes_pending_when_off(monkeypatch, tmp_path):
    gh = FakeGh(labels=["ai: off", "ai-review: pending"])
    monkeypatch.setattr(pr.config, "run_gh", gh)
    args = type("A", (), {"repo": "o/r", "pr": 5, "run_url": "", "passes_dir": str(tmp_path)})
    assert pr.cmd_review_publish(args) == 0
    assert gh.writes() == [["api", "-X", "DELETE", "repos/o/r/issues/5/labels/ai-review%3A%20pending"]]


# --- budgets (WP12b, ADR-0045) ---------------------------------------------------------------------------------------

LIMITS = {"agent_budget_usd": 1, "run_budget_usd": 5, "agent_minutes": 10}


@pytest.mark.parametrize("usage,want", [
    ({}, ""),
    ({"extract": None, "classify": {"cost_usd": 0.4, "subtype": "success", "timed_out": False}}, ""),
    ({"extract": {"cost_usd": 0.01, "subtype": "error_max_budget_usd"}}, "agent `extract` hit its cost budget ($1)"),
    ({"classify": {"timed_out": True}}, "agent `classify` hit its time budget (10 min)"),
    ({"a": {"cost_usd": 3.0}, "b": {"cost_usd": 2.5}, "c": {"cost_usd": "9"}}, "over the run budget ($5)"),
    ({"a": {"cost_usd": 3.0}, "b": {"cost_usd": 2.0}}, ""),  # exactly at the run budget
])
def test_budget_hit(usage, want):
    got = guard.budget_hit(usage, LIMITS)
    assert (want in got and got) if want else got == ""


def test_report_budget_labels_escalates_and_posts_one_sticky_note():
    own = {"id": 6, "user": {"login": BOT}, "body": guard.BUDGET_MARKER + " old"}
    gh = FakeGh(comments=[own])
    assert guard.report_budget(gh, "o/r", 3, "https://run/9", "agent `x` hit its cost budget", "triage: needs-human")
    assert ["api", "-X", "POST", "repos/o/r/issues/3/labels", "-f", "labels[]=ai: budget",
            "-f", "labels[]=triage: needs-human"] in gh.writes()
    [patch] = [c for c in gh.writes() if c[2] == "PATCH"]
    assert patch[3] == "repos/o/r/issues/comments/6" and "https://run/9" in patch[-1]
    assert patch[-1].removeprefix("body=").startswith(guard.BUDGET_MARKER)
    assert not any(c[3].endswith("/comments") for c in gh.writes() if c[2] == "POST")


def test_report_budget_does_nothing_but_pending_removal_when_off():
    gh = FakeGh(labels=["ai: off"])
    assert not guard.report_budget(gh, "o/r", 3, "https://run/9", "r", "triage: needs-human")
    assert [c[2] for c in gh.writes()] == ["DELETE"]


def test_publish_escalates_a_budget_hit_instead_of_publishing(monkeypatch, tmp_path):
    gh = FakeGh()
    monkeypatch.setattr(config, "run_gh", gh)
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("AIWF_CONFIG", json.dumps({"limits": LIMITS}))
    monkeypatch.setenv("AIWF_USAGE", json.dumps({"extract": {"subtype": "error_max_budget_usd"}, "classify": None}))
    monkeypatch.setenv("AGENT_JSON", "")
    args = argparse.Namespace(kind="classifier", repo="o/r", issue=3, run_url="https://run/9")
    assert cli.cmd_publish(args) == 0
    assert "budget=true" in out.read_text()
    labels = [a for c in gh.writes() if c[3].endswith("/labels") for a in c if a.startswith("labels[]=")]
    assert labels == ["labels[]=ai: budget", "labels[]=triage: needs-human"]  # no ai: error


def test_publish_without_budget_hit_publishes(monkeypatch):
    monkeypatch.setenv("AIWF_CONFIG", json.dumps({"limits": LIMITS}))
    monkeypatch.setenv("AIWF_USAGE", json.dumps({"extract": {"cost_usd": 0.1, "subtype": "success"}}))
    assert not guard.check_budget(FakeGh(), "o/r", 3, "https://run/9", "triage: needs-human")
