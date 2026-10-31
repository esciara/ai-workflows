import pytest

from aiwf import board as boardmod
from aiwf import gendoc, progress

SCAN = boardmod.scan_secrets


def bead(wp, title, status="open", deps=(), **meta):
    issue = {"id": f"aiwf-{wp.lower()}", "title": title, "status": status, "metadata": {"wp": wp, **meta}}
    issue["dependencies"] = [{"issue_id": issue["id"], "depends_on_id": d, "type": "blocks"} for d in deps]
    return issue


BOARD = [
    bead("WP10", "B6 · PR into A", deps=["aiwf-wp9", "aiwf-wp3"]),
    bead("WP3", "A · formal review", status="in_review", deps=["aiwf-wp0"], pr="[#5](u)"),
    bead("WP9", "B5 · fix loop", status="in_progress", deps=["aiwf-wp0"]),
    bead(
        "WP0",
        "Repo bootstrap",
        status="closed",
        pr="[#2](u)",
        notes="Python 3.12",
        log=["2026-10-30 · WP0 · [#2](u) · green"],
        metrics={"maintainer_interventions": "1", "verifier_fails": "0", "rework_prs": "0", "coordination_issues": "0", "notes": "a | b"},
    ),
    {"id": "aiwf-wp14.1", "title": "follow-up", "status": "open", "parent": "aiwf-wp14"},
    {"id": "aiwf-merge-slot", "title": "Merge Slot", "status": "in_progress", "metadata": {"holder": "x"}},
]

DOC = """# Progress

<!-- BEGIN generated:wp-table (note) -->
stale
<!-- END generated:wp-table -->

## Metrics

<!-- BEGIN generated:metrics -->
<!-- END generated:metrics -->

## Log

<!-- BEGIN generated:log -->
- old
<!-- END generated:log -->
"""


def test_wp_table_orders_by_number_maps_status_and_sorts_deps():
    lines = progress.wp_table(BOARD).splitlines()
    assert lines[0] == "| WP | Package | Depends on | Status | PR | Notes |"
    assert lines[2:] == [
        "| WP0 | Repo bootstrap | — | done | [#2](u) | Python 3.12 |",
        "| WP3 | A · formal review | WP0 | in review | [#5](u) | |",
        "| WP9 | B5 · fix loop | WP0 | in progress | | |",
        "| WP10 | B6 · PR into A | WP3, WP9 | todo | | |",
    ]


def test_metrics_only_for_beads_with_metrics_and_pipes_escaped():
    lines = progress.metrics_table(BOARD).splitlines()
    assert lines[0] == "| WP | maintainer interventions | verifier fails | rework PRs | coordination issues | notes |"
    assert lines[2:] == ["| WP0 | 1 | 0 | 0 | 0 | a \\| b |"]


def test_render_replaces_only_generated_blocks():
    out = progress.render(DOC, BOARD)
    assert out.startswith("# Progress\n\n<!-- BEGIN generated:wp-table (note) -->\n| WP | Package")
    assert "stale" not in out and "- old" not in out
    assert "<!-- BEGIN generated:log -->\n- 2026-10-30 · WP0 · [#2](u) · green\n<!-- END generated:log -->" in out
    assert progress.render(out, BOARD) == out


def test_unknown_status_and_duplicate_wp_are_errors():
    with pytest.raises(progress.BoardError):
        progress.wp_table([bead("WP1", "x", status="weird")])
    with pytest.raises(progress.BoardError):
        progress.wp_table([bead("WP1", "x"), bead("WP1", "y")])


def test_missing_marker_is_an_error():
    with pytest.raises(gendoc.GenDocError):
        progress.render("# Progress\n", BOARD)


def test_main_check_and_write_from_export(tmp_path):
    board, doc = tmp_path / "board.jsonl", tmp_path / "progress.md"
    board.write_text(boardmod.dumps(BOARD))
    doc.write_text(DOC)
    args = ["--board", str(board), "--file", str(doc)]
    assert progress.main([*args, "--check"]) == 1
    assert doc.read_text() == DOC
    assert progress.main([*args, "--no-export"]) == 0
    assert progress.main([*args, "--check"]) == 0


def test_main_exports_scans_then_writes(tmp_path, monkeypatch):
    board, doc = tmp_path / "board.jsonl", tmp_path / "progress.md"
    doc.write_text(DOC)
    export = boardmod.dumps(boardmod.normalize(BOARD))
    monkeypatch.setattr(boardmod, "fresh_export", lambda: export)
    monkeypatch.setattr(boardmod, "scan_secrets", lambda text: [])
    assert progress.main(["--board", str(board), "--file", str(doc)]) == 0
    assert board.read_text() == export
    assert progress.main(["--board", str(board), "--file", str(doc), "--check"]) == 0


def test_main_refuses_to_write_on_secret_or_missing_scanner(tmp_path, monkeypatch, capsys):
    board, doc = tmp_path / "board.jsonl", tmp_path / "progress.md"
    doc.write_text(DOC)
    monkeypatch.setattr(boardmod, "fresh_export", lambda: boardmod.dumps(BOARD))
    monkeypatch.setattr(boardmod, "scan_secrets", lambda text: ["github-pat"])
    assert progress.main(["--board", str(board), "--file", str(doc)]) == 2
    assert "github-pat" in capsys.readouterr().err
    monkeypatch.setattr(boardmod.shutil, "which", lambda name: None)
    monkeypatch.setattr(boardmod, "scan_secrets", SCAN)
    assert progress.main(["--board", str(board), "--file", str(doc)]) == 2
    assert "gitleaks not installed" in capsys.readouterr().err
    assert not board.exists() and doc.read_text() == DOC


def test_repo_progress_matches_committed_export():
    assert progress.main(["--check"]) == 0


def test_repo_progress_file_has_all_generated_blocks():
    text = progress.PROGRESS_PATH.read_text()
    assert gendoc.block_names(text) == ["wp-table", "metrics", "log"]
