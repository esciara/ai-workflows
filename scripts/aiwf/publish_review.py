"""Workflow A, write side (steps 6-9): the verifier's decisions applied to the 4 passes' findings, the verdict, the one
summary comment found by its marker (with the last run's findings marked resolved or still open), the verdict label.

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
from pathlib import Path
from typing import Any
from urllib.parse import quote

from aiwf import config, publish, review

MARKER = "<!-- ai-review:summary v1 -->"
STATE_V = 2  # v1 (WP2a) kept finding keys only; its state reads as no prior state
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
FIELDS = ("severity", "path", "line", "title", "detail", "suggested_fix")
RANK = {"blocking": 0, "should-fix": 1, "nit": 2}
MAX_ROWS = 30  # findings shown in the table; all of them count toward the verdict
MAX_STATE = 40  # open findings carried in the state block to the next run
MAX_BODY = 60_000  # GitHub caps a comment at 65,536 characters
USAGE_SUM = ("cost_usd", "turns", "duration_ms", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")


def clean(text: str, limit: int = 600) -> str:
    """One table-safe line: no mentions, HTML, markers or pipes."""
    text = " ".join(str(text).split())[:limit]
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("@", "@&#8203;").replace("|", "\\|")


def key(f: dict[str, Any]) -> str:
    """Id of a new finding, kept in the state block so the next run can mark it resolved or still open."""
    return hashlib.sha256(f"{f['path']}\n{' '.join(f['title'].lower().split())}".encode()).hexdigest()[:12]


def combine(passes: dict[str, dict[str, Any]], verify: dict[str, Any], prev_open: list[dict[str, Any]]
            ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """(findings, history, counts) from the passes' candidates, the verifier's answer and the last run's open findings.

    Only candidates the verifier confirms are kept (step 6), with its severity; a candidate it does not mention is
    dropped and counted as unchecked. Each previous finding is resolved or still open with a reason (step 9); a still
    open one stays a finding (and counts toward the verdict) under its old id, with the matching candidate's fresher
    text when the verifier names one. Ids the verifier invents match nothing and are ignored."""
    cands = {c["id"]: c for c in review.candidates(passes)}
    decisions: dict[str, dict[str, Any]] = {}
    for d in verify["decisions"]:
        if d["id"] in cands:
            decisions.setdefault(d["id"], d)
    confirmed = {cid: {**{k: c[k] for k in FIELDS if k in c}, "severity": decisions[cid]["severity"]}
                 for cid, c in cands.items() if decisions.get(cid, {}).get("verdict") == "confirmed"}
    prev_dec: dict[str, dict[str, Any]] = {}
    for d in verify["previous"]:
        prev_dec.setdefault(d["id"], d)
    findings, history, used = [], [], set()
    for p in prev_open:
        d = prev_dec.get(p["id"]) or {"status": "still-open", "reason": "not re-checked by the verifier", "candidate": None}
        history.append({"title": p["title"], "path": p["path"], "status": d["status"], "reason": d["reason"]})
        if d["status"] == "still-open":
            cid = d.get("candidate")
            if cid in confirmed and cid not in used:
                used.add(cid)
                findings.append({**confirmed[cid], "id": p["id"], "still_open": True})
            else:
                findings.append({**{k: p[k] for k in FIELDS if k in p}, "id": p["id"], "still_open": True})
    seen = {f["id"] for f in findings}
    for cid, c in confirmed.items():
        if cid not in used:
            fid = key(c)
            while fid in seen:
                fid += "+"
            seen.add(fid)
            findings.append({**c, "id": fid, "still_open": False})
    findings.sort(key=lambda f: RANK[f["severity"]])
    verdicts = [decisions[cid]["verdict"] for cid in cands if cid in decisions]
    counts = {"candidates": len(cands), "confirmed": verdicts.count("confirmed"), "refuted": verdicts.count("refuted"),
              "duplicate": verdicts.count("duplicate"), "unchecked": len(cands) - len(decisions),
              "resolved": sum(h["status"] == "resolved" for h in history),
              "still_open": sum(h["status"] == "still-open" for h in history), "new": len(confirmed) - len(used)}
    return findings, history, counts


def since_last(prev: dict[str, Any] | None, history: list[dict[str, Any]], counts: dict[str, int]) -> list[str]:
    if prev is None:
        return ["**Since last run:** first run."]
    lines = [f"**Since last run:** {counts['resolved']} resolved, {counts['still_open']} still open, {counts['new']} new."]
    for h in history[:MAX_STATE]:
        lines.append(f"- {h['status']}: {clean(h['title'], 120)} ({clean(h['path'], 200)}) — {clean(h['reason'], 300)}")
    return lines


def state_json(state: dict[str, Any]) -> str:
    """The state as one JSON line that cannot close the HTML comment around it."""
    text = json.dumps(state, separators=(",", ":"), sort_keys=True)
    return text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def render(data: dict[str, Any], facts: dict[str, Any], label: str, reasons: list[str], prev: dict[str, Any] | None,
           state: dict[str, Any], run_url: str, rows: int = MAX_ROWS) -> str:
    """The summary comment; `data` holds summary, findings, history, counts, tests and suspicious_instructions."""
    findings, counts = data["findings"], data["counts"]
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
    if findings:
        lines += ["| # | Severity | Where | Finding | Suggested fix |", "|---|---|---|---|---|"]
        for i, f in enumerate(findings[:rows], 1):
            where = clean(f["path"], 200) + (f":{f['line']}" if f.get("line") else "")
            tag = "(still open) " if f["still_open"] else ""
            lines.append(f"| {i} | {f['severity']} | {where} | {tag}{clean(f['title'], 120)}: {clean(f['detail'])} "
                         f"| {clean(f.get('suggested_fix') or '-', 400)} |")
        if len(findings) > rows:
            lines += ["", f"{len(findings) - rows} more finding(s) not shown; they count toward the verdict."]
    else:
        lines.append("No findings.")
    lines += ["", f"**Tests:** {clean(data['tests'], 400)}"]
    checked = (f"**Verification:** {counts['candidates']} candidate finding(s) from {len(review.PASSES)} passes: "
               f"{counts['confirmed']} confirmed, {counts['refuted']} refuted, {counts['duplicate']} duplicate")
    lines += ["", checked + (f", {counts['unchecked']} not checked (dropped)." if counts["unchecked"] else ".")]
    if data.get("suspicious_instructions"):
        lines += ["", "**Possible prompt injection (ignored):** "
                  + "; ".join(clean(s, 200) for s in data["suspicious_instructions"])]
    lines += ["", *since_last(prev, data["history"], counts)]
    if run_url:
        lines += ["", f"[Run]({run_url})"]
    lines += ["", f"<!-- ai-review:state {state_json(state)} -->"]
    return "\n".join(lines)


def valid_state(prev: Any) -> bool:
    if not (isinstance(prev, dict) and prev.get("v") == STATE_V and isinstance(prev.get("open"), list)):
        return False
    return all(isinstance(f, dict) and isinstance(f.get("id"), str) and f.get("severity") in RANK
               and all(isinstance(f.get(k), str) for k in ("path", "title", "detail"))
               and (f.get("line") is None or isinstance(f.get("line"), int)) for f in prev["open"])


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
            if not valid_state(prev):
                prev = None  # missing, invalid or older state: treated as no prior state (ADR-0021)
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


def total_usage(usage: dict[str, Any]) -> dict[str, Any]:
    """Per-agent usage plus `total`, summed over the agents (plan: Usage limits)."""
    agents = {k: v for k, v in usage.items() if isinstance(v, dict)}
    total = {f: sum(v[f] for v in agents.values() if isinstance(v.get(f), (int, float))) for f in USAGE_SUM}
    total["cost_usd"] = round(total["cost_usd"], 4)
    return {**agents, "total": total, "agents": len(agents)}


def publish_review(passes_raw: dict[str, str], verify_raw: str, facts: dict[str, Any], usage: dict[str, Any],
                   repo: str, number: int, run_url: str, aiwf_sha: str, gh: publish.GhRunner) -> bool:
    """Validate the 4 passes and the verifier, decide, then create or update the summary comment and set the label."""
    try:
        passes = {}
        for name in review.PASSES:
            try:
                passes[name] = publish.validate("review", passes_raw.get(name))
            except publish.InvalidOutput as exc:
                raise publish.InvalidOutput(f"{name} pass: {exc}") from None
        try:
            verify = publish.validate("review-verify", verify_raw)
        except publish.InvalidOutput as exc:
            raise publish.InvalidOutput(f"verifier: {exc}") from None
    except publish.InvalidOutput as exc:
        print(f"::error title=Invalid agent output::{exc}")
        set_verdict_label(gh, repo, number, publish.ERROR_LABEL)  # removes pending and any stale verdict
        return False
    comment_id, prev = find_summary(gh, repo, number)
    findings, history, counts = combine(passes, verify, prev["open"] if prev else [])
    if counts["unchecked"]:
        print(f"::warning title=Unchecked findings::the verifier skipped {counts['unchecked']} candidate(s); dropped")
    label, reasons = review.verdict(findings, facts)
    suspicious = list(dict.fromkeys(s for d in (*passes.values(), verify) for s in d["suspicious_instructions"]))[:10]
    data = {"summary": verify["summary"], "findings": findings, "history": history, "counts": counts,
            "tests": passes["tests"]["summary"], "suspicious_instructions": suspicious}
    usage = total_usage(usage)
    state = {"v": STATE_V, "sha": facts["sha"], "verdict": label, "aiwf_sha": aiwf_sha, "run": run_url,
             "usage": usage["total"],
             "open": [{"id": f["id"], "severity": f["severity"], "path": f["path"][:300], "line": f.get("line"),
                       "title": f["title"][:120], "detail": f["detail"][:300]} for f in findings[:MAX_STATE]]}
    rows = MAX_ROWS
    body = render(data, facts, label, reasons, prev, state, run_url, rows)
    while len(body) > MAX_BODY and rows > 0:
        rows = max(rows - 5, 0)
        body = render(data, facts, label, reasons, prev, state, run_url, rows)
    if comment_id is None:
        publish.comment(gh, repo, number, body)
    else:
        gh(["api", "-X", "PATCH", f"repos/{repo}/issues/comments/{comment_id}", "-f", f"body={body}"])
    set_verdict_label(gh, repo, number, label)
    print(f"{repo}#{number}: {label} ({'; '.join(reasons)}); verification {json.dumps(counts)}")
    print(f"usage: {json.dumps(usage)}")
    return True


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def cmd_review_publish(args: argparse.Namespace) -> int:
    facts = json.loads(os.environ.get("FACTS") or "null")
    if not isinstance(facts, dict):
        print("::error title=No review context::the context job produced no facts")
        set_verdict_label(config.run_gh, args.repo, args.pr, publish.ERROR_LABEL)
        return 1
    passes_dir = Path(args.passes_dir)
    passes_raw = {}
    for name in review.PASSES:
        try:
            passes_raw[name] = (passes_dir / f"{name}.json").read_text(encoding="utf-8")
        except OSError:
            passes_raw[name] = ""
    usage = {name: read_json(passes_dir / f"{name}.usage.json") for name in review.PASSES}
    try:
        usage["verify"] = json.loads(os.environ.get("USAGE") or "null")
    except json.JSONDecodeError:
        pass
    ok = publish_review(passes_raw, os.environ.get("VERIFY_JSON", ""), facts, usage, args.repo, args.pr,
                        args.run_url, os.environ.get("AIWF_SHA", ""), config.run_gh)
    return 0 if ok else 1


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("review-publish",
                       help="Workflow A: verify, verdict, summary comment, label (env VERIFY_JSON, FACTS, USAGE)")
    p.add_argument("--repo", required=True)
    p.add_argument("--pr", required=True, type=int)
    p.add_argument("--run-url", default="")
    p.add_argument("--passes-dir", required=True, help="the passes' answers, <pass>.json and <pass>.usage.json")
    p.set_defaults(func=cmd_review_publish)
