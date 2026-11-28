import pytest

from aiwf.factory import m0


@pytest.fixture(autouse=True)
def _no_real_keychain(monkeypatch):
    """Never run the real `security unlock-keychain` from a test; test_factory_keychain.py overrides this to test the real function."""
    monkeypatch.setattr(m0, "unlock_keychain", lambda: (True, "skipped: test"))
