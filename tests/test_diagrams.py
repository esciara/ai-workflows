import json

import pytest

from aiwf import board as boardmod
from aiwf import diagrams, gendoc

DOC = """# Diagrams

<!-- BEGIN generated:a (from a.mmd) -->
```mermaid
old
```
<!-- END generated:a -->

text between

<!-- BEGIN generated:b -->
<!-- END generated:b -->
"""


def test_render_puts_each_source_in_its_block(tmp_path):
    (tmp_path / "a.mmd").write_text("flowchart TD\n  A --> B\n")
    (tmp_path / "b.mmd").write_text("flowchart LR\n  C")
    out = diagrams.render(DOC, tmp_path)
    assert "<!-- BEGIN generated:a (from a.mmd) -->\n```mermaid\nflowchart TD\n  A --> B\n```\n<!-- END generated:a -->" in out
    assert "<!-- BEGIN generated:b -->\n```mermaid\nflowchart LR\n  C\n```\n<!-- END generated:b -->" in out
    assert "old" not in out and "text between" in out
    assert diagrams.render(out, tmp_path) == out


def test_source_without_block_and_block_without_source_are_errors(tmp_path):
    (tmp_path / "a.mmd").write_text("x")
    with pytest.raises(gendoc.GenDocError, match="no content.*b"):
        diagrams.render(DOC, tmp_path)
    (tmp_path / "b.mmd").write_text("x")
    (tmp_path / "c.mmd").write_text("x")
    with pytest.raises(gendoc.GenDocError, match="no marker.*c"):
        diagrams.render(DOC, tmp_path)


def test_fence_in_source_is_an_error(tmp_path):
    (tmp_path / "a.mmd").write_text("```")
    (tmp_path / "b.mmd").write_text("x")
    with pytest.raises(gendoc.GenDocError):
        diagrams.render(DOC, tmp_path)


def test_main_writes(tmp_path):
    (tmp_path / "a.mmd").write_text("A")
    (tmp_path / "b.mmd").write_text("B")
    doc = tmp_path / "diagrams.md"
    doc.write_text(DOC)
    assert diagrams.main(["--file", str(doc), "--sources", str(tmp_path)]) == 0
    assert doc.read_text() == diagrams.render(DOC, tmp_path)


# status views (ADR-0046)

PLAN = "# Plan\n\n| ID | Package |\n| --- | --- |\n| WP0 | a |\n| WP1 | b |\n| WP2 | c |\n"
LANE_MMD = """flowchart TD
  %% lane base: WP0
  %% lane a: WP1 WP2
  WP0["WP0 x"] --> WP1["WP1 y"]
  WP1 --> WP2["WP2 z"]
  classDef a fill:#fff
"""
LANE_DOC = """<!-- BEGIN generated:overview -->
<!-- END generated:overview -->

<!-- BEGIN generated:overview-links -->
<!-- END generated:overview-links -->
"""


def wp(n, status, **extra):
    return {"id": f"aiwf-wp{n}", "title": f"WP{n}", "status": status, "metadata": {"wp": f"WP{n}"}, **extra}


def split(sid, parent, status):
    return {"id": f"{parent}.{sid}", "title": f"WP{sid} · part", "status": status, "dependencies": [{"type": "parent-child", "depends_on_id": parent}]}


BOARD = [wp(0, "closed"), wp(1, "in_review"), wp(2, "open")]


def lane_sources(tmp_path, mmd=LANE_MMD):
    (tmp_path / "overview.mmd").write_text(mmd)
    return tmp_path


def test_status_view_injects_classes_clicks_and_links_table(tmp_path):
    out = diagrams.render(LANE_DOC, lane_sources(tmp_path), BOARD, PLAN)
    assert "  class WP0 baseDone\n  class WP1 aWip\n  class WP2 a\n```" in out
    assert f'  click WP2 "{diagrams.PLAN_URL}#L7" "Open WP2 in docs/plan.md" _blank' in out
    assert f"| WP0 | [docs/plan.md, line 5]({diagrams.PLAN_URL}#L5) |\n| WP1 |" in out
    assert "%% lane a: WP1 WP2" in out  # the lane lines stay; mermaid ignores %% comments
    assert diagrams.render(out, tmp_path, BOARD, PLAN) == out


