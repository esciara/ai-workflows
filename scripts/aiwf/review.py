"""Workflow A, read side (steps 2-4 and 7): PR context for the agents, CI gate, risk tier, verdict rubric.

Runs in the `context` job with a read-only token. PR text and code are untrusted: they go into the agent's context file
between tags, never onto a command line. Agents get the code inline and no file tools (ADR-0034).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from aiwf import config

GhRunner = Callable[[list[str]], str]
CI_BUDGET = 20 * 60  # seconds; then the verdict is human-review (ADR-0034); a config key comes with WP12 budgets
CI_POLL = 20
CI_GRACE = 90  # with no check run at all, wait this long for CI to register before calling it "none"
CONTEXT_CAP = 120_000  # characters of diff + files + callers handed to an agent
GREEN = {"success", "neutral", "skipped"}
DEF_RE = re.compile(r"\b(?:def|function|func|fn|class)\s+([A-Za-z_][A-Za-z0-9_]{2,})")


def glob_re(pattern: str) -> re.Pattern[str]:
    """`**` spans directories, `*` and `?` stay within one path segment."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def risk_tier(paths: list[str], risk_paths: dict[str, list[str]]) -> str:
    for tier in ("high", "medium"):
        pats = [glob_re(p) for p in risk_paths.get(tier, [])]
        if any(p.match(path) for p in pats for path in paths):
            return tier
    return "low"


def ci_state(check_runs: list[dict[str, Any]], own_run_id: str, required: list[str] | None) -> str:
    """`pending`, `green`, `red` or `none` for the head SHA's check runs, ours excluded (ADR-0007, ADR-0034)."""
    own = f"/actions/runs/{own_run_id}/"
    runs = [r for r in check_runs if own not in (r.get("html_url") or "") and own not in (r.get("details_url") or "")]
    if required:
        runs = [r for r in runs if r["name"] in required]
        if {r["name"] for r in runs} != set(required):
            return "pending"
    if not runs:
        return "none"
    if any(r["status"] != "completed" for r in runs):
        return "pending"
    return "green" if all(r["conclusion"] in GREEN for r in runs) else "red"


def wait_ci(gh: GhRunner, repo: str, sha: str, own_run_id: str, required: list[str] | None,
            budget: float = CI_BUDGET, poll: float = CI_POLL, sleep: Callable[[float], None] = time.sleep) -> str:
    """Final CI state, or `timeout` when checks are still running after `budget` seconds."""
    waited = 0.0
    while True:
        runs = json.loads(gh(["api", "--paginate", "--slurp", f"repos/{repo}/commits/{sha}/check-runs?per_page=100"]))
        state = ci_state([r for page in runs for r in page["check_runs"]], own_run_id, required)
        if state in ("green", "red") or (state == "none" and waited >= CI_GRACE):
            return state
        if waited >= budget:
            return "timeout"
        sleep(poll)
        waited += poll


def verdict(findings: list[dict[str, Any]], facts: dict[str, Any]) -> tuple[str, list[str]]:
    """The spec's rubric, first matching row wins; returns (label, reasons)."""
    blocking = sum(f["severity"] == "blocking" for f in findings)
    if blocking or facts["ci"] == "red":
        return "ai-review: changes-requested", [r for r in (
            f"{blocking} blocking finding(s)" if blocking else "", "a CI check is red" if facts["ci"] == "red" else "") if r]
    reasons = [r for r in (
        "risk tier high" if facts["tier"] == "high" else "",
        "no linked issue" if not facts["linked_issues"] else "",
        f"{facts['changed_lines']} changed lines (> {facts['human_review_lines']})"
        if facts["changed_lines"] > facts["human_review_lines"] else "",
        f"CI still running after {CI_BUDGET // 60} min" if facts["ci"] == "timeout" else "",
    ) if r]
    if reasons:
        return "ai-review: human-review", reasons
    return "ai-review: merge", ["no blocking findings, CI green, tier " + facts["tier"]]


def changed_names(diff: str) -> list[str]:
    """Function and class names defined on changed lines or in hunk headers of `diff`."""
    names: list[str] = []
    for line in diff.splitlines():
        if line.startswith(("+++", "---")) or not line.startswith(("+", "-", "@@")):
            continue
        names += [n for n in DEF_RE.findall(line) if n not in names]
    return names[:20]


