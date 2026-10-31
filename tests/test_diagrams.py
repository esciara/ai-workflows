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
