"""Regenerate the mermaid blocks of docs/diagrams.md from docs/diagrams/<name>.mmd (block `generated:<name>`).

Per-WP diagrams `docs/diagrams/wp<N>[x].mmd` (ADR-0048) all go into one block, `generated:per-wp`: one section per diagram,
in the order of the WP table of docs/plan.md, with a heading (WP id and package, linked to its plan row), the row's Done
when and the diagram. A per-WP stem with no plan row is an error. A track adds only the `.mmd`; no marker to place.

A diagram with `%% lane <lane>: WP0 WP1 ...` lines is a status view (ADR-0046): each listed WP node gets its class from
the bead status in docs/board.jsonl (`<lane>` not started, `<lane>Wip` in progress, `<lane>Done` done), a click link to
its row in the WP table of docs/plan.md, and the same links as a table in block `generated:<name>-links`. Status classes,
`class` and `click` lines are never hand-typed in such a diagram; the renderer refuses them.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from aiwf import board, gendoc

ROOT = Path(__file__).resolve().parents[2]
DIAGRAMS_PATH = ROOT / "docs" / "diagrams.md"
SOURCES_DIR = ROOT / "docs" / "diagrams"
PLAN_PATH = ROOT / "docs" / "plan.md"
PLAN_URL = "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1"

LANE = re.compile(r"^\s*%%\s*lane\s+(\w+)\s*:(.*)$")
NODE = re.compile(r"\b(WP\d+)\[")
HAND_STATUS = re.compile(r":::|^\s*(class|click)\s", re.M)
PLAN_ROW = re.compile(r"^\| (WP\d+[a-z]?) \|")
PER_WP = re.compile(r"^wp\d", re.I)
PER_WP_BLOCK = "per-wp"
WIP = frozenset({"in_progress", "in_review"})
SUFFIX = {"done": "Done", "wip": "Wip", "todo": ""}


class DiagramError(gendoc.GenDocError):
    pass


def plan_rows(plan_text: str) -> dict[str, int]:
    """1-based line of each `| WP<n> |` row of the WP table in docs/plan.md."""
    return {m.group(1): n for n, line in enumerate(plan_text.splitlines(), 1) if (m := PLAN_ROW.match(line))}


def plan_cells(plan_text: str) -> dict[str, tuple[int, str, str]]:
    """WP id -> (1-based line, Package, Done when) for each `| WP<n> |` row of the WP table in docs/plan.md."""
    lines = plan_text.splitlines()
    out: dict[str, tuple[int, str, str]] = {}
    cols: list[str] = []
    for n, line in enumerate(lines, 1):
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.startswith("|") else []
        if "Package" in cells and "Done when" in cells:
            cols = cells
        elif cols and PLAN_ROW.match(line) and len(cells) == len(cols):
            out[cells[0]] = (n, cells[cols.index("Package")], cells[cols.index("Done when")])
    if missing := sorted(set(plan_rows(plan_text)) - set(out)):
        raise DiagramError(f"docs/plan.md: WP row(s) {', '.join(missing)} not under a header with Package and Done when")
    return out


def per_wp_section(wp: str, body: str, row: tuple[int, str, str]) -> str:
    line, package, done = row
    return "\n".join([
        f"## {wp} — {package}",
        "",
        f"Done when ([docs/plan.md, line {line}]({PLAN_URL}#L{line})): {done}",
        "",
        f"```mermaid\n{body}\n```",
    ])


def per_wp(sources: list[tuple[str, str]], plan_text: str | None) -> str:
    """The `generated:per-wp` block: one section per (stem, body), in plan order."""
    if plan_text is None:
        raise DiagramError("per-WP diagrams need docs/plan.md")
    rows = plan_cells(plan_text)
    order = {wp: i for i, wp in enumerate(rows)}
    sections = []
    for stem, body in sources:
        wp = "WP" + stem[2:]
        if wp not in rows:
            raise DiagramError(f"{stem}.mmd: no {wp} row in the WP table of docs/plan.md; name it after a plan row (wp<N>.mmd or wp<N><x>.mmd for a split)")
        sections.append((order[wp], per_wp_section(wp, body, rows[wp])))
    return "\n\n".join(text for _, text in sorted(sections))


def lanes(body: str) -> dict[str, str]:
    """WP node -> lane, from the `%% lane` lines."""
    out: dict[str, str] = {}
    for line in body.splitlines():
        if m := LANE.match(line):
            for wp in m.group(2).split():
                if wp in out:
                    raise DiagramError(f"{wp} is in two lanes ({out[wp]}, {m.group(1)})")
                out[wp] = m.group(1)
    return out


def status(wp: str, records: list[dict]) -> str:
    """'done', 'wip' or 'todo' for a WP from its bead and its split beads.

    Done only when the WP bead and all its splits are closed. In progress when the WP bead or a split is in progress or in
    review, or when some of them are closed and others not (e.g. WP bead closed with a split still open). Else not started.
    """
    bead = board.work_package_beads(records).get(wp)
    if bead is None:
        raise DiagramError(f"no bead with metadata.wp {wp!r} in docs/board.jsonl")
    parts = board.splits(records).get(bead["id"], [])
    states = [bead["status"], *(p["status"] for p in parts)]
    if all(s == "closed" for s in states):
        return "done"
    if WIP & set(states) or "closed" in states:
        return "wip"
    return "todo"


def status_view(name: str, body: str, records: list[dict] | None, plan_text: str | None) -> tuple[str, str]:
    """(mermaid body with click and class lines appended, links table) for a diagram with lanes."""
    if m := HAND_STATUS.search(body):
        line = body[: m.start()].count("\n") + 1
        raise DiagramError(f"{name}.mmd:{line}: status classes, class and click lines are generated from the board; remove them")
    if records is None:
        raise DiagramError(f"{name}.mmd needs docs/board.jsonl (run scripts/dev/render-progress first, or `bd import` it)")
    if plan_text is None:
        raise DiagramError(f"{name}.mmd needs docs/plan.md")
    lane_of = lanes(body)
    nodes = list(dict.fromkeys(NODE.findall(body)))
    if missing := [wp for wp in nodes if wp not in lane_of]:
        raise DiagramError(f"{name}.mmd: no lane for {', '.join(missing)}")
    if unknown := sorted(set(lane_of) - set(nodes)):
        raise DiagramError(f"{name}.mmd: lane lists unknown node(s) {', '.join(unknown)}")
    rows = plan_rows(plan_text)
    if missing := [wp for wp in nodes if wp not in rows]:
        raise DiagramError(f"no row for {', '.join(missing)} in the WP table of docs/plan.md")
    order = sorted(nodes, key=lambda wp: int(wp[2:]))
    clicks = [f'  click {wp} "{PLAN_URL}#L{rows[wp]}" "Open {wp} in docs/plan.md" _blank' for wp in order]
    classes = [f"  class {wp} {lane_of[wp]}{SUFFIX[status(wp, records)]}" for wp in order]
    table = ["| WP | Definition |", "| --- | --- |"]
    table += [f"| {wp} | [docs/plan.md, line {rows[wp]}]({PLAN_URL}#L{rows[wp]}) |" for wp in order]
    return "\n".join([body, "", *clicks, "", *classes]), "\n".join(table)


def blocks(sources_dir: Path, records: list[dict] | None = None, plan_text: str | None = None) -> dict[str, str]:
    out = {}
    wps: list[tuple[str, str]] = []
    for src in sorted(sources_dir.glob("*.mmd")):
        body = src.read_text(encoding="utf-8").rstrip("\n")
        if "```" in body:
            raise gendoc.GenDocError(f"{src.name}: must not contain a code fence")
        if PER_WP.match(src.stem):
            if any(LANE.match(line) for line in body.splitlines()):
                raise DiagramError(f"{src.name}: lanes are for status views, not per-WP diagrams")
            wps.append((src.stem.lower(), body))
            continue
        if any(LANE.match(line) for line in body.splitlines()):
            body, out[f"{src.stem}-links"] = status_view(src.stem, body, records, plan_text)
        out[src.stem] = f"```mermaid\n{body}\n```"
    if wps:
        out[PER_WP_BLOCK] = per_wp(wps, plan_text)
    return out


def render(text: str, sources_dir: Path, records: list[dict] | None = None, plan_text: str | None = None) -> str:
    return gendoc.replace_blocks(text, blocks(sources_dir, records, plan_text))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="render-diagrams", description=__doc__.splitlines()[0])
    ap.add_argument("--file", default=str(DIAGRAMS_PATH), help="diagrams file to update")
    ap.add_argument("--sources", default=str(SOURCES_DIR), help="directory of .mmd sources")
    ap.add_argument("--board", default=str(board.BOARD_PATH), help="board export for the status views (default docs/board.jsonl)")
    ap.add_argument("--plan", default=str(PLAN_PATH), help="plan whose WP table the click links point at")
    args = ap.parse_args(argv)
    target, board_path, plan_path = Path(args.file), Path(args.board), Path(args.plan)
    try:
        records = board.parse(board_path.read_text(encoding="utf-8")) if board_path.is_file() else None
        plan_text = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else None
        old = target.read_text(encoding="utf-8")
        new = render(old, Path(args.sources), records, plan_text)
    except (gendoc.GenDocError, board.BoardError, OSError) as exc:
        print(f"render-diagrams: {exc}", file=sys.stderr)
        return 2
    if new != old:
        target.write_text(new, encoding="utf-8")
        print(f"updated {target}")
    return 0