@pytest.mark.parametrize("line", ['  WP0["x"]:::done', "  class WP0 done", '  click WP0 "u"'])
def test_hand_typed_status_or_links_are_errors(tmp_path, line):
    lane_sources(tmp_path, LANE_MMD + line + "\n")
    with pytest.raises(diagrams.DiagramError, match="overview.mmd:7: .*generated"):
        diagrams.render(LANE_DOC, tmp_path, BOARD, PLAN)


def test_node_without_lane_unknown_lane_node_and_two_lanes_are_errors(tmp_path):
    lane_sources(tmp_path, LANE_MMD.replace(" WP1 WP2\n", " WP1\n"))
    with pytest.raises(diagrams.DiagramError, match="no lane for WP2"):
        diagrams.render(LANE_DOC, tmp_path, BOARD, PLAN)
    lane_sources(tmp_path, LANE_MMD.replace(" WP1 WP2\n", " WP1 WP2 WP9\n"))
    with pytest.raises(diagrams.DiagramError, match="unknown node.*WP9"):
        diagrams.render(LANE_DOC, tmp_path, BOARD, PLAN)
    lane_sources(tmp_path, LANE_MMD.replace(" WP1 WP2\n", " WP0 WP1 WP2\n"))
    with pytest.raises(diagrams.DiagramError, match="two lanes"):
        diagrams.render(LANE_DOC, tmp_path, BOARD, PLAN)


def test_missing_plan_row_bead_or_board_are_errors(tmp_path):
    lane_sources(tmp_path)
    with pytest.raises(diagrams.DiagramError, match="no row for WP2"):
        diagrams.render(LANE_DOC, tmp_path, BOARD, PLAN.replace("| WP2 | c |\n", ""))
    with pytest.raises(diagrams.DiagramError, match="no bead .*WP2"):
        diagrams.render(LANE_DOC, tmp_path, BOARD[:2], PLAN)
    with pytest.raises(diagrams.DiagramError, match="needs docs/board.jsonl"):
        diagrams.render(LANE_DOC, tmp_path, None, PLAN)


def test_main_reports_missing_board(tmp_path, capsys):
    (tmp_path / "src").mkdir()
    src = lane_sources(tmp_path / "src")
    doc, plan = tmp_path / "diagrams.md", tmp_path / "plan.md"
    doc.write_text(LANE_DOC)
    plan.write_text(PLAN)
    args = ["--file", str(doc), "--sources", str(src), "--plan", str(plan), "--board", str(tmp_path / "none.jsonl")]
    assert diagrams.main(args) == 2
    assert "needs docs/board.jsonl" in capsys.readouterr().err
    (tmp_path / "board.jsonl").write_text("".join(json.dumps(r) + "\n" for r in BOARD))
    assert diagrams.main([*args[:-1], str(tmp_path / "board.jsonl")]) == 0
    assert "class WP1 aWip" in doc.read_text()


@pytest.mark.parametrize(
    ("parent", "parts", "expected"),
    [
        ("closed", [], "done"),
        ("closed", ["closed", "closed"], "done"),
        ("closed", ["closed", "open"], "wip"),  # parent closed with an open split: not done
        ("open", ["closed", "open"], "wip"),
        ("open", ["in_progress", "open"], "wip"),
        ("open", ["open", "open"], "todo"),
        ("in_review", [], "wip"),
        ("blocked", [], "todo"),
        ("open", [], "todo"),
    ],
)
def test_status_from_bead_and_splits(parent, parts, expected):
    records = [wp(2, parent), *(split(f"2{chr(97 + i)}", "aiwf-wp2", s) for i, s in enumerate(parts))]
    assert diagrams.status("WP2", records) == expected


def test_follow_up_children_do_not_count_as_splits():
    followup = {"id": "aiwf-wp2.9", "title": "Pin callers", "status": "open", "dependencies": [{"type": "parent-child", "depends_on_id": "aiwf-wp2"}]}
    assert diagrams.status("WP2", [wp(2, "closed"), followup]) == "done"


