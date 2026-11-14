"""Markdown helpers for comments built from untrusted text, shared by Workflow B's publishers."""

from __future__ import annotations


def inline(text: str, limit: int = 200) -> str:
    """Inline code, also safe in a table cell: one line, no backticks, pipes escaped."""
    return "`" + " ".join(str(text).split())[:limit].replace("`", "'").replace("|", "\\|") + "`"


def run_link(run_url: str, missing: str = "a later run") -> str:
    """`[run](url)` for a workflow run, or `missing` when there is no URL."""
    return f"[run]({run_url})" if run_url else missing
