"""Regenerate the mermaid blocks of docs/diagrams.md from docs/diagrams/<name>.mmd (block `generated:<name>`)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aiwf import gendoc

ROOT = Path(__file__).resolve().parents[2]
DIAGRAMS_PATH = ROOT / "docs" / "diagrams.md"
SOURCES_DIR = ROOT / "docs" / "diagrams"


def blocks(sources_dir: Path) -> dict[str, str]:
    out = {}
    for src in sorted(sources_dir.glob("*.mmd")):
        body = src.read_text(encoding="utf-8").rstrip("\n")
        if "```" in body:
            raise gendoc.GenDocError(f"{src.name}: must not contain a code fence")
        out[src.stem] = f"```mermaid\n{body}\n```"
    return out


def render(text: str, sources_dir: Path) -> str:
    return gendoc.replace_blocks(text, blocks(sources_dir))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="render-diagrams", description=__doc__.splitlines()[0])
    ap.add_argument("--file", default=str(DIAGRAMS_PATH), help="diagrams file to update")
    ap.add_argument("--sources", default=str(SOURCES_DIR), help="directory of .mmd sources")
    args = ap.parse_args(argv)
    target = Path(args.file)
    try:
        old = target.read_text(encoding="utf-8")
        new = render(old, Path(args.sources))
    except (gendoc.GenDocError, OSError) as exc:
        print(f"render-diagrams: {exc}", file=sys.stderr)
        return 2
    if new != old:
        target.write_text(new, encoding="utf-8")
        print(f"updated {target}")
    return 0
