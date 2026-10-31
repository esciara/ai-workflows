"""Generated files and their single writer (ADR-0015).

`docs/progress.md`, `docs/board.jsonl`, the ADR index and `docs/diagrams.md` are written only by the orchestrator, in a
serial sync PR on a `sync-*` branch after each merge batch. Track PRs change only sources (ADR files, `.mmd` files).
`check-branch` fails when another branch changes a generated file; `stale` reports generated files out of date with
their sources and is checked only on sync-* branches (a stale main shows as the SessionStart sync-due warning). Both run locally and in CI.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATED = ("docs/progress.md", "docs/board.jsonl", "docs/adr/README.md", "docs/diagrams.md")
SYNC_PREFIX = "sync-"
MARKER = "<!-- BEGIN generated:"


def is_sync_branch(branch: str) -> bool:
    return branch.startswith(SYNC_PREFIX)


def freshness_checked(branch: str) -> bool:
    """Generated files must be fresh only on sync-* branches; other branches may not regenerate them (ADR-0015)."""
    return is_sync_branch(branch)


def in_force(path: str, base_text: str | None) -> bool:
    """The rule applies to a file once its generator is on the base branch: the file exists there with generated blocks (or is the export)."""
    if base_text is None:
        return False
    return path.endswith(".jsonl") or MARKER in base_text


def violations(branch: str, changed: list[str], base_texts: dict[str, str | None]) -> list[str]:
    if is_sync_branch(branch):
        return []
    return sorted(p for p in changed if p in GENERATED and in_force(p, base_texts.get(p)))


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=30)


def current_branch(root: Path = ROOT) -> str:
    """PR head branch in Actions (GITHUB_HEAD_REF), else the pushed ref (GITHUB_REF_NAME), else the local checkout."""
    env = os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME")
    return env or _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def check_branch(root: Path = ROOT, base: str = "origin/main", branch: str | None = None) -> list[str] | None:
    """Generated files this branch changes against `base` without being a sync branch; None if `base` is unavailable."""
    diff = _git(root, "diff", "--name-only", f"{base}...HEAD")
    if diff.returncode != 0:
        return None
    base_texts = {}
    for p in GENERATED:
        show = _git(root, "show", f"{base}:{p}")
        base_texts[p] = show.stdout if show.returncode == 0 else None
    return violations(branch or current_branch(root), diff.stdout.split(), base_texts)


def stale(root: Path = ROOT, fresh_export: str | None = None) -> list[str]:
    """Messages for generated files out of date with their sources; `fresh_export` (normalised `bd export`) adds the board check."""
    from aiwf import adrindex, board, diagrams, gendoc, progress

    out = []
    try:
        if fresh_export is not None and (root / "docs/board.jsonl").read_text(encoding="utf-8") != fresh_export:
            out.append("docs/board.jsonl differs from the local beads board")
        export = board.parse((root / "docs/board.jsonl").read_text(encoding="utf-8"))
        checks = [
            ("docs/progress.md", lambda t: progress.render(t, export)),
            ("docs/adr/README.md", lambda t: adrindex.render(t, root / "docs/adr")),
            ("docs/diagrams.md", lambda t: diagrams.render(t, root / "docs/diagrams")),
        ]
        for path, render in checks:
            text = (root / path).read_text(encoding="utf-8")
            if render(text) != text:
                out.append(f"{path} is out of date with its sources")
    except (OSError, board.BoardError, progress.BoardError, gendoc.GenDocError) as exc:
        out.append(f"cannot check generated files: {exc}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="generated", description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["check-branch", "stale"])
    ap.add_argument("--base", default="origin/main")
    args = ap.parse_args(argv)
    if args.command == "check-branch":
        bad = check_branch(base=args.base)
        if bad is None:
            print(f"generated: {args.base} not available; skipped", file=sys.stderr)
            return 0
        for p in bad:
            print(f"{p} is generated; only the orchestrator's {SYNC_PREFIX}* branch may change it (ADR-0015)", file=sys.stderr)
        return 1 if bad else 0
    msgs = stale()
    for m in msgs:
        print(m, file=sys.stderr)
    return 1 if msgs else 0


if __name__ == "__main__":
    sys.exit(main())
