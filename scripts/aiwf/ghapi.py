"""Small GitHub API helpers shared by the orchestrator modules. `gh` is a runner such as config.run_gh."""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.parse import quote

BOT = "github-actions[bot]"  # the workflow's GITHUB_TOKEN identity; only its marker comments are ours (ADR-0021)

GhRunner = Callable[[list[str]], str]


def get_json(gh: GhRunner, path: str) -> Any:
    return json.loads(gh(["api", path]) or "null")


def get_or_none(gh: GhRunner, path: str, notice: str = "") -> Any | None:
    """GET as JSON, or None when the API refuses it. `notice`: also say so in the log, with this title."""
    try:
        return get_json(gh, path)
    except RuntimeError as exc:
        if notice:
            print(f"::notice title={notice}::{path.split('?')[0]}: {str(exc)[:200]}")
        return None


def find_marker_comment(gh: GhRunner, repo: str, number: int, marker: str) -> dict[str, Any] | None:
    """The bot's own comment starting with `marker`; a forged marker from anyone else is ignored."""
    out = gh(["api", "--paginate", "--jq", ".[]", f"repos/{repo}/issues/{number}/comments?per_page=100"])
    for line in out.splitlines():
        if line.strip():
            c = json.loads(line)
            if c["user"]["login"] == BOT and (c.get("body") or "").startswith(marker):
                return c
    return None


def upsert_marker_comment(gh: GhRunner, repo: str, number: int, marker: str, body: str) -> None:
    """One comment per item, found by its marker and updated in place on reruns."""
    found = find_marker_comment(gh, repo, number, marker)
    if found is None:
        gh(["api", "-X", "POST", f"repos/{repo}/issues/{number}/comments", "-f", f"body={body}"])
    else:
        gh(["api", "-X", "PATCH", f"repos/{repo}/issues/comments/{found['id']}", "-f", f"body={body}"])


def remove_label(gh: GhRunner, repo: str, number: int, label: str) -> None:
    """Remove a label; one that is not set is fine, any other API error is raised."""
    try:
        gh(["api", "-X", "DELETE", f"repos/{repo}/issues/{number}/labels/{quote(label, safe='')}"])
    except RuntimeError as exc:
        if "404" not in str(exc) and "Not Found" not in str(exc):
            raise
