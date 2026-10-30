"""Replace generated blocks in a Markdown file, between `<!-- BEGIN generated:<name> -->` and `<!-- END generated:<name> -->`."""

from __future__ import annotations

import re

_BLOCK = re.compile(
    r"(?P<begin><!-- BEGIN generated:(?P<name>[\w.-]+)[^\n]*-->\n)(?P<body>.*?)(?P<end><!-- END generated:(?P=name) -->)",
    re.DOTALL,
)


class GenDocError(Exception):
    pass


def block_names(text: str) -> list[str]:
    return [m.group("name") for m in _BLOCK.finditer(text)]


def replace_blocks(text: str, blocks: dict[str, str]) -> str:
    """Return `text` with each named block's body set to `blocks[name]`; every block in the text must be given, and every given block must exist."""
    found = block_names(text)
    if len(found) != len(set(found)):
        raise GenDocError(f"duplicate generated blocks: {found}")
    missing = sorted(set(blocks) - set(found))
    if missing:
        raise GenDocError(f"no marker for generated block(s): {', '.join(missing)}")
    unknown = sorted(set(found) - set(blocks))
    if unknown:
        raise GenDocError(f"no content for generated block(s): {', '.join(unknown)}")

    def sub(m: re.Match[str]) -> str:
        body = blocks[m.group("name")].rstrip("\n") + "\n"
        return m.group("begin") + body + m.group("end")

    return _BLOCK.sub(sub, text)
