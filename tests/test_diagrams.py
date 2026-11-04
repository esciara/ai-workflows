import pytest

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


# status views (ADR-0046; status from the plan's Status column)

PLAN = "# Plan\n\n| ID | Package | Status |\n| --- | --- | --- |\n| WP0 | a | done |\n| WP1 | b | in progress |\n| WP2 | c | todo |\n"
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


def lane_sources(tmp_path, mmd=LANE_MMD):
    (tmp_path / "overview.mmd").write_text(mmd)
    return tmp_path


def test_status_view_injects_classes_clicks_and_links_table(tmp_path):
    out = diagrams.render(LANE_DOC, lane_sources(tmp_path), PLAN)
    assert "  class WP0 baseDone\n  class WP1 aWip\n  class WP2 a\n```" in out
    assert f'  click WP2 "{diagrams.PLAN_URL}#L7" "Open WP2 in docs/plan.md" _blank' in out
    assert f"| WP0 | [docs/plan.md, line 5]({diagrams.PLAN_URL}#L5) |\n| WP1 |" in out
    assert "%% lane a: WP1 WP2" in out  # the lane lines stay; mermaid ignores %% comments
    assert diagrams.render(out, tmp_path, PLAN) == out


@pytest.mark.parametrize("line", ['  WP0["x"]:::done', "  class WP0 done", '  click WP0 "u"'])
def test_hand_typed_status_or_links_are_errors(tmp_path, line):
    lane_sources(tmp_path, LANE_MMD + line + "\n")
    with pytest.raises(diagrams.DiagramError, match="overview.mmd:7: .*generated"):
        diagrams.render(LANE_DOC, tmp_path, PLAN)


def test_node_without_lane_unknown_lane_node_and_two_lanes_are_errors(tmp_path):
    lane_sources(tmp_path, LANE_MMD.replace(" WP1 WP2\n", " WP1\n"))
    with pytest.raises(diagrams.DiagramError, match="no lane for WP2"):
        diagrams.render(LANE_DOC, tmp_path, PLAN)
    lane_sources(tmp_path, LANE_MMD.replace(" WP1 WP2\n", " WP1 WP2 WP9\n"))
    with pytest.raises(diagrams.DiagramError, match="unknown node.*WP9"):
        diagrams.render(LANE_DOC, tmp_path, PLAN)
    lane_sources(tmp_path, LANE_MMD.replace(" WP1 WP2\n", " WP0 WP1 WP2\n"))
    with pytest.raises(diagrams.DiagramError, match="two lanes"):
        diagrams.render(LANE_DOC, tmp_path, PLAN)


def test_missing_plan_row_or_bad_status_are_errors(tmp_path):
    lane_sources(tmp_path)
    with pytest.raises(diagrams.DiagramError, match="no row for WP2"):
        diagrams.render(LANE_DOC, tmp_path, PLAN.replace("| WP2 | c | todo |\n", ""))
    with pytest.raises(diagrams.DiagramError, match="WP2 Status 'later'"):
        diagrams.render(LANE_DOC, tmp_path, PLAN.replace("| c | todo |", "| c | later |"))


@pytest.mark.parametrize(("cell", "expected"), [("done", "done"), ("in progress", "wip"), ("paused", "wip"), ("todo", "todo")])
def test_status_from_plan_status_column(cell, expected):
    assert diagrams.status("WP2", PLAN.replace("| c | todo |", f"| c | {cell} |")) == expected


def test_repo_overview_renders_from_the_repo_plan():
    out = diagrams.render(diagrams.DIAGRAMS_PATH.read_text(), diagrams.SOURCES_DIR, diagrams.PLAN_PATH.read_text())
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
    out = diagrams.render(WP_DOC, tmp_path, WP_PLAN)
    assert "## WP1 — Shared runtime\n\n" in out
    assert f"Done when ([docs/plan.md, line 3]({diagrams.PLAN_URL}#L3)): `/ping` gets a reply\n\n```mermaid\nflowchart TD\n  A --> B\n```\n<!-- END" in out
    assert "stale" not in out
    assert diagrams.render(out, tmp_path, WP_PLAN) == out


def test_per_wp_sections_follow_plan_order_and_split_stems_work(tmp_path):
    for stem in ("wp10", "wp2a", "wp1", "wp2"):
        (tmp_path / f"{stem}.mmd").write_text(f"flowchart TD\n  {stem}")
    out = diagrams.render(WP_DOC, tmp_path, WP_PLAN)
    heads = [line for line in out.splitlines() if line.startswith("## ")]
    assert heads == ["## WP1 — Shared runtime", "## WP2 — A · core review", "## WP2a — A · one pass", "## WP10 — B6 · PR into A"]
    assert "#L5)): one label\n\n```mermaid\nflowchart TD\n  wp2a\n```" in out


def test_per_wp_stem_without_plan_row_is_an_error(tmp_path):
    (tmp_path / "wp4x.mmd").write_text("flowchart TD")
    with pytest.raises(diagrams.DiagramError, match="wp4x.mmd: no WP4x row"):
        diagrams.render(WP_DOC, tmp_path, WP_PLAN)
    with pytest.raises(diagrams.DiagramError, match="need docs/plan.md"):
        diagrams.render(WP_DOC, tmp_path, None)


def test_per_wp_diagrams_need_no_marker_of_their_own(tmp_path):
    (tmp_path / "a.mmd").write_text("A")
    (tmp_path / "wp1.mmd").write_text("W")
    doc = "<!-- BEGIN generated:a -->\n<!-- END generated:a -->\n" + WP_DOC
    out = diagrams.render(doc, tmp_path, WP_PLAN)
    assert "```mermaid\nA\n```" in out and "## WP1 — Shared runtime" in out
    with pytest.raises(diagrams.DiagramError, match="lanes are for status views"):
        (tmp_path / "wp2.mmd").write_text("flowchart TD\n  %% lane a: WP2\n")
        diagrams.render(doc, tmp_path, WP_PLAN)


def test_repo_per_wp_diagrams_render_into_the_per_wp_block():
    out = diagrams.render(diagrams.DIAGRAMS_PATH.read_text(), diagrams.SOURCES_DIR, diagrams.PLAN_PATH.read_text())
    for src in diagrams.SOURCES_DIR.glob("wp*.mmd"):
        assert f"## {'WP' + src.stem[2:]} — " in out
