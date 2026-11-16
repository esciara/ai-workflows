"""The `verdict` required check of this repo's Workflow A caller (ADR-0053, states ADR-0055, reruns ADR-0059).

Ported from the job's bash with no change of behaviour. Green on `ai-review: merge` or on the repository owner's approval
of the head commit. Red (with an `::error` annotation and the step summary) while waiting for that approval, on
`changes-requested` and on a failed review. Also posts a `verdict` commit status for the merge box's text; that status
does not gate. Reads its inputs from the environment (event fields go through env, never into a command line) and calls
the GitHub API with `gh` and the job's read-only-plus-statuses GITHUB_TOKEN. Never approves anything.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

from aiwf import config
from aiwf.ghapi import GhRunner

LABEL_MERGE = "ai-review: merge"
LABEL_HUMAN = "ai-review: human-review"
LABEL_CHANGES = "ai-review: changes-requested"
BOT = "github-actions[bot]"
DEPENDABOT = "dependabot[bot]"
MAX_DESCRIPTION = 140  # the commit status description limit

THREADS_QUERY = ("query($o:String!,$n:String!,$p:Int!){repository(owner:$o,name:$n){pullRequest(number:$p)"
                 "{reviewThreads(first:100){pageInfo{hasNextPage} nodes{isResolved}}}}}")
THREADS_JQ = ('.data.repository.pullRequest.reviewThreads | "\\([.nodes[] | select(.isResolved | not)] | length)'
              '\\(if .pageInfo.hasNextPage then "+" else "" end)"')
PREV_JQ = ('[.[] | select(.context == "verdict" and .creator.login == "github-actions[bot]" '
           'and ((.description // "") | startswith("approved on ") | not))][0] '
           '| select(. != null) | "\\(.state)\\t\\(.description // "")"')
RERUN_JOBS_JQ = ('.jobs[] | select(.name == "verdict" and (.conclusion == "failure" or .conclusion == "cancelled" '
                 'or .conclusion == "timed_out")) | .id')

_THREAD_TAIL = re.compile(r"; .* unresolved thread.*", re.S)
_VERDICT_REASON = re.compile(r"\*\*Verdict:\*\* ([^\n]*)")


class Done(Exception):
    """End the run with this exit code (the bash step's `exit`)."""

    def __init__(self, code: int):
        self.code = code


def bare(text: str) -> str:
    """A restored text drops its old thread count (the shortest `; * unresolved thread*` suffix, as the shell did)."""
    for i in range(len(text) - 1, -1, -1):
        if _THREAD_TAIL.fullmatch(text, i):
            return text[:i]
    return text


def _cntrl_free(text: str) -> str:
    return "".join(ch for ch in text if not (ord(ch) < 32 or ord(ch) == 127))


def _json_stream(text: str) -> list[Any]:
    """The concatenated JSON values `gh api --paginate --jq '.[]'` prints, one object per element."""
    dec, out, i = json.JSONDecoder(), [], 0
    while True:
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            return out
        value, i = dec.raw_decode(text, i)
        out.append(value)


def owner_approvals(reviews: list[dict[str, Any]], head_sha: str) -> str:
    """Latest non-comment review per user, kept when APPROVED on the head commit by the repository owner."""
    latest: dict[str, dict[str, Any]] = {}
    for r in reviews:
        if r.get("state") in ("COMMENTED", "PENDING"):
            continue
        latest[(r.get("user") or {}).get("login") or ""] = r
    return ",".join(login for login, r in sorted(latest.items())
                    if r.get("state") == "APPROVED" and r.get("commit_id") == head_sha
                    and r.get("author_association") == "OWNER")


def review_reason(reviews: list[dict[str, Any]], head_sha: str) -> str:
    """The reasons of the AI review of the head commit (`**Verdict:** a; b.` in its body), control characters removed."""
    found = ""
    for r in reviews:
        if r.get("commit_id") != head_sha or (r.get("user") or {}).get("login") != BOT:
            continue
        m = _VERDICT_REASON.search(r.get("body") or "")
        if m:
            found = m.group(1).removesuffix(".")
    return _cntrl_free(found)


class Verdict:
    def __init__(self, env: dict[str, str], gh: GhRunner):
        self.env, self.gh = env, gh
        self.repo, self.pr, self.sha = env["REPO"], env["PR"], env["HEAD_SHA"]
        self.short = self.sha[:7]

    def summary(self, line: str) -> None:
        print(line)
        path = self.env.get("GITHUB_STEP_SUMMARY")
        if path:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def threads_info(self) -> str:
        """Information only: "N unresolved threads at <sha>" (A's and others'). The ruleset's resolution rule is the gate."""
        owner, _, name = self.repo.partition("/")
        try:
            n = self.gh(["api", "graphql", "-f", f"query={THREADS_QUERY}", "-f", f"o={owner}", "-f", f"n={name}",
                         "-F", f"p={self.pr}", "--jq", THREADS_JQ]).strip()
        except RuntimeError:
            return ""
        if re.fullmatch(r"[0-9]+\+?", n):
            return f"; {n} unresolved thread{'' if n == '1' else 's'} at {self.short}"
        return ""

    def status(self, state: str, text: str) -> None:
        """Post the `verdict` commit status, max 140 characters; the job result is the verdict."""
        text, info = bare(text), self.threads_info()
        desc = text[:max(0, MAX_DESCRIPTION - len(info))] + info
        try:  # not fatal: Dependabot runs get a read-only token whatever `permissions:` says
            self.gh(["api", "-X", "POST", f"repos/{self.repo}/statuses/{self.sha}", "-f", "context=verdict",
                     "-f", f"state={state}", "-f", f"description={desc}"])
        except RuntimeError:
            print("::warning title=verdict::could not post the verdict status (read-only token?)")
        self.summary(f"verdict: {state}, {desc}")

    def red(self, text: str) -> None:
        self.status("failure", text)
        print(f"::error title=verdict::{bare(text)}")
        raise Done(1)

    def hold(self, text: str) -> None:
        """Waiting keeps the job red (a pending status does not gate a required check pinned to the Actions integration)."""
        self.status("pending", text)
        print(f"::error title=waiting for maintainer approval::{bare(text)}")
        raise Done(1)

    def waiting(self, why: str) -> None:
        self.hold(f"waiting for maintainer approval of {self.short} ({why})")

    def _lines(self, args: list[str]) -> list[str]:
        """`gh` output lines; a failed call counts as no output (a shell `for x in $(...)` ignored its status)."""
        try:
            return self.gh(args).split()
        except RuntimeError:
            return []

    def rerun_stale(self) -> None:
        """After an owner approval, rerun the earlier failed `verdict` jobs on this head SHA (ADR-0059). Not fatal."""
        env, repo = self.env, self.repo
        if env["EVENT"] != "pull_request_review" or env.get("RUN_ATTEMPT") != "1":
            return
        if env.get("HEAD_REPO") != repo:
            print("fork PR: no rerun of earlier verdict runs (read-only token)")
            return
        try:
            head = self.gh(["api", f"repos/{repo}/pulls/{self.pr}", "--jq", ".head.sha"]).strip()
        except RuntimeError:
            head = ""
        if head != self.sha:
            print("head moved: no rerun")
            return
        try:
            wf = self.gh(["api", f"repos/{repo}/actions/runs/{env['RUN_ID']}", "--jq", ".workflow_id"]).strip()
        except RuntimeError:
            print("::warning title=verdict::could not list earlier verdict runs; rerun red ones by hand")
            return
        for run in self._lines(["api", "--paginate", f"repos/{repo}/actions/workflows/{wf}/runs?head_sha={self.sha}"
                                f"&status=completed&per_page=100", "--jq", ".workflow_runs[] | .id | tostring"]):
            if run == env["RUN_ID"]:
                continue
            for job in self._lines(["api", "--paginate", f"repos/{repo}/actions/runs/{run}/jobs?filter=latest&per_page=100",
                                    "--jq", RERUN_JOBS_JQ]):
                try:
                    self.gh(["api", "-X", "POST", f"repos/{repo}/actions/jobs/{job}/rerun"])
                    print(f"reran verdict job {job} of run {run}")
                except RuntimeError:
                    print(f"::warning title=verdict::could not rerun verdict job {job} of run {run}; rerun it by hand")

    def run(self) -> None:
        env, repo, pr, short = self.env, self.repo, self.pr, self.short
        event, review_state = env["EVENT"], env.get("REVIEW_STATE", "")
        if event == "pull_request_review" and review_state == "commented":
            # Green, no new status: the other runs on this head keep their answers, and a red one still blocks (ADR-0059).
            self.summary(f"review state {review_state} ignored; the other verdict runs of {short} keep their answers")
            raise Done(0)
        reviews = _json_stream(self.gh(["api", "--paginate", f"repos/{repo}/pulls/{pr}/reviews", "--jq", ".[]"]))
        approved = owner_approvals(reviews, self.sha)
        if approved:
            self.status("success", f"approved on {short} by {approved}")
            self.rerun_stale()
            raise Done(0)
        if event != "pull_request":
            # No owner approval: restore the AI verdict of the head SHA, the newest `verdict` status this workflow posted
            # that is not an approval (statuses are listed newest first). None yet: waiting.
            prev = self.gh(["api", f"repos/{repo}/commits/{self.sha}/statuses?per_page=100", "--jq", PREV_JQ]).strip("\n")
            prev_state, _, prev_text = prev.partition("\t")
            if prev_state == "failure":
                self.red(prev_text)
            if prev_state == "success":
                self.status("success", prev_text)
                raise Done(0)
            if prev_state == "pending":
                self.hold(prev_text)
            self.waiting("no owner approval")
        if env.get("AUTHOR") == DEPENDABOT:
            self.waiting("Dependabot PR, no AI review")
        result = env.get("REVIEW", "")
        if result == "skipped":
            self.waiting("AI review did not run")
        if result != "success":
            self.red(f"AI review {result} and no owner approval of {short}")
        labels = self.gh(["api", f"repos/{repo}/issues/{pr}/labels", "--jq", ".[].name"]).split("\n")
        why = review_reason(reviews, self.sha)
        if LABEL_MERGE in labels:
            self.status("success", f"{LABEL_MERGE} on {short}")
            raise Done(0)
        if LABEL_HUMAN in labels:
            self.waiting(why or "human-review")
        if LABEL_CHANGES in labels:
            self.red(f"changes requested on {short}: {why or 'see the AI review'}")
        self.waiting("no AI verdict label")


def cmd_verdict(args: argparse.Namespace, env: dict[str, str] | None = None, gh: GhRunner | None = None) -> int:
    try:
        Verdict(dict(os.environ if env is None else env), gh or config.run_gh).run()
    except Done as done:
        return done.code
    except (RuntimeError, ValueError, KeyError) as exc:  # a failed read: red, as the shell step's `set -e` was
        print(f"::error title=verdict::{exc}")
        return 1
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("verdict", help="the `verdict` required check (env REPO, PR, HEAD_SHA, HEAD_REPO, RUN_ID, "
                                       "RUN_ATTEMPT, AUTHOR, EVENT, REVIEW_STATE, REVIEW, GH_TOKEN)")
    p.set_defaults(func=cmd_verdict)


if __name__ == "__main__":
    sys.exit(cmd_verdict(argparse.Namespace()))