def callers(names: list[str], workdir: Path, limit: int = 15) -> str:
    out = []
    for name in names:
        proc = subprocess.run(["git", "grep", "-n", "-w", "-I", "-e", name], cwd=workdir, capture_output=True, text=True)
        hits = [h for h in proc.stdout.splitlines() if not DEF_RE.search(h.split(":", 2)[-1])][:limit]
        if hits:
            out.append(f"### {name}\n" + "\n".join(hits))
    return "\n\n".join(out)


def capped(parts: list[tuple[str, str]], cap: int = CONTEXT_CAP) -> str:
    out, left = [], cap
    for tag, text in parts:
        if len(text) > left:
            text = text[: max(left, 0)] + f"\n[... truncated: context cap of {cap} characters reached]"
        left -= len(text)
        out.append(f"<{tag}>\n{text}\n</{tag}>")
    return "\n\n".join(out)


def gather(gh: GhRunner, repo: str, number: int, sha: str, workdir: Path, cfg: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """(agent context text, facts) for PR `number` at head `sha`; `workdir` is a checkout of that head."""
    pr = json.loads(gh(["api", f"repos/{repo}/pulls/{number}"]))
    files = json.loads(gh(["api", "--paginate", "--slurp", f"repos/{repo}/pulls/{number}/files?per_page=100"]))
    files = [f for page in files for f in page]
    paths = sorted({f["filename"] for f in files} | {f["previous_filename"] for f in files if f.get("previous_filename")})
    diff = gh(["api", f"repos/{repo}/pulls/{number}", "-H", "Accept: application/vnd.github.diff"])
    owner, name = repo.split("/")
    q = ("query($o:String!,$n:String!,$p:Int!){repository(owner:$o,name:$n){pullRequest(number:$p){"
         "closingIssuesReferences(first:5){nodes{number title body}}}}}")
    gql = json.loads(gh(["api", "graphql", "-f", f"query={q}", "-f", f"o={owner}", "-f", f"n={name}", "-F", f"p={number}"]))
    issues = gql["data"]["repository"]["pullRequest"]["closingIssuesReferences"]["nodes"]
    touched = []
    for f in files:
        p = workdir / f["filename"]
        if f["status"] != "removed" and p.is_file() and p.stat().st_size < 200_000:
            touched.append(f'<file path="{f["filename"]}">\n{p.read_text(errors="replace")}\n</file>')
    pr_text = f"Title: {pr['title']}\n\n{pr.get('body') or ''}"
    issue_text = "\n\n".join(f"Issue #{i['number']}: {i['title']}\n\n{i.get('body') or ''}" for i in issues) or "(none)"
    context = capped([("pr_description", pr_text), ("linked_issues", issue_text), ("diff", diff),
                      ("touched_files", "\n".join(touched)), ("callers", callers(changed_names(diff), workdir))])
    facts = {
        "sha": sha,
        "tier": risk_tier(paths, cfg["risk_paths"]),
        "changed_lines": pr["additions"] + pr["deletions"],
        "human_review_lines": cfg["limits"]["human_review_lines"],
        "linked_issues": [i["number"] for i in issues],
    }
    return context, facts


def cmd_review_context(args: argparse.Namespace) -> int:
    cfg = json.loads(os.environ["AIWF_CONFIG"])
    context, facts = gather(config.run_gh, args.repo, args.pr, args.sha, Path(args.workdir), cfg)
    facts["ci"] = wait_ci(config.run_gh, args.repo, args.sha, os.environ.get("GITHUB_RUN_ID", ""), cfg.get("required_checks"))
    Path(args.out).write_text(context, encoding="utf-8")
    print(f"context: {len(context)} chars; facts: {json.dumps(facts)}")
    if os.environ.get("GITHUB_OUTPUT"):
        from aiwf.cli import write_outputs
        write_outputs(os.environ["GITHUB_OUTPUT"], {"facts": json.dumps(facts, separators=(",", ":"))})
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("review-context", help="Workflow A: gather PR context, wait for CI, risk tier (env AIWF_CONFIG)")
    p.add_argument("--repo", required=True)
    p.add_argument("--pr", required=True, type=int)
    p.add_argument("--sha", required=True)
    p.add_argument("--workdir", required=True, help="checkout of the PR head (read as text, never executed)")
    p.add_argument("--out", required=True, help="file for the agents' context")
    p.set_defaults(func=cmd_review_context)
