"""Workflow A, step 8: where each confirmed finding goes (spec, "Where review comments go"). Pure rules, no GitHub calls.

- `inline`: a comment on the line in the run's one GitHub review, with a `suggestion` block when the fix is a few lines
  on a low- or medium-risk path.
- `collapsed`: summary only, in the collapsed nits section (a one-place nit on a low- or medium-risk path).
- `general`: summary table only (no line, spread wide, or a line GitHub cannot comment on).
"""

from __future__ import annotations

import re
from typing import Any

INLINE, COLLAPSED, GENERAL = "inline", "collapsed", "general"
MAX_PLACES = 5  # same pattern in up to 5 places: inline on the first; more is "spread wide"
MAX_FILES = 3  # ... or across more than 3 files
MAX_SUGGESTION_LINES = 10  # "the fix is a few lines"


def hunk(facts: dict[str, Any], path: str, line: int | None) -> tuple[int, int] | None:
    """The diff hunk (head-side line range) holding `path:line`, or None when GitHub cannot comment there."""
    if not line:
        return None
    for start, end in facts.get("commentable", {}).get(path, []):
        if start <= line <= end:
            return start, end
    return None


def places(f: dict[str, Any]) -> list[tuple[str, int | None]]:
    return [(f["path"], f.get("line")), *[(a["path"], a.get("line")) for a in f.get("also") or []]]


def place(f: dict[str, Any], facts: dict[str, Any]) -> str:
    """The spec's placement table, first matching row wins."""
    if not f.get("line"):
        return GENERAL  # something absent, architecture, or the PR itself
    where = places(f)
    if len(where) > MAX_PLACES or len({p for p, _ in where}) > MAX_FILES:
        return GENERAL  # spread wide
    high = f["path"] in facts.get("high_paths", [])
    if f["severity"] == "nit" and not high and len(where) == 1:
        return COLLAPSED
    return INLINE if hunk(facts, f["path"], f["line"]) else GENERAL


def suggestion(f: dict[str, Any], facts: dict[str, Any]) -> tuple[int, int, str] | None:
    """(start_line, end_line, code) for a GitHub `suggestion` block, or None.

    Only on low- and medium-risk paths, for a replacement of at most a few lines whose range lies in one diff hunk."""
    code = f.get("replacement")
    if code is None or f["path"] in facts.get("high_paths", []):
        return None
    start, end = f["line"], f.get("end_line") or f["line"]
    h = hunk(facts, f["path"], start)
    code = code.replace("\r\n", "\n").rstrip("\n")
    if end < start or end - start >= MAX_SUGGESTION_LINES or not h or end > h[1]:
        return None
    if len(code.split("\n")) > MAX_SUGGESTION_LINES:
        return None
    return start, end, code


def fence(code: str) -> str:
    """A backtick fence longer than any backtick run in `code`, so the code cannot close its block."""
    longest = max((len(m) for m in re.findall(r"`+", code)), default=0)
    return "`" * max(3, longest + 1)
