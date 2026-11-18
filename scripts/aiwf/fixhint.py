"""B1's "possibly fixed by X" hint, handed to B2 (spec B2, aiwf-1st).

The hint is read only from our own triage comment (the workflow bot's marker comment, never reporter text), and only
the one fixed sentence B1's publish writes is parsed. What survives is a commit or PR number of this repo, checked
against the API, and the full 40-hex SHA of the commit just before the fix: the only thing that goes into B2's prompt.
"""

from __future__ import annotations

import re
from typing import Any

from aiwf.ghapi import GhRunner, find_marker_comment, get_or_none
from aiwf.publish_triage import MARKER

SHA = re.compile(r"[0-9a-f]{40}")
LINE = re.compile(r"^Possibly fixed on the default branch by https://[A-Za-z0-9.-]+/(?P<repo>[\w.-]+/[\w.-]+)/"
                  r"(?P<kind>commit|pull)/(?P<ref>[0-9a-f]{40}|[0-9]{1,9}) \(", re.MULTILINE)


def before_fix(gh: GhRunner, repo: str, kind: str, ref: str) -> str | None:
    """The 40-hex SHA just before the fix: a commit's first parent, or the first parent of a merged PR's merge commit."""
    sha = None
    if kind == "pull" and ref.isdigit():
        pr = get_or_none(gh, f"repos/{repo}/pulls/{ref}") or {}
        merge = pr.get("merge_commit_sha") if pr.get("merged_at") else None
        ref, kind = (merge, "commit") if isinstance(merge, str) else ("", "")
    if kind == "commit" and SHA.fullmatch(ref):
        parents = (get_or_none(gh, f"repos/{repo}/commits/{ref}") or {}).get("parents") or []
        sha = (parents[0] or {}).get("sha") if parents else None
    return sha if isinstance(sha, str) and SHA.fullmatch(sha) else None


def find(gh: GhRunner, repo: str, issue: int) -> dict[str, Any] | None:
    """{"kind", "ref", "before"} for the fix B1 named on this issue, or None (no hint, foreign repo, unresolvable)."""
    comment = find_marker_comment(gh, repo, issue, MARKER)
    m = LINE.search((comment or {}).get("body") or "")
    if not m or m["repo"].lower() != repo.lower():
        return None
    before = before_fix(gh, repo, m["kind"], m["ref"])
    return {"kind": m["kind"], "ref": m["ref"], "before": before} if before else None
