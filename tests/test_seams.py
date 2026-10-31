"""ADR-0025 seams: per-module commands, per-workflow publishers, the e2e slot and the e2e config (ADR-0026, ADR-0028)."""

import os
import signal
import subprocess
import sys
import types

import pytest

from aiwf import cli, config, e2eslot, publish


def test_shared_commands_registered_once():
    assert cli.command_modules()[0] is cli
    for argv in (["labels-sync", "--repo", "o/r"], ["publish", "--kind", "ping", "--repo", "o/r", "--issue", "1"]):
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
    from aiwf import publish_commands

    assert publish.publishers()["ping"] is publish_commands.publish_ping


def test_unknown_kind_posts_nothing():
    calls = []
    with pytest.raises(ValueError, match="no publisher"):
        publish.publish("nope", "{}", "o/r", 1, "", calls.append)
    assert calls == []


@pytest.mark.parametrize("name", ["playground.yml"])
def test_e2e_config_read_from_this_checkout(name, tmp_path):
    cfg = config.load(*config.read_e2e(name))
    assert cfg["maintainers"] == ["esciara"]
    out = tmp_path / "out"
    assert cli.main(["config", "--repo", "o/r", "--e2e-config", name, "--github-output", str(out)]) == 0  # no gh call
    assert '"maintainers":["esciara"]' in out.read_text()


@pytest.mark.parametrize("name", ["../../../.github/ai-workflows.yml", "/etc/passwd", "sub/x.yml", ".hidden.yml", "x.json", "missing.yml"])
def test_e2e_config_rejects_paths_and_missing(name):
    with pytest.raises(config.ConfigError):
        config.read_e2e(name)


def test_no_e2e_config_reads_the_repo(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(config, "run_gh", lambda args: seen.append(args) or ("main" if "--jq" in args else
                        '{"type": "file", "content": "bWFpbnRhaW5lcnM6IFthXQo="}'))  # "maintainers: [a]\n"
    assert cli.main(["config", "--repo", "o/r", "--e2e-config", "", "--github-output", str(tmp_path / "o")]) == 0
    assert any("repos/o/r/contents/.github/ai-workflows.yml?ref=main" in a for a in seen)


HOLDER = "import sys, time; from aiwf import e2eslot; from pathlib import Path\n" \
         "with e2eslot.hold(Path(sys.argv[1])):\n    print('held', flush=True); time.sleep(60)\n"


def test_slot_is_exclusive_and_released_when_the_holder_dies(tmp_path):
    lock = tmp_path / "e2e.lock"
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    holder = subprocess.Popen([sys.executable, "-c", HOLDER, str(lock)], stdout=subprocess.PIPE, text=True, env=env)
    try:
        assert holder.stdout.readline().strip() == "held"
        with pytest.raises(e2eslot.SlotBusy, match="pid"):
            with e2eslot.hold(lock, timeout=0):
                pass
        holder.send_signal(signal.SIGKILL)
        holder.wait()
        with e2eslot.hold(lock, timeout=5, poll=0.1):
            pass
    finally:
        holder.kill()


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def test_push_target_needs_the_slot_and_uses_a_lease(tmp_path):
    remote, work, lock = tmp_path / "remote.git", tmp_path / "work", tmp_path / "e2e.lock"
    git("init", "--bare", "-q", str(remote), cwd=tmp_path)
    git("init", "-q", str(work), cwd=tmp_path)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "one", cwd=work)
    with pytest.raises(RuntimeError, match="needs the e2e slot"):
        e2eslot.push_target(remote=str(remote), cwd=work, path=lock)
    with e2eslot.hold(lock, timeout=0):
        sha = e2eslot.push_target(remote=str(remote), cwd=work, path=lock)  # creates the branch
        assert git("rev-parse", "e2e-target", cwd=remote) == sha
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "two", cwd=work)
        assert e2eslot.push_target(remote=str(remote), cwd=work, path=lock) == git("rev-parse", "HEAD", cwd=work)
    assert str(lock) not in e2eslot._held


sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent / "e2e"))
import playground as pg  # noqa: E402


def test_e2e_pr_branches_carry_the_routing_prefix():
    assert pg.pr_branch(e2e=True, wp="wp2", slug="core-review").startswith("e2e/wp2-core-review-")
    assert not pg.pr_branch(e2e=False).startswith("e2e/")
    for wp, slug in [("2", "x"), ("wp2", ""), ("wp2", "Bad_Slug"), ("wp2", "a/b")]:
        with pytest.raises(ValueError):
            pg.pr_branch(e2e=True, wp=wp, slug=slug)


def test_throwaway_e2e_pr_uses_prefix_then_labels_and_cleans_up(monkeypatch):
    calls = []

    def api(path, *fields, method="GET", as_tester=False):
        calls.append((method, path, fields))
        if path.endswith("/labels?per_page=100"):
            return [{"name": pg.E2E_LABEL}]
        if path.endswith("/pulls") and method == "POST":
            return {"number": 5}
        return {"default_branch": "main", "object": {"sha": "abc"}, "state": "open"}

    monkeypatch.setattr(pg, "api", api)
    monkeypatch.setattr(pg, "gh", lambda args, as_tester=False: calls.append(("GH", args[2], args[3])))
    with pg.throwaway_pr("[e2e] t", e2e=True, wp="wp2", slug="demo") as pr:
        assert pr["branch"].startswith("e2e/wp2-demo-") and pr["number"] == 5
    ref = next(c for c in calls if c[1].endswith("/git/refs"))
    assert f"ref=refs/heads/{pr['branch']}" in ref[2]
    i_pr = next(i for i, c in enumerate(calls) if c[1].endswith("/pulls") and c[0] == "POST")
    i_lb = next(i for i, c in enumerate(calls) if c[1].endswith("/issues/5/labels"))
    assert i_pr < i_lb and set(calls[i_lb][2]) == {f"labels[]={pg.FIXTURE_LABEL}", f"labels[]={pg.E2E_LABEL}"}
    assert ("GH", "DELETE", f"repos/{pg.REPO}/git/refs/heads/{pr['branch']}") in calls
    assert ("PATCH", f"repos/{pg.REPO}/pulls/5", ("state=closed",)) in calls
