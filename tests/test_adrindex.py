import pytest

from aiwf import adrindex, gendoc

DOC = """# ADRs

## Index

<!-- BEGIN generated:adr-index (note) -->
stale
<!-- END generated:adr-index -->
"""


def adr(tmp_path, name, title, status="Accepted", alias=None):
    num = name[:4]
    alias = alias or f"D{int(num)}"
    (tmp_path / name).write_text(f"# ADR-{num} · {title}\n\n- Status: {status}\n- Date: 2026-10-31\n- Alias: `{alias}`\n\n## Context\n\n- Status: not this one\n")


def test_index_is_sorted_and_built_from_heading_alias_and_status(tmp_path):
    adr(tmp_path, "0010-b.md", "Second `code`", status="Superseded by ADR-0011")
    adr(tmp_path, "0002-a.md", "First")
    (tmp_path / "README.md").write_text(DOC)
    (tmp_path / "notes.md").write_text("ignored")
    out = adrindex.render(DOC, tmp_path)
    assert "stale" not in out
    assert out.endswith(
        "| ADR | Alias | Title | Status |\n| --- | --- | --- | --- |\n"
        "| [ADR-0002](0002-a.md) | D2 | First | Accepted |\n"
        "| [ADR-0010](0010-b.md) | D10 | Second `code` | Superseded by ADR-0011 |\n"
        "<!-- END generated:adr-index -->\n"
    )
    assert adrindex.render(out, tmp_path) == out


def test_malformed_adr_is_an_error(tmp_path):
    (tmp_path / "0003-x.md").write_text("# ADR-0004 · wrong number\n- Status: Accepted\n- Alias: `D3`\n")
    with pytest.raises(gendoc.GenDocError, match="first heading"):
        adrindex.index(tmp_path)
    (tmp_path / "0003-x.md").write_text("# ADR-0003 · no alias\n- Status: Accepted\n")
    with pytest.raises(gendoc.GenDocError, match="Alias"):
        adrindex.index(tmp_path)


def test_main_check_and_write(tmp_path):
    adr(tmp_path, "0001-a.md", "A")
    (tmp_path / "README.md").write_text(DOC)
    assert adrindex.main(["--dir", str(tmp_path), "--check"]) == 1
    assert adrindex.main(["--dir", str(tmp_path)]) == 0
    assert adrindex.main(["--dir", str(tmp_path), "--check"]) == 0


def test_repo_adr_index_is_up_to_date():
    assert adrindex.main(["--check"]) == 0
