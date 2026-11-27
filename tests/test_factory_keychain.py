import subprocess

from aiwf.factory import doctor, m0, spike


class Run:
    """Fake subprocess.run: records argv, returns the given returncode/stderr."""

    def __init__(self, rc=0, stderr="", exc=None):
        self.rc, self.stderr, self.exc, self.calls = rc, stderr, exc, []

    def __call__(self, args, **kw):
        self.calls.append(args)
        if self.exc:
            raise self.exc
        return subprocess.CompletedProcess(args, self.rc, "", self.stderr)


def darwin_with_keychain(monkeypatch, tmp_path):
    kc = tmp_path / "login.keychain-db"
    kc.write_text("")
    monkeypatch.setattr(m0.sys, "platform", "darwin")
    monkeypatch.setattr(m0, "keychain_path", lambda: kc)
    return kc


def test_unlock_uses_empty_password(monkeypatch, tmp_path):
    kc = darwin_with_keychain(monkeypatch, tmp_path)
    run = Run()
    monkeypatch.setattr(m0.subprocess, "run", run)
    assert m0.unlock_keychain() == (True, "unlocked")
    assert run.calls == [["security", "unlock-keychain", "-p", "", str(kc)]]


def test_unlock_skips_off_macos(monkeypatch):
    monkeypatch.setattr(m0.sys, "platform", "linux")
    run = Run()
    monkeypatch.setattr(m0.subprocess, "run", run)
    ok, msg = m0.unlock_keychain()
    assert ok and msg.startswith("skipped") and run.calls == []


def test_unlock_skips_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(m0.sys, "platform", "darwin")
    monkeypatch.setattr(m0, "keychain_path", lambda: tmp_path / "nope")
    run = Run()
    monkeypatch.setattr(m0.subprocess, "run", run)
    ok, msg = m0.unlock_keychain()
    assert ok and "does not exist" in msg and run.calls == []


def test_unlock_failure_reports_the_line(monkeypatch, tmp_path):
    darwin_with_keychain(monkeypatch, tmp_path)
    monkeypatch.setattr(m0.subprocess, "run", Run(rc=51, stderr="bad password\n"))
    ok, msg = m0.unlock_keychain()
    assert not ok and "rc=51" in msg and "bad password" in msg


def test_unlock_oserror_is_a_failure(monkeypatch, tmp_path):
    darwin_with_keychain(monkeypatch, tmp_path)
    monkeypatch.setattr(m0.subprocess, "run", Run(exc=FileNotFoundError("security")))
    assert m0.unlock_keychain() == (False, "security did not run (FileNotFoundError)")


def test_doctor_ok_when_unlocked(monkeypatch, tmp_path):
    kc = darwin_with_keychain(monkeypatch, tmp_path)
    run = Run()
    monkeypatch.setattr(m0.subprocess, "run", run)
    assert doctor.check_keychain() == (True, "login keychain unlocked")
    assert ["security", "show-keychain-info", str(kc)] in run.calls


def test_doctor_fails_when_unlock_fails(monkeypatch, tmp_path):
    darwin_with_keychain(monkeypatch, tmp_path)
    monkeypatch.setattr(m0.subprocess, "run", Run(rc=1, stderr="denied"))
    ok, msg = doctor.check_keychain()
    assert not ok and "denied" in msg


def test_doctor_fails_when_still_locked(monkeypatch, tmp_path):
    darwin_with_keychain(monkeypatch, tmp_path)
    monkeypatch.setattr(m0, "unlock_keychain", lambda: (True, "unlocked"))
    monkeypatch.setattr(doctor.subprocess, "run", Run(rc=36, stderr="User interaction is not allowed."))
    ok, msg = doctor.check_keychain()
    assert not ok and "rc=36" in msg


def test_doctor_skip_passes(monkeypatch):
    monkeypatch.setattr(m0.sys, "platform", "linux")
    assert doctor.check_keychain()[0] is True


def test_doctor_lists_keychain_check():
    assert "keychain" in [n for n, _ in doctor.CHECKS]


def test_spike_unlocks_first_and_stops_on_failure(monkeypatch, capsys):
    monkeypatch.setattr(m0, "unlock_keychain", lambda: (False, "denied"))
    monkeypatch.setattr(spike.secrets, "read_secret", lambda n: (_ for _ in ()).throw(AssertionError("read before unlock")))
    assert spike.main() == 1
    assert "FAIL keychain: denied" in capsys.readouterr().out


def test_main_unlocks_before_run(monkeypatch, tmp_path, capsys):
    order = []
    monkeypatch.setattr(m0, "stop_file", lambda: tmp_path / "STOP")
    monkeypatch.setattr(m0, "read_failures", lambda: 0)
    monkeypatch.setattr(m0, "write_failures", lambda n: None)
    monkeypatch.setattr(m0, "unlock_keychain", lambda: order.append("unlock") or (False, "denied"))
    monkeypatch.setattr(m0, "_run", lambda: order.append("run") or 0)
    assert m0.main() == 0
    assert order == ["unlock", "run"] and "keychain: denied" in capsys.readouterr().err
