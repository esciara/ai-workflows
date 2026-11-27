import pytest

from aiwf.factory import m0, secrets, spike


@pytest.fixture(autouse=True)
def _no_real_keychain(monkeypatch):
    monkeypatch.setattr(m0, "unlock_keychain", lambda: (True, "skipped: test"))


def fake_sh(rc_by_prefix, out_by_prefix=None):
    """Replaces spike.sh: the first matching prefix of the args decides (rc, stdout); records every call."""
    calls = []

    def sh(args, env=None, stdin=None, timeout=300):
        calls.append(args)
        for prefix, rc in rc_by_prefix:
            if args[: len(prefix)] == prefix:
                return rc, (out_by_prefix or {}).get(tuple(prefix), "")
        return 0, ""

    sh.calls = calls
    return sh


def test_all_green_prints_pass_summary_and_removes_the_sandbox(monkeypatch, capsys):
    monkeypatch.setattr(secrets, "read_secret", lambda name: "tok-secret-value")
    sh = fake_sh([(["sbx", "exec"], 0)], {("sbx", "exec"): "Hello, world!"})
    monkeypatch.setattr(spike, "sh", sh)
    assert spike.main() == 0
    out = capsys.readouterr().out
    assert "SUMMARY: PASS" in out and "\nFAIL " not in out
    assert "tok-secret-value" not in out
    assert m0.sbx_rm_args(spike.NAME) in sh.calls
    exec_call = next(c for c in sh.calls if c[:2] == ["sbx", "exec"])
    assert m0.TOKEN_ENV in exec_call and "tok-secret-value" not in " ".join(exec_call)


def test_missing_secret_fails_before_touching_sbx(monkeypatch, capsys):
    def boom(name):
        raise secrets.SecretsError("no key file")

    monkeypatch.setattr(secrets, "read_secret", boom)
    sh = fake_sh([])
    monkeypatch.setattr(spike, "sh", sh)
    assert spike.main() == 1
    assert "FAIL secrets" in capsys.readouterr().out and sh.calls == []


def test_sbx_without_gui_stops_the_spike(monkeypatch, capsys):
    monkeypatch.setattr(secrets, "read_secret", lambda name: "t")
    sh = fake_sh([(["sbx", "ls"], 1)])
    monkeypatch.setattr(spike, "sh", sh)
    assert spike.main() == 1
    assert "FAIL sbx-no-gui" in capsys.readouterr().out and not any(c[:2] == ["sbx", "create"] for c in sh.calls)


def test_a_failed_claude_run_still_removes_the_sandbox(monkeypatch, capsys):
    monkeypatch.setattr(secrets, "read_secret", lambda name: "t")
    sh = fake_sh([(["sbx", "exec"], 2)])
    monkeypatch.setattr(spike, "sh", sh)
    assert spike.main() == 1
    assert "FAIL claude-stdin-bare-e-egress" in capsys.readouterr().out
    assert sh.calls.count(m0.sbx_rm_args(spike.NAME)) == 2
