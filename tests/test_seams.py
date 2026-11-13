"""ADR-0025 seams: per-module commands, per-workflow publishers, the e2e helpers (slots: tests/test_e2eslot.py)."""

import contextlib
import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

from aiwf import cli, config, publish


def test_shared_commands_registered_once():
    assert cli.command_modules()[0] is cli
    for argv in (["labels-sync", "--repo", "o/r"], ["publish", "--kind", "classifier", "--repo", "o/r", "--issue", "1"]):
        with pytest.raises(SystemExit):
            cli.main([*argv, "--bogus"])  # parses up to the unknown flag: the command exists


def test_module_with_register_adds_its_command(monkeypatch):
    mod = types.ModuleType("aiwf.fake_wf")
    mod.register = lambda sub: sub.add_parser("fake-wf").set_defaults(func=lambda args: 7)
    monkeypatch.setattr(cli, "command_modules", lambda: [cli, mod])
    assert cli.main(["fake-wf"]) == 7


def test_duplicate_command_is_an_error(monkeypatch):
    monkeypatch.setattr(cli, "command_modules", lambda: [cli, cli])
    with pytest.raises(Exception, match="conflicting subparser"):
        cli.main(["labels-sync", "--repo", "o/r"])


def test_publishers_come_from_per_workflow_modules():
    from aiwf import publish_triage

    assert publish.publishers()["classifier"] is publish_triage.publish_classifier


def test_unknown_kind_posts_nothing():
    calls = []
    with pytest.raises(ValueError, match="no publisher"):
        publish.publish("nope", "{}", "o/r", 1, "", calls.append)
    assert calls == []


def test_config_reads_the_repo(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(config, "run_gh", lambda args: seen.append(args) or ("main" if "--jq" in args else
                        '{"type": "file", "content": "bWFpbnRhaW5lcnM6IFthXQo="}'))  # "maintainers: [a]\n"
    assert cli.main(["config", "--repo", "o/r", "--github-output", str(tmp_path / "o")]) == 0
    assert any("repos/o/r/contents/.github/ai-workflows.yml?ref=main" in a for a in seen)


sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent / "e2e"))
import playground as pg  # noqa: E402


def test_e2e_pr_branches_carry_the_slot_routing_prefix(monkeypatch):
    assert pg.pr_branch(e2e=True, wp="wp2", slug="core-review", slot=3).startswith("e2e/3/wp2-core-review-")
    monkeypatch.setenv("AIWF_E2E_SLOT_HELD", "2")
    monkeypatch.setenv("AIWF_E2E_TARGET_SHA", "abc")
    assert pg.pr_branch(e2e=True, wp="wp2", slug="core-review").startswith("e2e/2/wp2-core-review-")
    assert not pg.pr_branch(e2e=False).startswith("e2e/")
    for wp, slug in [("2", "x"), ("wp2", ""), ("wp2", "Bad_Slug"), ("wp2", "a/b")]:
        with pytest.raises(ValueError):
            pg.pr_branch(e2e=True, wp=wp, slug=slug)


def test_e2e_names_follow_the_held_slot(monkeypatch):
    monkeypatch.delenv("AIWF_E2E_SLOT_HELD", raising=False)
    assert "no e2e slot" in pg.E2E_WORKFLOW and "no e2e slot" in pg.E2E_LABEL  # importable without a slot
    with pytest.raises(pytest.fail.Exception, match="AIWF_E2E_SLOT"):
        pg.pr_branch(e2e=True, wp="wp2", slug="x")
    monkeypatch.setenv("AIWF_E2E_SLOT_HELD", "3")
    monkeypatch.setenv("AIWF_E2E_TARGET_SHA", "abc")
    assert (pg.E2E_WORKFLOW, pg.E2E_NOTIFY_WORKFLOW, pg.E2E_LABEL) == (
        "AI workflows (e2e 3)", "AI workflows notify (e2e 3)", "e2e-target-3")


