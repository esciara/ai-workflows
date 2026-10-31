"""Workflow A, write side (steps 6-9): the verifier's decisions applied to the 4 passes' findings, the verdict, the one
summary comment found by its marker (with the last run's findings marked resolved or still open), the run's one GitHub
review carrying the new inline comments (never Approve; ADR-0016), the verdict label.

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
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from aiwf import config, publish, review
from aiwf import review_placement as placement

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
FIELDS = ("severity", "path", "line", "title", "detail", "suggested_fix", "end_line", "replacement", "also")
RANK = {"blocking": 0, "should-fix": 1, "nit": 2}
MAX_ROWS = 30  # findings shown in the table; all of them count toward the verdict
MAX_STATE = 40  # open findings carried in the state block to the next run
MAX_BODY = 60_000  # GitHub caps a comment at 65,536 characters
THREAD_RE = re.compile(r"https://[A-Za-z0-9.-]+/[A-Za-z0-9._/-]+/pull/\d+#discussion_r\d+\Z")
FINDING_RE = re.compile(r"<!-- ai-review:finding ([0-9a-f]{12}\+*) -->")
CHANGES = "ai-review: changes-requested"
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
            thread = {"thread": p["thread"]} if p.get("thread") else {}
            if cid in confirmed and cid not in used:
                used.add(cid)
                findings.append({**confirmed[cid], "id": p["id"], "still_open": True, **thread})
            else:
                findings.append({**{k: p[k] for k in FIELDS if k in p}, "id": p["id"], "still_open": True, **thread})
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


def row(i: int, f: dict[str, Any]) -> str:
    """One summary table row; the place links to the finding's inline thread when it has one."""
    where = clean(f["path"], 200) + (f":{f['line']}" if f.get("line") else "")
    if f.get("thread"):
        where = f"[{where}]({f['thread']})"
    if f.get("also"):
        where += f" (+{len(f['also'])} more)"
    tag = "(still open) " if f["still_open"] else ""
    return (f"| {i} | {f['severity']} | {where} | {tag}{clean(f['title'], 120)}: {clean(f['detail'])} "
            f"| {clean(f.get('suggested_fix') or '-', 400)} |")


def render(data: dict[str, Any], facts: dict[str, Any], label: str, reasons: list[str], prev: dict[str, Any] | None,
           state: dict[str, Any], run_url: str, rows: int = MAX_ROWS) -> str:
    """The summary comment; `data` holds summary, findings, history, counts, tests, suspicious_instructions and notes."""
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
    main = [f for f in findings if f.get("place") != placement.COLLAPSED]
    nits = [f for f in findings if f.get("place") == placement.COLLAPSED]
    head = ["| # | Severity | Where | Finding | Suggested fix |", "|---|---|---|---|---|"]
    if main:
        lines += head + [row(i, f) for i, f in enumerate(main[:rows], 1)]
        if len(main) > rows:
            lines += ["", f"{len(main) - rows} more finding(s) not shown; they count toward the verdict."]
    else:
        lines.append("No findings." if not nits else "No findings beyond the nits below.")
    if nits:
        shown = nits[:rows]
        lines += ["", f"<details><summary>{len(nits)} nit(s), summary only</summary>", "", *head,
                  *[row(i, f) for i, f in enumerate(shown, len(main[:rows]) + 1)], "", "</details>"]
    for note in data.get("notes", []):
        lines += ["", f"**Note:** {note}"]
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
               and (f.get("line") is None or isinstance(f.get("line"), int))
               and (f.get("thread") is None or (isinstance(f["thread"], str) and THREAD_RE.match(f["thread"])))
               for f in prev["open"])


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


