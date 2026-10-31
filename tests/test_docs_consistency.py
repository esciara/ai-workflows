"""Source-vs-source checks of the hand-written docs (ADR-0047). Never a render against its source: nothing here reads a
generated block, docs/board.jsonl, docs/progress.md or docs/diagrams.md, so no check can go stale between sync PRs.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADR_DIR = ROOT / "docs" / "adr"
PLAN = ROOT / "docs" / "plan.md"
OVERVIEW = ROOT / "docs" / "diagrams" / "overview.mmd"
KNOWN_ISSUES = ROOT / "docs" / "known-issues.md"

ADR_FILE = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")
ADR_REF = re.compile(r"ADR-(\d{4})")
HEADER = re.compile(r"^- (Status|Supersedes|Superseded by|Amends|Amended by): (.*)$")
STATUS = re.compile(r"^(Proposed|Accepted|Superseded by ADR-(\d{4}))$")
PLAN_ROW = re.compile(r"^\| (WP\d+)([a-z]?) \|")
WP_REF = re.compile(r"WP\d+[a-z]?")
EDGE = re.compile(r"\b(WP\d+)(?:\[[^\]]*\])?(?::::\w+)?\s*-->\s*(WP\d+)\b")
NODE = re.compile(r"\b(WP\d+)\[")


def adr_headers(adr_dir: Path = ADR_DIR) -> dict[str, dict[str, list[str]]]:
    """ADR number -> header field -> values (ADR numbers referenced; the raw text for Status). Header = lines before '## '."""
    out = {}
    for path in sorted(adr_dir.glob("*.md")):
        if not (m := ADR_FILE.match(path.name)):
            continue
        fields: dict[str, list[str]] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                break
            if h := HEADER.match(line):
                key, value = h.groups()
                fields.setdefault(key, []).extend([value.strip()] if key == "Status" else ADR_REF.findall(value))
        out[m.group(1)] = fields
    return out


def adr_problems(headers: dict[str, dict[str, list[str]]]) -> list[str]:
    problems = []
    for num, f in headers.items():
        status = f.get("Status", [])
        if len(status) != 1 or not (s := STATUS.match(status[0])):
            problems.append(f"ADR-{num}: Status {status} is not Proposed, Accepted or 'Superseded by ADR-NNNN'")
            continue
        superseded_by = {s.group(2)} if s.group(2) else set()
        if f.get("Superseded by") and set(f["Superseded by"]) != superseded_by:
            problems.append(f"ADR-{num}: 'Superseded by' header {f['Superseded by']} disagrees with Status {status[0]!r}")
        for ref in [*superseded_by, *(r for k in ("Supersedes", "Amends", "Amended by") for r in f.get(k, []))]:
            if ref not in headers:
                problems.append(f"ADR-{num} refers to ADR-{ref}, which has no file")
        for new in superseded_by & set(headers):
            if num not in headers[new].get("Supersedes", []):
                problems.append(f"ADR-{num} is superseded by ADR-{new}, but ADR-{new} has no 'Supersedes: ADR-{num}'")
        for old in set(f.get("Supersedes", [])) & set(headers):
            if headers[old].get("Status") != [f"Superseded by ADR-{num}"]:
                problems.append(f"ADR-{num} supersedes ADR-{old}, but ADR-{old} Status is {headers[old].get('Status')}")
        for old in set(f.get("Amends", [])) & set(headers):
            if num not in headers[old].get("Amended by", []):
                problems.append(f"ADR-{num} amends ADR-{old}, but ADR-{old} has no 'Amended by: ADR-{num}'")
        for new in set(f.get("Amended by", [])) & set(headers):
            if num not in headers[new].get("Amends", []):
                problems.append(f"ADR-{num} is amended by ADR-{new}, but ADR-{new} has no 'Amends: ADR-{num}'")
    return problems


def plan_rows(text: str) -> dict[str, set[str]]:
    """WP id (WP2, WP2a) -> its 'Depends on' ids, from the WP table of docs/plan.md."""
    rows, col = {}, None
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.startswith("|") else []
        if "Depends on" in cells:
            col = cells.index("Depends on")
        elif col is not None and PLAN_ROW.match(line):
            rows[cells[0]] = set(WP_REF.findall(cells[col]))
    return rows


def overview_graph(text: str) -> tuple[set[str], dict[str, set[str]]]:
    """(WP nodes, node -> the nodes with an edge into it), from docs/diagrams/overview.mmd."""
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("%%"))
    nodes = set(NODE.findall(body))
    deps: dict[str, set[str]] = {n: set() for n in nodes}
    for src, dst in EDGE.findall(body):
        deps.setdefault(dst, set()).add(src)
    return nodes, deps


def plan_vs_overview_problems(plan_text: str, overview_text: str) -> list[str]:
    """WP rows (no letter) match the overview's nodes and edges. A split row (WP2a) is only in the plan: its WP needs a row,
    and what it depends on must be a row of the plan."""
    rows = plan_rows(plan_text)
    nodes, edges = overview_graph(overview_text)
    wps = {wp for wp in rows if wp[-1].isdigit()}
    problems = [f"{wp}: row in docs/plan.md but no node in overview.mmd" for wp in sorted(wps - nodes)]
    problems += [f"{wp}: node in overview.mmd but no row in docs/plan.md" for wp in sorted(nodes - wps)]
    for wp in sorted(wps & nodes):
        if rows[wp] != edges.get(wp, set()):
            problems.append(f"{wp}: Depends on {sorted(rows[wp])} in docs/plan.md, edges from {sorted(edges.get(wp, set()))} in overview.mmd")
    for sid in sorted(set(rows) - wps):
        if sid[:-1] not in rows:
            problems.append(f"{sid}: split row without a {sid[:-1]} row")
        if unknown := sorted(rows[sid] - set(rows)):
            problems.append(f"{sid}: depends on {unknown}, which have no row")
    return problems


def known_issue_problems(text: str, adr_dir: Path = ADR_DIR) -> list[str]:
    """ADR mentions and docs/adr links in docs/known-issues.md resolve to ADR files. Bead ids are not checked (ADR-0047)."""
    files = {p.name for p in adr_dir.glob("*.md")}
    numbers = {m.group(1) for name in files if (m := ADR_FILE.match(name))}
    problems = [f"ADR-{n} has no file" for n in sorted(set(ADR_REF.findall(text)) - numbers)]
    problems += [f"link adr/{name} has no file" for name in sorted(set(re.findall(r"adr/([^)\s#]+\.md)", text)) - files)]
    return problems


# --- the repo ---


def test_adr_status_and_relations_are_symmetric():
    assert adr_problems(adr_headers()) == []


def test_plan_wp_rows_match_overview_nodes_and_edges():
    assert plan_vs_overview_problems(PLAN.read_text(encoding="utf-8"), OVERVIEW.read_text(encoding="utf-8")) == []


def test_known_issues_adr_references_resolve():
    assert known_issue_problems(KNOWN_ISSUES.read_text(encoding="utf-8")) == []


# --- the checks themselves ---


def write_adrs(tmp_path, adrs: dict[str, str]) -> Path:
    for num, header in adrs.items():
        (tmp_path / f"{num}-x.md").write_text(f"# ADR-{num} · x\n\n{header}\n\n## Context\n\n- Amends: ADR-9999 (body, ignored)\n")
    return tmp_path


def test_symmetric_adrs_pass(tmp_path):
    d = write_adrs(tmp_path, {
        "0001": "- Status: Superseded by ADR-0003\n- Amended by: [ADR-0002](0002-x.md)",
        "0002": "- Status: Accepted\n- Amends: ADR-0001",
        "0003": "- Status: Accepted\n- Supersedes: [ADR-0001](0001-x.md)",
    })
    assert adr_problems(adr_headers(d)) == []


@pytest.mark.parametrize(
    ("adrs", "expected"),
    [
        ({"0001": "- Status: Accepted", "0002": "- Status: Accepted\n- Supersedes: ADR-0001"}, "ADR-0001 Status is ['Accepted']"),
        ({"0001": "- Status: Superseded by ADR-0002", "0002": "- Status: Accepted"}, "has no 'Supersedes: ADR-0001'"),
        ({"0001": "- Status: Accepted", "0002": "- Status: Accepted\n- Amends: ADR-0001"}, "has no 'Amended by: ADR-0002'"),
        ({"0001": "- Status: Accepted\n- Amended by: ADR-0002", "0002": "- Status: Accepted"}, "has no 'Amends: ADR-0001'"),
        ({"0001": "- Status: Done"}, "is not Proposed"),
        ({"0001": "- Status: Accepted\n- Amends: ADR-0007"}, "ADR-0007, which has no file"),
        ({"0001": "- Status: Accepted\n- Superseded by: ADR-0002", "0002": "- Status: Accepted\n- Supersedes: ADR-0001"}, "disagrees with Status"),
    ],
)
def test_asymmetric_adrs_are_reported(tmp_path, adrs, expected):
    problems = adr_problems(adr_headers(write_adrs(tmp_path, adrs)))
    assert any(expected in p for p in problems), problems


PLAN_T = """| ID | Package | Depends on | Delivers | Done when |
| --- | --- | --- | --- | --- |
| WP0 | a | — | x | y |
| WP1 | b | WP0 | x | y |
| WP2 | c | WP1, WP0 | x | y |
| WP2a | c1 | WP1 | x | y |
| WP2b | c2 | WP2a | x | y |
"""
MMD = """flowchart TD
  %% lane a: WP0 WP1 WP2
  WP0["WP0 a"]:::done --> WP1["WP1 b"]
  WP1 --> WP2["WP2 c"]
  WP0 --> WP2
  click WP0 "u"
