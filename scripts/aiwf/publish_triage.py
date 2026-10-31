"""Publishers for Workflow B (issue triage). B1: labels and one triage comment from the classifier's checked JSON.

The classifier's references (duplicate issue, fixing commit or PR) are checked against the repo before they are linked:
an unknown or invalid reference is dropped, never posted. A fix is only "possibly fixed by" (ADR-0035): reproducing the
bug (B2) confirms it. Triage never closes an issue.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import quote

from aiwf import publish

MARKER = "<!-- ai-workflows:triage -->"
BOT = "github-actions[bot]"  # the workflow's GITHUB_TOKEN identity; only its marker comments are ours (ADR-0021)
TYPE_LABELS = {"bug": "type: bug", "feature": "type: feature", "question": "type: question"}
DUPLICATE = "triage: duplicate"
NEEDS_HUMAN = "triage: needs-human"
RANGE_ENV = "AIWF_FIX_RANGE_CONFIDENCE"  # `low` when the fix candidates were not from the reported version
B1_LABELS = (*TYPE_LABELS.values(), DUPLICATE, NEEDS_HUMAN)  # cleared on /retriage before the new result


def get(gh: publish.GhRunner, path: str) -> Any | None:
    """GET as JSON, or None when the API refuses it (404 for an unknown issue or commit)."""
    try:
        return json.loads(gh(["api", path]) or "null")
    except RuntimeError:
        return None


def check_duplicate(gh: publish.GhRunner, repo: str, issue: int, number: int | None) -> dict[str, Any] | None:
    """The issue `number` when it is another real issue, open or closed as completed; else None."""
    if not number or number == issue:
        return None
    other = get(gh, f"repos/{repo}/issues/{number}")
    if not other or "pull_request" in other:
        return None
    if other["state"] != "open" and other.get("state_reason") != "completed":
        return None
    return other


def check_commit(gh: publish.GhRunner, repo: str, branch: str, sha: str | None) -> dict[str, Any] | None:
    """The commit when it exists and is on `branch` (the branch is ahead of it or at it); else None."""
    if not sha:
        return None
    commit = get(gh, f"repos/{repo}/commits/{sha}")
    if not commit:
        return None
    cmp = get(gh, f"repos/{repo}/compare/{commit['sha']}...{quote(branch, safe='')}")
    return commit if cmp and cmp.get("status") in {"ahead", "identical"} else None


def check_pr(gh: publish.GhRunner, repo: str, branch: str, number: int) -> dict[str, Any] | None:
    """The pull request when it exists and was merged into `branch`; else None."""
    pr = get(gh, f"repos/{repo}/pulls/{number}")
    if not pr or not pr.get("merged_at") or (pr.get("base") or {}).get("ref") != branch:
        return None
    return pr


def check_fix(gh: publish.GhRunner, repo: str, branch: str, ref: dict[str, Any] | None) -> dict[str, Any] | None:
    """The commit or merged PR the classifier names, when it is real and on the default branch; else None."""
    if not ref:
        return None
    if ref["kind"] == "commit":
        return check_commit(gh, repo, branch, ref["ref"]) if re.fullmatch(r"[0-9a-f]{7,40}", ref["ref"]) else None
    return check_pr(gh, repo, branch, int(ref["ref"])) if ref["ref"].isdigit() else None


def fix_confidence(data: dict[str, Any], range_confidence: str) -> str:
    """The agent's confidence in the fix, capped at low when the commit range was a guess (no tag for the version)."""
    return "low" if range_confidence == "low" else data["possibly_fixed_by"]["confidence"]


def is_duplicate(data: dict[str, Any], dup: dict[str, Any] | None) -> bool:
    return bool(dup) and data["duplicate_of"]["confidence"] in {"high", "medium"}


def body(data: dict[str, Any], dup: dict[str, Any] | None, fix: dict[str, Any] | None, fix_conf: str,
         run_url: str) -> str:
    lines = [MARKER, f"**AI triage:** {data['type']} ({data['confidence']} confidence). {data['reason']}"]
    if is_duplicate(data, dup):
        lines += ["", f"Duplicate of #{dup['number']} ({data['duplicate_of']['confidence']} confidence). Labelled "
                  f"`{DUPLICATE}`; a person takes over. Not closed."]
    elif dup:
        lines += ["", f"May duplicate #{dup['number']} (low confidence); not labelled as a duplicate."]
    if fix:
        lines += ["", f"Possibly fixed on the default branch by {fix['html_url']} ({fix_conf} confidence). Not "
                  "confirmed: reproducing the bug checks it. Not closed."]
    if data["confidence"] == "low":
        lines += ["", f"Low confidence: labelled `{NEEDS_HUMAN}`; a person takes over."]
    if run_url:
        lines += ["", f"[Run]({run_url})"]
    return "\n".join(lines)


def find_comment(gh: publish.GhRunner, repo: str, issue: int) -> int | None:
    out = gh(["api", "--paginate", f"repos/{repo}/issues/{issue}/comments?per_page=100", "--jq", ".[]"])
    for line in out.splitlines():
        if line.strip():
            c = json.loads(line)
            if c["user"]["login"] == BOT and MARKER in (c.get("body") or ""):
                return c["id"]
    return None


def upsert_comment(gh: publish.GhRunner, repo: str, issue: int, text: str) -> None:
    """One triage comment per issue, updated in place on reruns."""
    cid = find_comment(gh, repo, issue)
    if cid is None:
        publish.comment(gh, repo, issue, text)
    else:
        gh(["api", "-X", "PATCH", f"repos/{repo}/issues/comments/{cid}", "-f", f"body={text}"])


def remove_label(gh: publish.GhRunner, repo: str, issue: int, label: str) -> None:
    try:
        gh(["api", "-X", "DELETE", f"repos/{repo}/issues/{issue}/labels/{quote(label, safe='')}"])
    except RuntimeError:
        pass  # not set


def labels_for(data: dict[str, Any], duplicate: bool) -> list[str]:
    out = [TYPE_LABELS[data["type"]]]
    if duplicate:
        out.append(DUPLICATE)
    if data["confidence"] == "low":
        out.append(NEEDS_HUMAN)
    return out


def publish_classifier(data: dict[str, Any], repo: str, issue: int, run_url: str, gh: publish.GhRunner) -> None:
    current = {lb["name"] for lb in (get(gh, f"repos/{repo}/issues/{issue}") or {}).get("labels", [])}
    branch = (get(gh, f"repos/{repo}") or {}).get("default_branch", "main")
    dup_ref = (data.get("duplicate_of") or {}).get("number")
    dup = check_duplicate(gh, repo, issue, dup_ref)
    fix_ref = data.get("possibly_fixed_by") if data["type"] == "bug" else None
    fix = check_fix(gh, repo, branch, fix_ref)
    for name, value, ok in (("duplicate_of", dup_ref, dup), ("possibly_fixed_by", data.get("possibly_fixed_by"), fix)):
        if value and not ok:
            print(f"::warning title=Classifier reference dropped::{name}={json.dumps(value)} is not a valid reference")
    fix_conf = fix_confidence(data, os.environ.get(RANGE_ENV, "")) if fix else ""
    want = labels_for(data, is_duplicate(data, dup))
    for label in B1_LABELS:
        if label in current and label not in want:
            remove_label(gh, repo, issue, label)
    publish.add_labels(gh, repo, issue, *want)
    upsert_comment(gh, repo, issue, body(data, dup, fix, fix_conf, run_url))
    print(f"triaged {repo}#{issue}: {', '.join(want)}")


PUBLISHERS = {"classifier": publish_classifier}
