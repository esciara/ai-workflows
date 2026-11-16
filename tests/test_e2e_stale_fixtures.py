import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "e2e"))

import calendar  # noqa: E402
import time  # noqa: E402

import playground as pg  # noqa: E402

NOW = calendar.timegm(time.strptime("2026-11-16T12:00:00Z", "%Y-%m-%dT%H:%M:%SZ"))


def issue(n, title, created, **extra):
    return {"number": n, "title": title, "created_at": created, **extra}


def test_closes_only_old_non_reused_e2e_issues():
    issues = [
        issue(1, "[e2e] WP8 handover ab: Coupon", "2026-11-16T08:00:00Z"),  # old: closed
        issue(2, "[e2e] WP8 handover cd: Coupon", "2026-11-16T11:00:00Z"),  # live run: kept
        issue(3, "[e2e] WP1 command fixture (x) (slot 1)", "2026-11-10T00:00:00Z"),  # reused: kept
        issue(4, "[e2e] WP12 foo", "2026-11-10T00:00:00Z"),  # WP12 is not WP1: closed
        issue(5, "Real issue", "2026-11-10T00:00:00Z"),  # not an e2e title: kept
        issue(6, "[e2e] WP5 pr", "2026-11-10T00:00:00Z", pull_request={}),  # PR: kept
    ]
    assert pg.stale_fixture_issues(issues, NOW) == [1, 4]


def test_close_stale_fixtures_pages_oldest_first_and_closes_the_stale(monkeypatch):
    import json
    import time as _t

    calls, closed = [], []
    old = _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime(_t.time() - 5 * 3600))
    new = _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime())

    def gh(args, **kw):
        calls.append(args)
        return "\n".join(json.dumps(i) for i in [issue(7, "[e2e] WP6 x", old), issue(8, "[e2e] WP6 y", new)])

    monkeypatch.setattr(pg, "gh", gh)
    monkeypatch.setattr(pg, "close_issue", closed.append)
    assert pg.close_stale_fixtures() == [7] and closed == [7]
    assert "--paginate" in calls[0] and "direction=asc" in calls[0][-1]


def test_cleanup_failure_is_not_fatal(monkeypatch, capsys):
    import pytest
    conftest = __import__("conftest")

    def boom():
        pytest.fail("gh down", pytrace=False)

    monkeypatch.setattr(pg, "close_stale_fixtures", boom)
    conftest.close_stale_best_effort()
    assert "cleanup skipped" in capsys.readouterr().out
