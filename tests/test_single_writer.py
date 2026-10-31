"""Single writer for generated files (ADR-0015): only sync-* branches change them. Designed to run in CI later too."""

import subprocess

import pytest

from aiwf import generated

MARKED = "x\n<!-- BEGIN generated:t -->\n<!-- END generated:t -->\n"


def test_track_branch_changing_generated_files_is_a_violation():
    base = {"docs/progress.md": MARKED, "docs/board.jsonl": "", "docs/adr/README.md": MARKED, "docs/diagrams.md": MARKED}
    changed = ["docs/adr/0024-x.md", "docs/diagrams/wp2.mmd", "docs/progress.md", "docs/board.jsonl", "docs/adr/README.md", "docs/diagrams.md"]
    assert generated.violations("wp2-core-review", changed, base) == ["docs/adr/README.md", "docs/board.jsonl", "docs/diagrams.md", "docs/progress.md"]
    assert generated.violations("sync-2026-11-01", changed, base) == []
    assert generated.violations("wp2-core-review", ["docs/adr/0024-x.md", "docs/diagrams/wp2.mmd"], base) == []


def test_rule_applies_only_once_the_generator_is_on_the_base_branch():
    base = {"docs/progress.md": "hand-edited\n", "docs/board.jsonl": None, "docs/adr/README.md": MARKED, "docs/diagrams.md": None}
    changed = ["docs/progress.md", "docs/board.jsonl", "docs/adr/README.md", "docs/diagrams.md"]
    assert generated.violations("parallel-readiness", changed, base) == ["docs/adr/README.md"]


def test_this_branch_respects_the_single_writer_rule():
    bad = generated.check_branch()
    if bad is None:
        pytest.skip("origin/main not available")
    assert bad == [], f"generated files changed outside a sync-* branch: {bad}"


def test_stale_reports_out_of_date_generated_files(tmp_path):
    (tmp_path / "docs/adr").mkdir(parents=True)
    (tmp_path / "docs/diagrams").mkdir()
    (tmp_path / "docs/board.jsonl").write_text("")
    (tmp_path / "docs/progress.md").write_text("<!-- BEGIN generated:wp-table -->\n<!-- END generated:wp-table -->\n<!-- BEGIN generated:metrics -->\n<!-- END generated:metrics -->\n<!-- BEGIN generated:log -->\n<!-- END generated:log -->\n")
    (tmp_path / "docs/adr/README.md").write_text("<!-- BEGIN generated:adr-index -->\n<!-- END generated:adr-index -->\n")
    (tmp_path / "docs/diagrams.md").write_text("")
    msgs = generated.stale(tmp_path, fresh_export='{"id":"a"}\n')
    assert msgs == ["docs/board.jsonl differs from the local beads board", "docs/progress.md is out of date with its sources", "docs/adr/README.md is out of date with its sources"]


@pytest.mark.parametrize("branch, checked", [("sync-2026-11-01", True), ("main", False), ("wp2-foo", False), ("HEAD", False)])
def test_freshness_is_checked_only_on_sync_branches(branch, checked):
    assert generated.freshness_checked(branch) is checked


@pytest.mark.parametrize(
    "env, expected",
    [
        ({"GITHUB_HEAD_REF": "wp2-foo", "GITHUB_REF_NAME": "19/merge"}, "wp2-foo"),
        ({"GITHUB_HEAD_REF": "", "GITHUB_REF_NAME": "main"}, "main"),
        ({}, "local-branch"),
    ],
)
def test_current_branch_prefers_actions_env_then_git(monkeypatch, env, expected):
    for k in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(generated, "_git", lambda root, *a: subprocess.CompletedProcess(a, 0, "local-branch\n", ""))
    assert generated.current_branch() == expected


def test_repo_generated_files_are_up_to_date():
    branch = generated.current_branch()
    if not generated.freshness_checked(branch):
        pytest.skip(f"{branch}: generated files are checked fresh only on sync-* branches (ADR-0015)")
    assert generated.stale() == []