def inline_comment(f: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    """The review comment for an inline finding: its text, the other places, a `suggestion` block when it fits."""
    parts = [f"**{f['severity']}** · {clean(f['title'], 120)}", "", clean(f["detail"])]
    if f.get("suggested_fix"):
        parts += ["", f"Suggested fix: {clean(f['suggested_fix'], 400)}"]
    if f.get("also"):
        parts += ["", "Same problem also at: " + ", ".join(
            f"{clean(a['path'], 200)}" + (f":{a['line']}" if a.get("line") else "") for a in f["also"])]
    out: dict[str, Any] = {"path": f["path"], "line": f["line"], "side": "RIGHT"}
    sug = placement.suggestion(f, facts)
    if sug:
        start, end, code = sug
        fence = placement.fence(code)
        parts += ["", f"{fence}suggestion", code, fence]
        if end > start:
            out.update(start_line=start, start_side="RIGHT", line=end)
    parts += ["", f"<!-- ai-review:finding {f['id']} -->"]
    return {**out, "body": "\n".join(parts)}


def bot_changes_requested(gh: publish.GhRunner, repo: str, number: int) -> list[int]:
    """Ids of our own reviews that still request changes."""
    pages = json.loads(gh(["api", "--paginate", "--slurp", f"repos/{repo}/pulls/{number}/reviews?per_page=100"]))
    return [r["id"] for page in pages for r in page if r["user"]["login"] == BOT and r["state"] == "CHANGES_REQUESTED"]


def post_review(gh: publish.GhRunner, repo: str, number: int, payload: dict[str, Any]) -> dict[str, Any]:
    assert payload["event"] in ("REQUEST_CHANGES", "COMMENT")  # never APPROVE (spec, Workflow A step 8)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(payload, fh)
    try:
        return json.loads(gh(["api", "-X", "POST", f"repos/{repo}/pulls/{number}/reviews", "--input", fh.name]) or "{}")
    finally:
        os.unlink(fh.name)


def send_review(gh: publish.GhRunner, repo: str, number: int, facts: dict[str, Any], label: str, findings: list[dict[str, Any]],
                summary_url: str) -> list[str]:
    """At most one GitHub review for this run (ADR-0016): Request changes for `changes-requested`, else Comment, with
    the new inline comments; none when there is nothing new and the review state would not change. Our earlier
    Request changes reviews are dismissed once the verdict leaves `changes-requested`. Sets `thread` on findings
    commented inline; returns notes for the summary."""
    notes: list[str] = []
    sha = facts["sha"]
    new = [f for f in findings if f["place"] == placement.INLINE and not f.get("thread")]
    blocking = label == CHANGES
    active = bot_changes_requested(gh, repo, number)
    link = f"[summary]({summary_url})" if summary_url else "summary comment"
    if new or (blocking and not active):
        event = "REQUEST_CHANGES" if blocking else "COMMENT"
        payload = {"commit_id": sha, "event": event, "body": f"AI review — {HEADINGS[label]}. Details in the {link}.",
                   "comments": [inline_comment(f, facts) for f in new]}
        review_obj = None
        for _ in range(3):
            try:
                review_obj = post_review(gh, repo, number, payload)
                break
            except RuntimeError as exc:
                msg = str(exc)
                print(f"::warning title=Review not accepted::{msg[:300]}")
                if "own pull request" in msg and payload["event"] == "REQUEST_CHANGES":
                    payload["event"] = "COMMENT"  # GitHub refuses Request changes on the token's own PR
                    notes.append("GitHub does not let this workflow request changes on its own pull request; "
                                 "the review was sent as a comment.")
                elif payload["comments"]:
                    payload["comments"] = []
                    for f in new:
                        f["place"] = placement.GENERAL
                    notes.append("GitHub refused the inline comments; their findings are listed here only.")
                else:
                    break
        if review_obj is None:
            notes.append("The GitHub review could not be submitted; see the run log.")
        elif payload["comments"]:
            rid = review_obj["id"]
            pages = json.loads(gh(["api", "--paginate", "--slurp",
                                   f"repos/{repo}/pulls/{number}/reviews/{rid}/comments?per_page=100"]))
            threads = {m.group(1): c["html_url"] for page in pages for c in page
                       if (m := FINDING_RE.search(c.get("body") or "")) and THREAD_RE.match(c.get("html_url") or "")}
            for f in new:
                f["thread"] = threads.get(f["id"])
    if not blocking:
        for rid in active:
            try:
                gh(["api", "-X", "PUT", f"repos/{repo}/pulls/{number}/reviews/{rid}/dismissals",
                    "-f", f"message=Superseded: the AI review of {sha[:7]} no longer requests changes; see the "
                          f"{summary_url or 'summary comment'}.", "-f", "event=DISMISS"])
            except RuntimeError as exc:
                print(f"::warning title=Review not dismissed::{str(exc)[:300]}")
                notes.append("An earlier Request changes review from this workflow could not be dismissed; "
                             "a maintainer can dismiss it by hand.")
                break
    return notes


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
    for f in findings:  # a still-open finding keeps its thread; it is not commented again
        f["place"] = placement.INLINE if f.get("thread") else placement.place(f, facts)

    def upsert(cid: int | None) -> tuple[int | None, str]:
        """Create or update the summary comment; returns (id, html_url)."""
        state = {"v": STATE_V, "sha": facts["sha"], "verdict": label, "aiwf_sha": aiwf_sha, "run": run_url,
                 "usage": usage["total"],
                 "open": [{"id": f["id"], "severity": f["severity"], "path": f["path"][:300], "line": f.get("line"),
                           "title": f["title"][:120], "detail": f["detail"][:300],
                           **({"thread": f["thread"]} if f.get("thread") else {})} for f in findings[:MAX_STATE]]}
        rows = MAX_ROWS
        body = render(data, facts, label, reasons, prev, state, run_url, rows)
        while len(body) > MAX_BODY and rows > 0:
            rows = max(rows - 5, 0)
            body = render(data, facts, label, reasons, prev, state, run_url, rows)
        if cid is None:
            out = gh(["api", "-X", "POST", f"repos/{repo}/issues/{number}/comments", "-f", f"body={body}"])
        else:
            out = gh(["api", "-X", "PATCH", f"repos/{repo}/issues/comments/{cid}", "-f", f"body={body}"])
        got = json.loads(out or "{}")
        return got.get("id", cid), got.get("html_url", "")

    comment_id, summary_url = upsert(comment_id)
    notes = send_review(gh, repo, number, facts, label, findings, summary_url)
    if notes or any(f.get("thread") and not f["still_open"] for f in findings):
        data["notes"] = notes
        upsert(comment_id)  # now with links to the new inline threads, and any notes
    set_verdict_label(gh, repo, number, label)
    print(f"{repo}#{number}: {label} ({'; '.join(reasons)}); verification {json.dumps(counts)}")
    print("placement: " + json.dumps({p: sum(f["place"] == p for f in findings)
                                      for p in (placement.INLINE, placement.COLLAPSED, placement.GENERAL)}))
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