"""


def test_plan_matching_overview_passes_with_splits_only_in_plan():
    assert plan_vs_overview_problems(PLAN_T, MMD) == []


@pytest.mark.parametrize(
    ("plan", "mmd", "expected"),
    [
        (PLAN_T, MMD.replace("  WP0 --> WP2\n", ""), "WP2: Depends on ['WP0', 'WP1']"),
        (PLAN_T.replace("| WP1, WP0 |", "| WP1 |"), MMD, "edges from ['WP0', 'WP1']"),
        (PLAN_T, MMD + '  WP2 --> WP3["WP3 d"]\n', "WP3: node in overview.mmd but no row"),
        (PLAN_T + "| WP4 | d | WP1 | x | y |\n", MMD, "WP4: row in docs/plan.md but no node"),
        (PLAN_T + "| WP5a | e | WP1 | x | y |\n", MMD, "WP5a: split row without a WP5 row"),
        (PLAN_T.replace("| c2 | WP2a |", "| c2 | WP2c |"), MMD, "WP2b: depends on ['WP2c']"),
    ],
)
def test_plan_overview_mismatches_are_reported(plan, mmd, expected):
    problems = plan_vs_overview_problems(plan, mmd)
    assert any(expected in p for p in problems), problems


def test_known_issue_dangling_adr_is_reported(tmp_path):
    (tmp_path / "0001-a.md").write_text("")
    text = "See ADR-0001 and [ADR-0002](adr/0002-b.md), [ok](adr/0001-a.md), bead aiwf-zzz."
    assert known_issue_problems(text, tmp_path) == ["ADR-0002 has no file", "link adr/0002-b.md has no file"]