def test_repo_overview_renders_from_the_repo_board_and_plan():
    records = boardmod.parse(boardmod.BOARD_PATH.read_text())
    out = diagrams.render(diagrams.DIAGRAMS_PATH.read_text(), diagrams.SOURCES_DIR, records, diagrams.PLAN_PATH.read_text())
    assert "class WP0 baseDone" in out and ":::" not in out


# per-WP sections (ADR-0048)

WP_PLAN = """| ID | Package | Depends on | Delivers | Done when |
| --- | --- | --- | --- | --- |
| WP1 | Shared runtime | WP0 | x | `/ping` gets a reply |
| WP2 | A · core review | WP1 | x | one comment |
| WP2a | A · one pass | WP1 | x | one label |
| WP10 | B6 · PR into A | WP9 | x | verdict label |
"""
WP_DOC = "# D\n\n<!-- BEGIN generated:per-wp -->\nstale\n<!-- END generated:per-wp -->\n"


def test_per_wp_section_from_mmd_and_plan_row(tmp_path):
    (tmp_path / "wp1.mmd").write_text("flowchart TD\n  A --> B\n")
    out = diagrams.render(WP_DOC, tmp_path, None, WP_PLAN)
    assert "## WP1 — Shared runtime\n\n" in out
    assert f"Done when ([docs/plan.md, line 3]({diagrams.PLAN_URL}#L3)): `/ping` gets a reply\n\n```mermaid\nflowchart TD\n  A --> B\n```\n<!-- END" in out
    assert "stale" not in out
    assert diagrams.render(out, tmp_path, None, WP_PLAN) == out


def test_per_wp_sections_follow_plan_order_and_split_stems_work(tmp_path):
    for stem in ("wp10", "wp2a", "wp1", "wp2"):
        (tmp_path / f"{stem}.mmd").write_text(f"flowchart TD\n  {stem}")
    out = diagrams.render(WP_DOC, tmp_path, None, WP_PLAN)
    heads = [line for line in out.splitlines() if line.startswith("## ")]
    assert heads == ["## WP1 — Shared runtime", "## WP2 — A · core review", "## WP2a — A · one pass", "## WP10 — B6 · PR into A"]
    assert "#L5)): one label\n\n```mermaid\nflowchart TD\n  wp2a\n```" in out


def test_per_wp_stem_without_plan_row_is_an_error(tmp_path):
    (tmp_path / "wp4x.mmd").write_text("flowchart TD")
    with pytest.raises(diagrams.DiagramError, match="wp4x.mmd: no WP4x row"):
        diagrams.render(WP_DOC, tmp_path, None, WP_PLAN)
    with pytest.raises(diagrams.DiagramError, match="need docs/plan.md"):
        diagrams.render(WP_DOC, tmp_path, None, None)


def test_per_wp_diagrams_need_no_marker_of_their_own(tmp_path):
    (tmp_path / "a.mmd").write_text("A")
    (tmp_path / "wp1.mmd").write_text("W")
    doc = "<!-- BEGIN generated:a -->\n<!-- END generated:a -->\n" + WP_DOC
    out = diagrams.render(doc, tmp_path, None, WP_PLAN)
    assert "```mermaid\nA\n```" in out and "## WP1 — Shared runtime" in out
    with pytest.raises(diagrams.DiagramError, match="lanes are for status views"):
        (tmp_path / "wp2.mmd").write_text("flowchart TD\n  %% lane a: WP2\n")
        diagrams.render(doc, tmp_path, None, WP_PLAN)


def test_repo_per_wp_diagrams_render_into_the_per_wp_block():
    records = boardmod.parse(boardmod.BOARD_PATH.read_text())
    out = diagrams.render(diagrams.DIAGRAMS_PATH.read_text(), diagrams.SOURCES_DIR, records, diagrams.PLAN_PATH.read_text())
    for src in diagrams.SOURCES_DIR.glob("wp*.mmd"):
        assert f"## {'WP' + src.stem[2:]} — " in out
