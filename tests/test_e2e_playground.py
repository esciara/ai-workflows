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


class FakeRun:
    def __init__(self, results):
        self.results, self.calls = results, []

    def __call__(self, cmd, **k):
        self.calls.append(cmd)
        rc, err = self.results.pop(0)
        return type("P", (), {"returncode": rc, "stdout": "out", "stderr": err})()


def gh_with(monkeypatch, results):
    run, slept = FakeRun(results), []
    monkeypatch.setattr(playground.subprocess, "run", run)
    monkeypatch.setattr(playground.time, "sleep", slept.append)
    return run, slept


def test_gh_read_retries_5xx_with_backoff(monkeypatch):
    run, slept = gh_with(monkeypatch, [(1, "gh: Bad Gateway (HTTP 502)"), (1, "HTTP 503"), (0, "")])
    assert playground.gh(["api", "x"]) == "out"
    assert len(run.calls) == 3 and slept == [2, 5]


def test_gh_read_gives_up_after_three_attempts(monkeypatch):
    run, slept = gh_with(monkeypatch, [(1, "HTTP 502")] * 3)
    with pytest.raises(pytest.fail.Exception, match="GitHub call failed"):
        playground.gh(["api", "x"])
    assert len(run.calls) == 3


def test_gh_read_does_not_retry_non_5xx(monkeypatch):
    run, slept = gh_with(monkeypatch, [(1, "HTTP 404")])
    with pytest.raises(pytest.fail.Exception):
        playground.gh(["api", "x"])
    assert len(run.calls) == 1 and slept == []


@pytest.mark.parametrize("who", ["as_agent", "as_tester", "as_maintainer"])
def test_gh_write_never_retried(monkeypatch, who):
    run, slept = gh_with(monkeypatch, [(1, "HTTP 502")])
    with pytest.raises(pytest.fail.Exception):
        playground.gh(["api", "x"], **{who: True})
    assert len(run.calls) == 1 and slept == []
