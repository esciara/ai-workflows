import json
import random
import shutil
import string

import pytest

from aiwf import board

RAW = [
    {"id": "aiwf-wp2", "title": "B", "status": "in_progress", "assignee": "track-aiwf-wp2", "updated_at": "t1", "lease_expires_at": "t2", "heartbeat_at": "t3", "owner": "me@example.com", "labels": ["wp"]},
    {"id": "aiwf-merge-slot", "title": "Merge Slot", "status": "in_progress", "labels": ["gt:slot"], "metadata": {"holder": "x"}},
    {"id": "aiwf-wp10", "title": "A", "status": "open", "metadata": {"wp": "WP10"}},
]


def test_normalize_drops_volatile_fields_and_merge_slot_and_sorts_by_id():
    out = board.normalize(RAW)
    assert [r["id"] for r in out] == ["aiwf-wp10", "aiwf-wp2"]
    assert out[1] == {"id": "aiwf-wp2", "title": "B", "status": "in_progress", "assignee": "track-aiwf-wp2", "labels": ["wp"]}


def test_export_is_stable_when_only_volatile_fields_change():
    again = [dict(r, updated_at="later", heartbeat_at="later", lease_expires_at="later") for r in reversed(RAW)]
    assert board.dumps(board.normalize(RAW)) == board.dumps(board.normalize(again))


def test_dumps_parse_round_trip_and_errors():
    recs = board.normalize(RAW)
    text = board.dumps(recs)
    assert text.endswith("\n") and len(text.splitlines()) == 2
    assert board.parse(text) == recs
    with pytest.raises(board.BoardError, match="line 1"):
        board.parse("{nope\n")
    with pytest.raises(board.BoardError, match="id"):
        board.parse("[1]\n")


def test_fresh_export_normalizes_bd_output(monkeypatch):
    class Done:
        stdout = "".join(json.dumps(r) + "\n" for r in RAW)

    calls = []
    monkeypatch.setattr(board.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or Done())
    assert board.fresh_export() == board.dumps(board.normalize(RAW))
    assert calls == [["bd", "export"]]


def test_scan_without_gitleaks_is_an_error(monkeypatch):
    monkeypatch.setattr(board.shutil, "which", lambda name: None)
    with pytest.raises(board.SecretScanError, match="gitleaks not installed"):
        board.scan_secrets("x")


@pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks not installed")
def test_scan_finds_a_token_and_passes_clean_text():
    rng = random.Random(1)
    token = "ghp_" + "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(36))  # built at runtime: no secret-shaped literal in git
    assert board.scan_secrets(json.dumps({"description": f"token {token}"}) + "\n") == ["github-pat"]
    assert board.scan_secrets(board.dumps(board.normalize(RAW))) == []


def test_committed_export_is_normalized_and_clean():
    text = board.BOARD_PATH.read_text(encoding="utf-8")
    assert board.dumps(board.normalize(board.parse(text))) == text
