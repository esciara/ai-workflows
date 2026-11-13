"""Slot locks never land in the working directory (a file named `any` was once committed by mistake)."""

from aiwf import e2eslot


def test_hold_any_writes_only_the_numbered_lock_file(tmp_path, monkeypatch):
    lock_dir, cwd = tmp_path / "locks", tmp_path / "cwd"
    lock_dir.mkdir()
    cwd.mkdir()
    monkeypatch.setenv("AIWF_E2E_LOCK_DIR", str(lock_dir))
    monkeypatch.chdir(cwd)
    with e2eslot.hold("any", timeout=0) as n:
        assert e2eslot.lock_path(n).parent == lock_dir
    assert list(cwd.iterdir()) == []
    assert not (lock_dir / "any").exists()
