"""Per-run usage metrics (spec: Usage per run, ADR-0052): one JSON line per Workflow A run.

Each agent job saves the `result` message of claude-code-action's execution file, cut down to its numbers by jq, as
`<agent>.json` (artifact `review-usage-<agent>`); the `metrics` job joins them with the run's facts into one line, written to `metrics.jsonl`
(uploaded as the `ai-workflows-metrics` artifact) and printed to the log.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from aiwf import review

V = 1
AGENTS = (*review.PASSES, "verify")
USAGE_INTS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def _int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def usage_from_execution(log: Any) -> dict[str, Any] | None:
    """The numbers of the last `result` message of a claude-code-action execution file; None when there is none.

    Only numbers are kept: the result's text is the agent's answer to untrusted input and stays out of the metrics.
    """
    if not isinstance(log, list):
        return None
    results = [m for m in log if isinstance(m, dict) and m.get("type") == "result"]
    if not results:
        return None
    r = results[-1]
    usage = r.get("usage") if isinstance(r.get("usage"), dict) else {}
    cost = r.get("total_cost_usd")
    return {
        "duration_ms": _int(r.get("duration_ms")),
        "num_turns": _int(r.get("num_turns")),
        **{k: _int(usage.get(k)) for k in USAGE_INTS},
        "cost_usd": float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) else 0.0,
    }


def agents(usage_dir: Path) -> list[dict[str, Any]]:
    """One entry per agent that left a usage file, in AGENTS order; unreadable files are skipped."""
    out = []
    for name in AGENTS:
        try:
            data = json.loads((usage_dir / f"{name}.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        usage = usage_from_execution(data)
        if usage is not None:
            out.append({"agent": name, **usage})
    return out


def line(*, repo: str, run_id: int, run_attempt: int, pr: int, head_sha: str, aiwf_sha: str, verdict: str,
         started: float, now: float, usage_dir: Path) -> str:
    record = {
        "v": V, "workflow": "review", "repo": repo, "run_id": run_id, "run_attempt": run_attempt, "pr": pr,
        "head_sha": head_sha, "aiwf_sha": aiwf_sha, "verdict": verdict or None,
        "duration_s": round(max(now - started, 0.0), 1), "agents": agents(usage_dir),
    }
    return json.dumps(record, separators=(",", ":"), sort_keys=True)


def cmd_metrics(args: argparse.Namespace) -> int:
    text = line(repo=args.repo, run_id=args.run_id, run_attempt=args.run_attempt, pr=args.pr, head_sha=args.sha,
                aiwf_sha=os.environ.get("AIWF_SHA", ""), verdict=os.environ.get("VERDICT", ""),
                started=float(args.started or 0) or time.time(), now=time.time(), usage_dir=Path(args.usage_dir))
    Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(f"aiwf-metrics {text}")
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("review-metrics", help="Workflow A: the run's one metrics line (env AIWF_SHA, VERDICT)")
    p.add_argument("--repo", required=True)
    p.add_argument("--run-id", required=True, type=int)
    p.add_argument("--run-attempt", required=True, type=int)
    p.add_argument("--pr", required=True, type=int)
    p.add_argument("--sha", required=True)
    p.add_argument("--started", default="", help="epoch seconds the review started (the gate job)")
    p.add_argument("--usage-dir", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_metrics)
