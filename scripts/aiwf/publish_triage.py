"""Publishers for Workflow B (issue triage). B1: labels and one triage comment from the classifier's checked JSON.

The classifier's references (duplicate issue, fixing commit) are checked against the repo before they are linked:
an unknown or invalid reference is dropped, never posted. Triage never closes an issue.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from aiwf import publish

MARKER = "<!-- ai-workflows:triage -->"
BOT = "github-actions[bot]"  # the workflow's GITHUB_TOKEN identity; only its marker comments are ours (ADR-0021)
TYPE_LABELS = {"bug": "type: bug", "feature": "type: feature", "question": "type: question"}
DUPLICATE = "triage: duplicate"
NEEDS_HUMAN = "triage: needs-human"
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


def body(data: dict[str, Any], dup: dict[str, Any] | None, commit: dict[str, Any] | None, run_url: str) -> str:
    lines = [MARKER, f"**AI triage:** {data['type']} ({data['confidence']} confidence). {data['reason']}"]
    if dup:
        lines += ["", f"Duplicate of #{dup['number']}. Labelled `{DUPLICATE}`; a person takes over. Not closed."]
    elif commit:
        lines += ["", f"Already fixed on the default branch by {commit['html_url']}. Labelled `{DUPLICATE}`; a person "
                  "takes over. Not closed."]
    elif data["confidence"] == "low":
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
    elif data["confidence"] == "low":
        out.append(NEEDS_HUMAN)
    return out


def publish_classifier(data: dict[str, Any], repo: str, issue: int, run_url: str, gh: publish.GhRunner) -> None:
    current = {lb["name"] for lb in (get(gh, f"repos/{repo}/issues/{issue}") or {}).get("labels", [])}
    branch = (get(gh, f"repos/{repo}") or {}).get("default_branch", "main")
    dup = check_duplicate(gh, repo, issue, data.get("duplicate_of"))
    commit = None if dup else check_commit(gh, repo, branch, data.get("fixed_by_commit"))
    for dropped, value in (("duplicate_of", data.get("duplicate_of")), ("fixed_by_commit", data.get("fixed_by_commit"))):
        if value and not (dup if dropped == "duplicate_of" else commit):
            print(f"::warning title=Classifier reference dropped::{dropped}={value} is not a valid reference")
    want = labels_for(data, bool(dup or commit))
    for label in B1_LABELS:
        if label in current and label not in want:
            remove_label(gh, repo, issue, label)
    publish.add_labels(gh, repo, issue, *want)
    upsert_comment(gh, repo, issue, body(data, dup, commit, run_url))
    print(f"triaged {repo}#{issue}: {', '.join(want)}")


PUBLISHERS = {"classifier": publish_classifier}
