"""e2eslot.push_target to GitHub: the push goes through the agent App wrapper, never bare git (ADR-0031)."""

import subprocess

import pytest

from aiwf import e2eslot

SHA = "a" * 40


@pytest.fixture
def no_real_git(tmp_path, monkeypatch):
    """Locks in a temp dir; `git rev-parse` answers SHA and `ls-remote` answers nothing (the ref is absent remotely)."""
    monkeypatch.setenv("AIWF_E2E_LOCK_DIR", str(tmp_path))
    monkeypatch.setattr(e2eslot, "_git", lambda *a, cwd=e2eslot.ROOT: SHA if a[0] == "rev-parse" else "")


def test_a_non_local_remote_is_pushed_by_the_agent_app_with_a_lease(tmp_path, monkeypatch, no_real_git):
    ran = []
    monkeypatch.setattr(e2eslot.subprocess, "run", lambda cmd, **kw: ran.append((cmd, kw)))
    with e2eslot.hold(2, timeout=0):
        assert e2eslot.push_target(2, remote="origin", cwd=tmp_path) == SHA
    [(cmd, kw)] = ran
    assert cmd[0].endswith("scripts/dev/as-agent") and cmd[1:4] == ["git", "push", "--quiet"]
    assert cmd[4] == "--force-with-lease=refs/heads/e2e-target-2:"  # absent remotely: the lease expects no ref
    assert cmd[5:] == ["origin", f"{SHA}:refs/heads/e2e-target-2"]
    assert kw["cwd"] == tmp_path and kw["check"] is True


def test_the_lease_is_the_remotes_current_value(tmp_path, monkeypatch):
    monkeypatch.setenv("AIWF_E2E_LOCK_DIR", str(tmp_path))
    old = "b" * 40
    monkeypatch.setattr(e2eslot, "_git", lambda *a, cwd=e2eslot.ROOT: SHA if a[0] == "rev-parse" else f"{old}\trefs/x")
    ran = []
    monkeypatch.setattr(e2eslot.subprocess, "run", lambda cmd, **kw: ran.append(cmd))
    with e2eslot.hold(1, timeout=0):
        e2eslot.push_target(1, cwd=tmp_path)
    assert ran[0][4] == f"--force-with-lease=refs/heads/e2e-target-1:{old}"


def test_a_refused_agent_push_is_raised(tmp_path, monkeypatch, no_real_git):
    def refuse(cmd, **kw):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(e2eslot.subprocess, "run", refuse)
    with e2eslot.hold(2, timeout=0), pytest.raises(subprocess.CalledProcessError):
        e2eslot.push_target(2, cwd=tmp_path)
