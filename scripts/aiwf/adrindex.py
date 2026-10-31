"""Regenerate the ADR index in docs/adr/README.md (block `generated:adr-index`) from the ADR files' title, Alias and Status lines."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from aiwf import gendoc

ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = ROOT / "docs" / "adr"
README_PATH = ADR_DIR / "README.md"
_NAME = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")
_TITLE = re.compile(r"^# ADR-(\d{4}) · (.+)$", re.MULTILINE)
_FIELD = re.compile(r"^- (Status|Alias): (.+)$", re.MULTILINE)


def entry(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    num = _NAME.match(path.name).group(1)
    title = _TITLE.search(text)
    if not title or title.group(1) != num:
        raise gendoc.GenDocError(f"{path.name}: first heading must be '# ADR-{num} · <title>'")
    fields = dict(_FIELD.findall(text.split("\n## ", 1)[0]))  # header lines only, before the first section
    for key in ("Status", "Alias"):
        if key not in fields:
            raise gendoc.GenDocError(f"{path.name}: missing '- {key}:' line")
    return [f"[ADR-{num}]({path.name})", fields["Alias"].strip().strip("`"), title.group(2).strip(), fields["Status"].strip()]


def index(adr_dir: Path) -> str:
    rows = [entry(p) for p in sorted(adr_dir.glob("*.md")) if _NAME.match(p.name)]
    lines = ["| ADR | Alias | Title | Status |", "| --- | --- | --- | --- |"]
    return "\n".join(lines + [f"| {' | '.join(r)} |" for r in rows])


def render(text: str, adr_dir: Path) -> str:
    return gendoc.replace_blocks(text, {"adr-index": index(adr_dir)})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="render-adr-index", description=__doc__.splitlines()[0])
    ap.add_argument("--dir", default=str(ADR_DIR), help="ADR directory (README.md inside it is updated)")
    ap.add_argument("--check", action="store_true", help="exit 1 if the index is out of date; write nothing")
    args = ap.parse_args(argv)
    adr_dir = Path(args.dir)
    target = adr_dir / "README.md"
    try:
        old = target.read_text(encoding="utf-8")
        new = render(old, adr_dir)
    except (gendoc.GenDocError, OSError) as exc:
        print(f"render-adr-index: {exc}", file=sys.stderr)
        return 2
    if args.check:
        if new != old:
            print(f"{target} is out of date; run scripts/dev/render-adr-index", file=sys.stderr)
            return 1
        return 0
    if new != old:
        target.write_text(new, encoding="utf-8")
        print(f"updated {target}")
    return 0
