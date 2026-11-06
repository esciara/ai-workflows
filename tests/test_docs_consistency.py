"""ADR links in the hand-written docs resolve: every ADR-NNNN mention has a file, every link to an ADR file exists."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR_DIR = ROOT / "docs" / "adr"
ADR_FILE = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")
ADR_MENTION = re.compile(r"ADR-(\d{4})")
ADR_LINK = re.compile(r"\]\(([^)\s#]*\d{4}-[a-z0-9-]+\.md)[)#]")


def adr_link_problems(path: Path, text: str, adr_dir: Path = ADR_DIR) -> list[str]:
    files = [*adr_dir.glob("*.md"), *adr_dir.glob("archive/*.md")]
    numbers = {m.group(1) for f in files if (m := ADR_FILE.match(f.name))}
    problems = [f"{path.name}: ADR-{n} has no file" for n in sorted(set(ADR_MENTION.findall(text)) - numbers)]
    problems += [f"{path.name}: link {link} has no file" for link in sorted(set(ADR_LINK.findall(text))) if not (path.parent / link).is_file()]
    return problems


def test_adr_links_resolve():
    docs = [ROOT / "CLAUDE.md", ROOT / "README.md", *(ROOT / "docs").glob("*.md"), *ADR_DIR.glob("*.md"), *ADR_DIR.glob("archive/*.md")]
    assert [p for path in docs for p in adr_link_problems(path, path.read_text(encoding="utf-8"))] == []


def test_dangling_adr_mention_and_link_are_reported(tmp_path):
    (tmp_path / "0001-a.md").write_text("")
    text = "See ADR-0001 and [ADR-0002](0002-b.md), [ok](0001-a.md), bead aiwf-zzz."
    assert adr_link_problems(tmp_path / "x.md", text, tmp_path) == ["x.md: ADR-0002 has no file", "x.md: link 0002-b.md has no file"]
