"""Publishers for Workflow B (issue triage). B1: labels and one triage comment from the classifier's checked JSON.
It also writes the "New issue triaged" chat alert (spec: Chat notifications) to $GITHUB_OUTPUT as `alert_text` and
`alert_url`; triage.yml's notify job sends it for new issues only. The alert holds only fields the orchestrator checked
(type, checked duplicate number, labels) and the repo name, never the issue title or other agent text.

The classifier's references (duplicate issue, fixing commit or PR) must be among the candidates pass 2 was shown (env
AIWF_TRIAGE_CANDIDATES, from the candidates job; missing means none) and are checked against the repo before they are
linked: an unlisted, unknown or invalid reference is dropped, never posted. A fix is only "possibly fixed by" (ADR-0035): reproducing the
bug (B2) confirms it. Triage never closes an issue.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import quote

from aiwf import commands, publish
from aiwf.ghapi import get_or_none, remove_label, upsert_marker_comment

MARKER = "<!-- ai-workflows:triage -->"
TYPE_LABELS = {"bug": "type: bug", "feature": "type: feature", "question": "type: question"}
DUPLICATE = "triage: duplicate"
NEEDS_HUMAN = "triage: needs-human"
RANGE_ENV = "AIWF_FIX_RANGE_CONFIDENCE"  # `low` when the fix candidates were not from the reported version
CANDIDATES_ENV = "AIWF_TRIAGE_CANDIDATES"  # {"issues": [n], "commits": [sha], "prs": [n]}: what pass 2 was shown
B1_LABELS = (*TYPE_LABELS.values(), DUPLICATE, NEEDS_HUMAN)  # cleared on /retriage before the new result
WAITS_FOR_REPRODUCE = (f"Bug from a reporter outside `maintainers`: reproducing it runs code, so it waits for a maintainer to "
                       f"comment `/reproduce` (ADR-0037). Labelled `{NEEDS_HUMAN}`.")


def shown_candidates() -> dict[str, set[Any]]:
    """The candidates pass 2 was shown (env CANDIDATES_ENV); an unset or malformed value means none (fail closed)."""
    try:
        raw = json.loads(os.environ.get(CANDIDATES_ENV) or "{}")
    except json.JSONDecodeError:
        raw = {}
    raw = raw if isinstance(raw, dict) else {}

    def items(key: str, kind: type) -> set[Any]:
        value = raw.get(key)
        return {v for v in value if isinstance(v, kind) and not isinstance(v, bool)} if isinstance(value, list) else set()

    return {"issues": items("issues", int), "commits": items("commits", str), "prs": items("prs", int)}


def was_shown(shown: dict[str, set[Any]], name: str, value: Any) -> bool:
    """`duplicate_of` number or `possibly_fixed_by` ref was in pass 2's candidates (a commit by its listed prefix)."""
    if name == "duplicate_of":
        return isinstance(value, int) and value in shown["issues"]
    ref = str(value.get("ref") or "")
    if value.get("kind") == "commit":
        return len(ref) >= 7 and any(sha.startswith(ref) for sha in shown["commits"])
    return ref.isdigit() and int(ref) in shown["prs"]


def check_duplicate(gh: publish.GhRunner, repo: str, issue: int, number: int | None) -> dict[str, Any] | None:
    """The issue `number` when it is another real issue, open or closed as completed; else None."""
    if not number or number == issue:
        return None
    other = get_or_none(gh, f"repos/{repo}/issues/{number}")
    if not other or "pull_request" in other:
        return None
    if other["state"] != "open" and other.get("state_reason") != "completed":
        return None
    return other


def check_commit(gh: publish.GhRunner, repo: str, branch: str, sha: str | None) -> dict[str, Any] | None:
    """The commit when it exists and is on `branch` (the branch is ahead of it or at it); else None."""
    if not sha:
        return None
    commit = get_or_none(gh, f"repos/{repo}/commits/{sha}")
    if not commit:
        return None
    cmp = get_or_none(gh, f"repos/{repo}/compare/{commit['sha']}...{quote(branch, safe='')}")
    return commit if cmp and cmp.get("status") in {"ahead", "identical"} else None


def check_pr(gh: publish.GhRunner, repo: str, branch: str, number: int) -> dict[str, Any] | None:
    """The pull request when it exists and was merged into `branch`; else None."""
    pr = get_or_none(gh, f"repos/{repo}/pulls/{number}")
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
         run_url: str, suspicious: list[str] | None = None, waits: bool = False) -> str:
    lines = [MARKER, f"**AI triage:** {data['type']} ({data['confidence']} confidence). {publish.clean(data['reason'])}"]
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
    if waits:
        lines += ["", WAITS_FOR_REPRODUCE]
    if suspicious:
        lines += ["", publish.injection_line(suspicious)]
    if run_url:
        lines += ["", f"[Run]({run_url})"]
    return "\n".join(lines)


