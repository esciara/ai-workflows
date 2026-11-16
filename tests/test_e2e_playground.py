"""The e2e helper's 404 retry (no network: `api` is replaced)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "e2e"))
import playground  # noqa: E402


def fake_api(results):
    calls = []

    def api(path, *a, **k):
        calls.append(path)
        r = results.pop(0)
        if isinstance(r, str):
            pytest.fail(r, pytrace=False)
        return r

    return api, calls


def test_retries_404_then_succeeds(monkeypatch):
    api, calls = fake_api(["gh: Not Found (HTTP 404)", "gh: Not Found (HTTP 404)", {"ok": 1}])
    monkeypatch.setattr(playground, "api", api)
    slept = []
    assert playground.api_retry_404("p", sleep=slept.append) == {"ok": 1}
    assert len(calls) == 3 and slept == [3, 3]


def test_other_failure_is_immediate(monkeypatch):
    api, calls = fake_api(["gh: Server Error (HTTP 500)", {"ok": 1}])
    monkeypatch.setattr(playground, "api", api)
    with pytest.raises(pytest.fail.Exception):
        playground.api_retry_404("p", sleep=lambda s: None)
    assert len(calls) == 1


def test_gives_up_after_timeout(monkeypatch):
    api, calls = fake_api(["gh: Not Found (HTTP 404)"] * 50)
    monkeypatch.setattr(playground, "api", api)
    with pytest.raises(pytest.fail.Exception):
        playground.api_retry_404("p", timeout=0, sleep=lambda s: None)
    assert len(calls) == 1
