"""Markdown and text helpers for comments and agent context built from untrusted text, shared by the publishers and the context builders."""

from __future__ import annotations

import re
from datetime import datetime


def inline(text: str, limit: int = 200) -> str:
    """Inline code, also safe in a table cell: one line, no backticks, pipes escaped."""
    return "`" + " ".join(str(text).split())[:limit].replace("`", "'").replace("|", "\\|") + "`"


def run_link(run_url: str, missing: str = "a later run") -> str:
    """`[run](url)` for a workflow run, or `missing` when there is no URL."""
    return f"[run]({run_url})" if run_url else missing


def ticks(text: str) -> str:
    """A backtick fence longer than any backtick run in `text`, so the text cannot close its block."""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def tag_re(tags: tuple[str, ...]) -> re.Pattern[str]:
    """Matches the `<` of an opening or closing tag among `tags` (the group keeps the rest of it), for `defuse_tags`."""
    return re.compile(r"<(\s*/?\s*(?:" + "|".join(tags) + r")\b)", re.IGNORECASE)


def defuse_tags(text: str, pattern: re.Pattern[str]) -> str:
    """`text` with every tag matched by `pattern` (from `tag_re`) defused (`<diff>` -> `&lt;diff>`), the rest kept as written."""
    return pattern.sub(r"&lt;\1", text)


def defuse_links(text: str, zwsp: str) -> str:
    """A URL scheme (`https://`) or `www.` followed by `zwsp`, so the text does not autolink."""
    text = re.sub(r"(?i)\b([a-z][a-z0-9+.-]*)://", lambda m: f"{m.group(1)}:{zwsp}//", text)
    return re.sub(r"(?i)\bwww\.", lambda m: f"www{zwsp}.", text)


def parse_time(text: str) -> datetime:
    """An ISO 8601 timestamp as GitHub writes it (trailing `Z`)."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))
