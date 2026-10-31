"""Export the beads board to docs/board.jsonl, then render the generated blocks of docs/progress.md from that export.

The export (aiwf.board) is the committed record: docs/progress.md can be re-rendered from git alone (`--no-export`).

A work-package bead carries `metadata.wp` ("WP2"); optional `metadata.pr`, `metadata.notes`, `metadata.log` (list of
log lines) and `metadata.metrics` (maintainer_interventions, verifier_fails, rework_prs, coordination_issues, notes).
"Depends on" comes from the bead's `blocks` dependencies on other WP beads. Other beads are ignored.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from aiwf import board, gendoc

ROOT = Path(__file__).resolve().parents[2]
PROGRESS_PATH = ROOT / "docs" / "progress.md"

STATUS = {
    "open": "todo",
    "in_progress": "in progress",
    "in_review": "in review",
    "blocked": "blocked",
    "deferred": "deferred",
    "closed": "done",
}
METRIC_KEYS = ["maintainer_interventions", "verifier_fails", "rework_prs", "coordination_issues", "notes"]
METRIC_HEADERS = ["maintainer interventions", "verifier fails", "rework PRs", "coordination issues", "notes"]


class BoardError(Exception):
    pass


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _row(cells: list[object]) -> str:
    return "|" + "|".join(f" {c} " if c else " " for c in map(_cell, cells)) + "|"


def _wp_num(wp: str) -> int:
    if not (wp.startswith("WP") and wp[2:].isdigit()):
        raise BoardError(f"bad metadata.wp {wp!r}")
    return int(wp[2:])


def work_packages(issues: list[dict]) -> list[dict]:
    wps = [i for i in issues if isinstance(i.get("metadata"), dict) and "wp" in i["metadata"]]
    names = [i["metadata"]["wp"] for i in wps]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise BoardError(f"more than one bead for {', '.join(dupes)}")
    return sorted(wps, key=lambda i: _wp_num(i["metadata"]["wp"]))


def wp_table(issues: list[dict]) -> str:
    wps = work_packages(issues)
    by_id = {i["id"]: i["metadata"]["wp"] for i in wps}
    lines = ["| WP | Package | Depends on | Status | PR | Notes |", "| --- | --- | --- | --- | --- | --- |"]
    for i in wps:
        meta = i["metadata"]
        deps = sorted(
            (by_id[d["depends_on_id"]] for d in i.get("dependencies", []) if d.get("type") == "blocks" and d.get("depends_on_id") in by_id),
            key=_wp_num,
        )
        status = STATUS.get(i["status"])
        if status is None:
            raise BoardError(f"{i['id']}: unknown status {i['status']!r}")
        lines.append(_row([meta["wp"], i["title"], ", ".join(deps) or "—", status, meta.get("pr", ""), meta.get("notes", "")]))
    return "\n".join(lines)


def metrics_table(issues: list[dict]) -> str:
    lines = [_row(["WP", *METRIC_HEADERS]), "| --- " * (len(METRIC_KEYS) + 1) + "|"]
    for i in work_packages(issues):
        metrics = i["metadata"].get("metrics")
        if metrics:
            lines.append(_row([i["metadata"]["wp"], *(metrics.get(k, "") for k in METRIC_KEYS)]))
    return "\n".join(lines)


def log_lines(issues: list[dict]) -> str:
    entries = []
    for i in work_packages(issues):
        for line in i["metadata"].get("log", []):
            entries.append((line[:10], _wp_num(i["metadata"]["wp"]), line))
    return "\n".join(f"- {line}" for _, _, line in sorted(entries))


def render(text: str, issues: list[dict]) -> str:
    return gendoc.replace_blocks(text, {"wp-table": wp_table(issues), "metrics": metrics_table(issues), "log": log_lines(issues)})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="render-progress", description=__doc__.splitlines()[0])
    ap.add_argument("--board", default=str(board.BOARD_PATH), help="board export to write and render from (default docs/board.jsonl)")
    ap.add_argument("--file", default=str(PROGRESS_PATH), help="progress file to update")
    ap.add_argument("--no-export", action="store_true", help="render from the existing export; do not run bd (worktrees without a board)")
    args = ap.parse_args(argv)
    target, board_path = Path(args.file), Path(args.board)
    try:
        if args.no_export:
            export = board_path.read_text(encoding="utf-8")
        else:
            export = board.fresh_export()
            leaks = board.scan_secrets(export)
            if leaks:
                print(f"render-progress: secret scan found {', '.join(leaks)} in the board export; nothing written. Remove it from the beads and rerun.", file=sys.stderr)
                return 2
        old = target.read_text(encoding="utf-8")
        new = render(old, board.parse(export))
    except (BoardError, board.BoardError, board.SecretScanError, gendoc.GenDocError, subprocess.SubprocessError, OSError) as exc:
        print(f"render-progress: {exc}", file=sys.stderr)
        return 2
    if not args.no_export and (not board_path.exists() or board_path.read_text(encoding="utf-8") != export):
        board_path.write_text(export, encoding="utf-8")
        print(f"updated {board_path}")
    if new != old:
        target.write_text(new, encoding="utf-8")
        print(f"updated {target}")
    return 0
