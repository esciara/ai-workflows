import os
import plistlib
import subprocess
from pathlib import Path

import pytest

from aiwf.factory import doctor, secrets

TOKEN = "sk-ant-oat01-SECRETVALUE"


def make(tmp_path, key_mode=0o600, dir_mode=0o700, enc=True):
    d = tmp_path / "aiwf"
    d.mkdir()
    d.chmod(dir_mode)
    (d / "age.key").write_text("AGE-SECRET-KEY-FAKE")
    (d / "age.key").chmod(key_mode)
    if enc:
        (d / "secrets.enc.yaml").write_text("claude_oauth: ENC[...]")
    return secrets.Paths(key=d / "age.key", enc=d / "secrets.enc.yaml")


def test_good_key_file_has_no_problems(tmp_path):
    assert secrets.check_key_file(make(tmp_path)) == []


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o660, 0o400, 0o700])
def test_key_file_with_wrong_mode_refuses_to_start(tmp_path, mode):
    p = make(tmp_path, key_mode=mode)
    assert any(f"{mode:04o}" in x for x in secrets.check_key_file(p))
    with pytest.raises(secrets.SecretsError, match="refusing to start"):
        secrets.read_secret("claude_oauth", p)


def test_dir_with_wrong_mode_refuses(tmp_path):
    assert secrets.check_key_file(make(tmp_path, dir_mode=0o755))


def test_wrong_owner_refuses(tmp_path):
    p = make(tmp_path)
    assert any("owned by uid" in x for x in secrets.check_key_file(p, uid=os.getuid() + 1))


def test_missing_and_symlinked_key_refuse(tmp_path):
    p = make(tmp_path)
    p.key.unlink()
    assert any("missing" in x for x in secrets.check_key_file(p))
    real = tmp_path / "real.key"
    real.write_text("x")
    real.chmod(0o600)
    p.key.symlink_to(real)
    assert secrets.check_key_file(p)


def test_missing_enc_file_refuses(tmp_path):
    with pytest.raises(secrets.SecretsError, match="secrets file"):
        secrets.read_secret("claude_oauth", make(tmp_path, enc=False))


def fake_sops(monkeypatch, rc=0, out=TOKEN + "\n"):
    seen = {}

    def run(args, **kw):
        seen.update(kw, args=args)
        return subprocess.CompletedProcess(args, rc, out, "stderr " + TOKEN)

    monkeypatch.setattr(secrets.subprocess, "run", run)
    return seen


def test_read_secret_uses_stdout_key_env_and_no_value_in_argv(tmp_path, monkeypatch):
    p = make(tmp_path)
    seen = fake_sops(monkeypatch)
    assert secrets.read_secret("claude_oauth", p) == TOKEN
    assert seen["args"][:3] == ["sops", "decrypt", "--extract"] and seen["args"][3] == '["claude_oauth"]'
    assert all(TOKEN not in a for a in seen["args"])
    assert seen["env"]["SOPS_AGE_KEY_FILE"] == str(p.key)


def test_sops_failure_and_empty_value_never_leak(tmp_path, monkeypatch):
    p = make(tmp_path)
    fake_sops(monkeypatch, rc=128)
    with pytest.raises(secrets.SecretsError) as e:
        secrets.read_secret("claude_oauth", p)
    assert TOKEN not in str(e.value) and "stderr" not in str(e.value)
    fake_sops(monkeypatch, out="\n")
    with pytest.raises(secrets.SecretsError, match="empty"):
        secrets.read_secret("claude_oauth", p)


def test_sops_not_installed(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("sops")

    monkeypatch.setattr(secrets.subprocess, "run", boom)
    with pytest.raises(secrets.SecretsError, match="sops"):
        secrets.read_secret("claude_oauth", make(tmp_path))


def test_doctor_reports_bad_key_file_and_exits_nonzero(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AIWF_CONFIG_DIR", str(make(tmp_path, key_mode=0o644).directory))
    monkeypatch.setattr(doctor, "CHECKS", [("key-file", doctor.check_key_file)])
    assert doctor.main() == 1
    assert "FAIL key-file" in capsys.readouterr().out
    monkeypatch.setattr(doctor, "CHECKS", [("ok", lambda: (True, "fine"))])
    assert doctor.main() == 0


def test_doctor_crashing_check_prints_type_only(monkeypatch, capsys):
    def crash():
        raise RuntimeError(TOKEN)

    monkeypatch.setattr(doctor, "CHECKS", [("x", crash)])
    assert doctor.main() == 1
    out = capsys.readouterr().out
    assert "RuntimeError" in out and TOKEN not in out


def test_doctor_decrypt_check_hides_value(tmp_path, monkeypatch):
    monkeypatch.setenv("AIWF_CONFIG_DIR", str(make(tmp_path).directory))
    fake_sops(monkeypatch)
    ok, msg = doctor.check_decrypt()
    assert ok and TOKEN not in msg


def test_launchd_plist_template():
    path = Path(__file__).parent.parent / "templates" / "factory" / "com.esciara.aiwf-factory.plist"
    plist = plistlib.loads(path.read_bytes())
    assert plist["UserName"] == "factory" and plist["RunAtLoad"] is True
    assert plist["Umask"] == 0o077 and plist["WorkingDirectory"].endswith("/factory/src")
    assert plist["ProgramArguments"][-2:] == ["aiwf.factory", "run"]
    assert "/opt/homebrew/bin" in plist["EnvironmentVariables"]["PATH"]
    text = path.read_text()
    assert "sk-ant" not in text and "CLAUDE_CODE_OAUTH_TOKEN" not in text and "BEGIN" not in text