def suspicious_instructions(data: dict[str, Any]) -> list[str]:
    """The classifier's and the extractor's quotes of instructions found in the issue (env EXTRACT_JSON, read
    leniently: the extract job's output was schema-checked by Claude; a missing or odd value adds nothing)."""
    try:
        extract = json.loads(os.environ.get("EXTRACT_JSON") or "{}")
    except json.JSONDecodeError:
        extract = {}
    found = [*(data.get("suspicious_instructions") or [])]
    if isinstance(extract, dict) and isinstance(extract.get("suspicious_instructions"), list):
        found += [s for s in extract["suspicious_instructions"] if isinstance(s, str)]
    return list(dict.fromkeys(s for s in found if s.strip()))[:10]


def labels_for(data: dict[str, Any], duplicate: bool, waits: bool = False) -> list[str]:
    out = [TYPE_LABELS[data["type"]]]
    if duplicate:
        out.append(DUPLICATE)
    if data["confidence"] == "low" or waits:
        out.append(NEEDS_HUMAN)
    return out


def alert(repo: str, issue: int, kind: str, duplicate_of: int | None, needs_human: bool, server: str
          ) -> tuple[str, str]:
    """The "New issue triaged" alert: `#n triaged as <type>`, plus `duplicate of #k` / `needs a person`; its link."""
    parts = [f"[{repo}] #{issue} triaged as {kind}"]
    if duplicate_of:
        parts.append(f"duplicate of #{duplicate_of}")
    if needs_human:
        parts.append("needs a person")
    return ", ".join(parts), f"{server}/{repo}/issues/{issue}"


def write_alert(text: str, url: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"alert_text={text}\nalert_url={url}\n")


def goes_to_b2(data: dict[str, Any], duplicate: bool) -> bool:
    """A bug B1 hands to B2: not a duplicate, not low confidence (those stop with a person)."""
    return data["type"] == "bug" and not duplicate and data["confidence"] != "low"


def author_trusted(gh: publish.GhRunner, repo: str, issue: dict[str, Any]) -> bool:
    """ADR-0037 gate: the issue author passes the command-author check (ADR-0005)."""
    login = (issue.get("user") or {}).get("login") or ""
    maintainers = json.loads(os.environ.get("AIWF_CONFIG") or "{}").get("maintainers", [])
    if not login or login.lower() not in {m.lower() for m in maintainers}:
        return False
    return commands.authorize(login, maintainers, commands.repo_permission(repo, login, gh))


def start_reproduce() -> None:
    """Job output `reproduce=true`: the triage workflow's B2 jobs run next in this run."""
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write("reproduce=true\n")


def publish_classifier(data: dict[str, Any], repo: str, issue: int, run_url: str, gh: publish.GhRunner) -> None:
    item = get_or_none(gh, f"repos/{repo}/issues/{issue}") or {}
    current = {lb["name"] for lb in item.get("labels", [])}
    branch = (get_or_none(gh, f"repos/{repo}") or {}).get("default_branch", "main")
    shown = shown_candidates()
    dup_ref = (data.get("duplicate_of") or {}).get("number")
    dup = check_duplicate(gh, repo, issue, dup_ref) if dup_ref and was_shown(shown, "duplicate_of", dup_ref) else None
    fix_ref = data.get("possibly_fixed_by") if data["type"] == "bug" else None
    fix = check_fix(gh, repo, branch, fix_ref) if fix_ref and was_shown(shown, "possibly_fixed_by", fix_ref) else None
    for name, value, ok in (("duplicate_of", dup_ref, dup), ("possibly_fixed_by", data.get("possibly_fixed_by"), fix)):
        if value and not ok:
            print(f"::warning title=Classifier reference dropped::{name}={json.dumps(value)} is not a valid reference")
    fix_conf = fix_confidence(data, os.environ.get(RANGE_ENV, "")) if fix else ""
    to_b2 = goes_to_b2(data, is_duplicate(data, dup))
    trusted = to_b2 and author_trusted(gh, repo, item)
    waits = to_b2 and not trusted
    want = labels_for(data, is_duplicate(data, dup), waits)
    if publish.ERROR_LABEL in current:  # left by an earlier run (ADR-0045)
        remove_label(gh, repo, issue, publish.ERROR_LABEL)
    for label in B1_LABELS:
        if label in current and label not in want:
            remove_label(gh, repo, issue, label)
    publish.add_labels(gh, repo, issue, *want)
    upsert_marker_comment(gh, repo, issue, MARKER, body(data, dup, fix, fix_conf, run_url, suspicious_instructions(data), waits))
    print(f"triaged {repo}#{issue}: {', '.join(want)}")
    dup_number = dup["number"] if dup and DUPLICATE in want else None
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    write_alert(*alert(repo, issue, data["type"], dup_number, NEEDS_HUMAN in want, server))
    if trusted:
        start_reproduce()


CAPPED_TEXT = "Automatic triage limit reached for today; a maintainer can run `/retriage`."


def publish_capped(repo: str, issue: int, gh: publish.GhRunner) -> None:
    """ADR-0058: a capped issue ran no agent. `triage: needs-human` and the sticky triage comment, fixed text only."""
    publish.add_labels(gh, repo, issue, NEEDS_HUMAN)
    upsert_marker_comment(gh, repo, issue, MARKER, f"{MARKER}\n**AI triage:** {CAPPED_TEXT}")
    print(f"triage capped {repo}#{issue}: {NEEDS_HUMAN}")


PUBLISHERS = {"classifier": publish_classifier}
