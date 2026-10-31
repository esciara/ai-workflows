"""Workflow A, write side (steps 7-9): verdict, the one summary comment found by its marker, the verdict label.

Workflow A publishes with `aiwf review-publish` rather than a `publish --kind` publisher, because the comment needs the
context job's facts (tier, CI, SHA) as well as the agent's JSON. Agent text is untrusted: every string is cleaned
before it reaches the comment, so it cannot mention anyone, add HTML or forge the marker or the state block.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from typing import Any
from urllib.parse import quote

from aiwf import config, publish, review

MARKER = "<!-- ai-review:summary v1 -->"
STATE_RE = re.compile(r"<!-- ai-review:state (\{.*?\}) -->\s*\Z", re.S)
BOT = "github-actions[bot]"  # the GITHUB_TOKEN identity; only its marker comments are trusted (ADR-0021)
PENDING = "ai-review: pending"
HEADINGS = {
    "ai-review: merge": "✅ Merge",
    "ai-review: changes-requested": "❌ Changes requested",
    "ai-review: human-review": "👀 Human review needed",
}
CI_TEXT = {"green": "green", "red": "red", "none": "no checks", "timeout": "still running (timed out)"}
PUBLISHERS: dict = {}  # see the module docstring


def clean(text: str, limit: int = 600) -> str:
    """One table-safe line: no mentions, HTML, markers or pipes."""
    text = " ".join(str(text).split())[:limit]
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("@", "@&#8203;").replace("|", "\\|")


def key(f: dict[str, Any]) -> str:
    """Stable id of a finding across runs (path + title), for 'since last run'."""
    return hashlib.sha256(f"{f['path']}\n{' '.join(f['title'].lower().split())}".encode()).hexdigest()[:12]


def since_last(prev: dict[str, Any] | None, keys: list[str]) -> str:
    if prev is None:
        return "first run."
    old = set(prev.get("open", []))
    return f"{len(old - set(keys))} resolved, {len(old & set(keys))} still open, {len(set(keys) - old)} new."


def render(data: dict[str, Any], facts: dict[str, Any], label: str, reasons: list[str], prev: dict[str, Any] | None,
           state: dict[str, Any], run_url: str) -> str:
    lines = [
        MARKER,
        f"## AI review — {HEADINGS[label]}",
        f"**Risk tier:** {facts['tier']} · **CI:** {CI_TEXT[facts['ci']]} · **Commit reviewed:** {facts['sha'][:7]}",
        "",
        f"**Summary** — {clean(data['summary'], 800)}",
        "",
        f"**Verdict:** {'; '.join(reasons)}.",
        "",
    ]
    if data["findings"]:
        lines += ["| # | Severity | Where | Finding | Suggested fix |", "|---|---|---|---|---|"]
        for i, f in enumerate(data["findings"], 1):
            where = clean(f["path"], 200) + (f":{f['line']}" if f.get("line") else "")
            lines.append(f"| {i} | {f['severity']} | {where} | {clean(f['title'], 120)}: {clean(f['detail'])} "
                         f"| {clean(f.get('suggested_fix') or '-', 400)} |")
    else:
        lines.append("No findings.")
    if data.get("suspicious_instructions"):
        lines += ["", "**Possible prompt injection (ignored):** "
                  + "; ".join(clean(s, 200) for s in data["suspicious_instructions"])]
    lines += ["", f"**Since last run:** {since_last(prev, state['open'])}"]
    if run_url:
        lines += ["", f"[Run]({run_url})"]
    lines += ["", f"<!-- ai-review:state {json.dumps(state, separators=(',', ':'), sort_keys=True)} -->"]
    return "\n".join(lines)


def find_summary(gh: publish.GhRunner, repo: str, number: int) -> tuple[int | None, dict[str, Any] | None]:
    """(comment id, prior state) of the bot's own summary comment; a forged marker from anyone else is ignored."""
    pages = json.loads(gh(["api", "--paginate", "--slurp", f"repos/{repo}/issues/{number}/comments?per_page=100"]))
    for c in (c for page in pages for c in page):
        body = c.get("body") or ""
        if c["user"]["login"] == BOT and body.startswith(MARKER):
            m = STATE_RE.search(body)
            try:
                prev = json.loads(m.group(1)) if m else None
            except json.JSONDecodeError:
                prev = None
            if not (isinstance(prev, dict) and prev.get("v") == 1 and isinstance(prev.get("open"), list)):
                prev = None  # missing or invalid state: treated as no prior state (ADR-0021)
            return c["id"], prev
    return None, None


def set_verdict_label(gh: publish.GhRunner, repo: str, number: int, label: str) -> None:
    for old in [PENDING, *HEADINGS]:
        if old != label:
            try:
                gh(["api", "-X", "DELETE", f"repos/{repo}/issues/{number}/labels/{quote(old, safe='')}"])
            except RuntimeError as exc:
                if "404" not in str(exc) and "Not Found" not in str(exc):
                    raise
    publish.add_labels(gh, repo, number, label)


def publish_review(raw: str, facts: dict[str, Any], usage: dict[str, Any] | None, repo: str, number: int,
                   run_url: str, aiwf_sha: str, gh: publish.GhRunner) -> bool:
    try:
        data = publish.validate("review", raw)
    except publish.InvalidOutput as exc:
        print(f"::error title=Invalid agent output::{exc}")
        set_verdict_label(gh, repo, number, publish.ERROR_LABEL)  # removes pending and any stale verdict
        return False
    label, reasons = review.verdict(data["findings"], facts)
    comment_id, prev = find_summary(gh, repo, number)
    state = {"v": 1, "sha": facts["sha"], "verdict": label, "open": [key(f) for f in data["findings"]],
             "aiwf_sha": aiwf_sha, "run": run_url, "usage": usage or {}}
    body = render(data, facts, label, reasons, prev, state, run_url)
    if comment_id is None:
        publish.comment(gh, repo, number, body)
    else:
        gh(["api", "-X", "PATCH", f"repos/{repo}/issues/comments/{comment_id}", "-f", f"body={body}"])
    set_verdict_label(gh, repo, number, label)
    print(f"{repo}#{number}: {label} ({'; '.join(reasons)}); usage {json.dumps(usage or {})}")
    return True


def cmd_review_publish(args: argparse.Namespace) -> int:
    facts = json.loads(os.environ.get("FACTS") or "null")
    if not isinstance(facts, dict):
        print("::error title=No review context::the context job produced no facts")
        set_verdict_label(config.run_gh, args.repo, args.pr, publish.ERROR_LABEL)
        return 1
    try:
        usage = json.loads(os.environ.get("USAGE") or "null")
    except json.JSONDecodeError:
        usage = None
    ok = publish_review(os.environ.get("AGENT_JSON", ""), facts, usage if isinstance(usage, dict) else None,
                        args.repo, args.pr, args.run_url, os.environ.get("AIWF_SHA", ""), config.run_gh)
    return 0 if ok else 1


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("review-publish", help="Workflow A: verdict, summary comment, label (env AGENT_JSON, FACTS, USAGE)")
    p.add_argument("--repo", required=True)
    p.add_argument("--pr", required=True, type=int)
    p.add_argument("--run-url", default="")
    p.set_defaults(func=cmd_review_publish)