def test_throwaway_e2e_pr_uses_prefix_then_labels_and_cleans_up(monkeypatch):
    monkeypatch.setenv("AIWF_E2E_SLOT_HELD", "2")
    monkeypatch.setenv("AIWF_E2E_TARGET_SHA", "abc")
    calls = []

    def api(path, *fields, method="GET", as_tester=False):
        calls.append((method, path, fields))
        if path.endswith("/labels?per_page=100"):
            return [{"name": pg.E2E_LABEL}]
        return {"default_branch": "main", "object": {"sha": "abc"}, "state": "open"}

    def gh(args, as_agent=False, **_):
        calls.append((args[2], args[3], tuple(args[4:])))  # the PR is created with gh (`-F draft=…` is a boolean)
        return '{"number": 5}'

    monkeypatch.setattr(pg, "api", api)
    monkeypatch.setattr(pg, "gh", gh)
    with pg.throwaway_pr("[e2e] t", e2e=True, wp="wp2", slug="demo") as pr:
        assert pr["branch"].startswith("e2e/2/wp2-demo-") and pr["number"] == 5
    ref = next(c for c in calls if c[1].endswith("/git/refs"))
    assert f"ref=refs/heads/{pr['branch']}" in ref[2]
    i_pr = next(i for i, c in enumerate(calls) if c[1].endswith("/pulls") and c[0] == "POST")
    i_lb = next(i for i, c in enumerate(calls) if c[1].endswith("/issues/5/labels"))
    assert "draft=false" in calls[i_pr][2]
    assert i_pr < i_lb and set(calls[i_lb][2]) == {f"labels[]={pg.FIXTURE_LABEL}", "labels[]=e2e-target-2"}
    assert ("DELETE", f"repos/{pg.REPO}/git/refs/heads/{pr['branch']}", ()) in calls
    assert ("PATCH", f"repos/{pg.REPO}/pulls/5", ("state=closed",)) in calls


def _e2e_conftest():
    spec = importlib.util.spec_from_file_location("e2e_conftest", Path(__file__).parent / "e2e" / "conftest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_controller_takes_the_slot_and_exports_it_to_workers(monkeypatch):
    from aiwf import e2eslot
    conftest, cleanups, seen = _e2e_conftest(), [], []

    @contextlib.contextmanager
    def hold(slot):
        seen.append(slot)
        yield 3

    monkeypatch.setattr(e2eslot, "hold", hold)
    monkeypatch.setattr(e2eslot, "push_target", lambda n, remote: f"sha-of-{n}-on-{remote}")
    for var in ("AIWF_E2E_SLOT_HELD", "AIWF_E2E_TARGET_SHA", "AIWF_E2E_REMOTE"):
        monkeypatch.setenv(var, "")  # recorded, so the values the configure hook sets are undone after the test
        monkeypatch.delenv(var)
    monkeypatch.setenv("AIWF_E2E", "1")
    config = types.SimpleNamespace(add_cleanup=cleanups.append)

    monkeypatch.setenv("AIWF_E2E_SLOT", "4")
    with pytest.raises(pytest.UsageError, match=r"1\|2\|3\|any"):
        conftest.pytest_configure(config)
    monkeypatch.setenv("AIWF_E2E_SLOT", "")
    conftest.pytest_configure(config)
    assert seen == [] and "AIWF_E2E_SLOT_HELD" not in os.environ
    monkeypatch.setenv("AIWF_E2E_SLOT", "any")
    conftest.pytest_configure(config)
    assert seen == ["any"] and len(cleanups) == 1
    assert (os.environ["AIWF_E2E_SLOT_HELD"], os.environ["AIWF_E2E_TARGET_SHA"]) == ("3", "sha-of-3-on-origin")
    assert conftest.e2e_target.__wrapped__() == "sha-of-3-on-origin"
    monkeypatch.delenv("AIWF_E2E_SLOT_HELD")
    with pytest.raises(pytest.fail.Exception, match="AIWF_E2E_SLOT=1"):
        conftest.e2e_target.__wrapped__()
