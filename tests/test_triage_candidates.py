"""`aiwf triage-candidates` (triage.cmd_candidates): pass 1's JSON in, pass 2's context file and range confidence out."""

import argparse
import json

import pytest

from aiwf import config, triage
from ghfake import RecordingGh

REPO = "o/r"
EXTRACT = {"reported_version": None, "search_phrases": ["total is wrong"], "file_paths": [], "suspicious_instructions": []}


class Github(RecordingGh):
    """Enough of GitHub for one issue: no duplicates, no tags or releases, three commits on `main`."""

    def respond(self, args):
        path = args[-1]
        if path == f"repos/{REPO}/issues/5":
            return json.dumps({"number": 5, "title": "Total wrong", "body": "after removing items", "state": "open"})
        if path.startswith("search/issues"):
            return json.dumps({"items": []})
        if "/tags" in path or "/releases/latest" in path:
            raise RuntimeError("HTTP 404")
        if "/commits?sha=main" in path:
            return json.dumps([{"sha": f"{i}" * 40, "commit": {"message": f"fix #5 step {i}\n\nbody",
                                                                "committer": {"date": "2026-01-01T00:00:00Z"}}}
                               for i in range(3)])
        raise AssertionError(path)


def args_for(tmp_path, github_output=None):
    return argparse.Namespace(repo=REPO, issue=5, out=str(tmp_path / "ctx.md"), github_output=github_output)


@pytest.fixture
def github(monkeypatch):
    gh = Github()
    monkeypatch.setattr(config, "run_gh", gh)
    monkeypatch.setenv("AIWF_CONFIG", json.dumps({"default_branch": "main"}))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    return gh


def test_writes_the_context_and_the_range_confidence(github, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("EXTRACT_JSON", json.dumps(EXTRACT))
    out = tmp_path / "gh_output"
    assert triage.cmd_candidates(args_for(tmp_path, str(out))) == 0
    ctx = (tmp_path / "ctx.md").read_text()
    assert "## Issue under triage" in ctx and "title: Total wrong" in ctx
    assert "commit 111111111111 fix #5 step 1 [fixes refs: #5]" in ctx  # fix refs to this issue are kept
    rc_line, cand_line = out.read_text().splitlines()
    assert rc_line == "range_confidence=low"  # no tag, no release: the fallback range
    listed = json.loads(cand_line.removeprefix("candidates="))  # what publish accepts (aiwf-wqn)
    assert len(listed["commits"]) == 3 and all(len(s) == 40 for s in listed["commits"]) and listed["prs"] == []
    assert "3 commits" in capsys.readouterr().out


def test_github_output_falls_back_to_the_env_var(github, monkeypatch, tmp_path):
    monkeypatch.setenv("EXTRACT_JSON", json.dumps(EXTRACT))
    out = tmp_path / "env_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert triage.cmd_candidates(args_for(tmp_path)) == 0
    assert out.read_text().splitlines()[0] == "range_confidence=low"


@pytest.mark.parametrize("raw", ["", "not json", "{}", json.dumps({**EXTRACT, "extra": 1})])
def test_invalid_extractor_output_fails_before_any_github_call(github, monkeypatch, tmp_path, capsys, raw):
    monkeypatch.setenv("EXTRACT_JSON", raw)
    assert triage.cmd_candidates(args_for(tmp_path)) == 1
    assert "::error title=Invalid agent output (extractor)::" in capsys.readouterr().out
    assert github.calls == [] and not (tmp_path / "ctx.md").exists()


def test_missing_extract_env_is_invalid_output(github, monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("EXTRACT_JSON", raising=False)
    assert triage.cmd_candidates(args_for(tmp_path)) == 1
    assert "Invalid agent output" in capsys.readouterr().out
