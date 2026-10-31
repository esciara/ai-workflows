"""Workflow A gate (WP4, ADR-0044): whether this event starts a review, and of which PR head.

- `pull_request`: same-repo, non-draft PRs are reviewed; fork PRs never (`fork_prs: on-command`: only after `/review`).
- `issue_comment` on a PR: `/review` from a maintainer (ADR-0005) reviews the PR's current head, fork or not, unless
  `fork_prs: off` and the PR comes from a fork. Fork code is then read as text, never executed.
The event payload is untrusted data: it is read from $GITHUB_EVENT_PATH, never from the command line.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Any

from aiwf import commands, config

GhRunner = commands.GhRunner


@dataclass(frozen=True)
class Gate:
    run: bool
    reason: str
    pr: int = 0
    sha: str = ""
    fork: bool = False

    def outputs(self) -> dict[str, str]:
        return {"run": str(self.run).lower(), "pr": str(self.pr or ""), "sha": self.sha, "fork": str(self.fork).lower()}


def is_fork(pr: dict[str, Any], repo: str) -> bool:
    """A PR whose head repo is not this repo; a deleted head repo (null) counts as a fork."""
    head_repo = (pr.get("head") or {}).get("repo") or {}
    return (head_repo.get("full_name") or "").lower() != repo.lower()


def decide(event: str, payload: dict[str, Any], cfg: dict[str, Any], repo: str, gh: GhRunner) -> Gate:
    if event == "pull_request":
        pr = payload.get("pull_request") or {}
        if pr.get("draft"):
            return Gate(False, "draft PR")
        if is_fork(pr, repo):
            return Gate(False, "fork PR: reviewed only after a maintainer's /review", fork=True)
        return Gate(True, "PR event", pr["number"], pr["head"]["sha"])
    if event == "issue_comment":
        issue = payload.get("issue") or {}
        if not issue.get("pull_request"):
            return Gate(False, "comment on an issue, not a PR")
        comment = payload.get("comment") or {}
        cmd = commands.accept(comment.get("body"), (comment.get("user") or {}).get("login", ""),
                              cfg.get("maintainers", []), repo, gh)
        if cmd is None or cmd.name != "review":
            return Gate(False, "no /review from a maintainer")
        pr = json.loads(gh(["api", f"repos/{repo}/pulls/{issue['number']}"]))
        if pr.get("state") != "open":
            return Gate(False, "PR is not open")
        fork = is_fork(pr, repo)
        if fork and cfg.get("fork_prs", "on-command") == "off":
            return Gate(False, "fork PR and fork_prs: off", fork=True)
        return Gate(True, "/review", pr["number"], pr["head"]["sha"], fork)
    return Gate(False, f"event {event} does not start a review")


def cmd_review_gate(args: argparse.Namespace) -> int:
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as fh:
        payload = json.load(fh)
    cfg = json.loads(os.environ.get("AIWF_CONFIG") or "{}")
    gate = decide(os.environ.get("GITHUB_EVENT_NAME", ""), payload, cfg, args.repo, config.run_gh)
    print(f"review gate: {'run' if gate.run else 'skip'} ({gate.reason})"
          + (f" PR #{gate.pr} at {gate.sha[:7]}{' (fork)' if gate.fork else ''}" if gate.run else ""))
    out = args.github_output or os.environ.get("GITHUB_OUTPUT")
    if out:
        from aiwf.cli import write_outputs
        write_outputs(out, gate.outputs())
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("review-gate", help="Workflow A: does this event start a review (env GITHUB_EVENT_PATH, "
                                           "GITHUB_EVENT_NAME, AIWF_CONFIG)")
    p.add_argument("--repo", required=True)
    p.add_argument("--github-output", default=None)
    p.set_defaults(func=cmd_review_gate)
