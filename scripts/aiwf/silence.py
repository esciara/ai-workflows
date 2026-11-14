"""Workflow B, B2: reporter silence, the ping step (spec: Reporter silence). No agent, no model token.

Runs in silence.yml's `ping` job, on the caller's daily schedule or a manual run. For each open issue with
`triage: needs-info` (and the caller's extra scope labels) and none of `triage: no-response`, `keep-open`, `ai: off`,
`ai: error`: it takes the bot's latest needs-info comment (by its hidden marker); when the issue's author has not
commented since and `ping` days have passed, it posts one comment starting with PING_MARKER that mentions each of
`maintainers`, then labels `triage: no-response`. It reads only labels, comment authors, dates and markers, never
issue text. It also writes the `actions/stale` inputs of the `stale` job, computed from `reporter_silence_days`.

After actions/stale, `silence-closed` takes `triage: no-response` and `stale` off the issues it just closed, so a
maintainer's reopen is final (aiwf-9ni): the reopened issue is out of the stale step's scope, and the ping step has
already pinged for that request. A reply from the reporter still reruns B2 (`triage: needs-info` stays).
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from aiwf import config, guard, publish
from aiwf.ghapi import BOT, GhRunner, remove_label
from aiwf.publish_reproduce import NEEDS_INFO, NEEDS_INFO_MARKER, all_comments

PING_MARKER = "<!-- ai-workflows:no-response -->"
NO_RESPONSE = "triage: no-response"
KEEP_OPEN = "keep-open"
STALE = "stale"
EXEMPT = frozenset({NO_RESPONSE, KEEP_OPEN, guard.OFF_LABEL, guard.ERROR_LABEL})
DAY = 86400.0


def parse_time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def fmt_days(days: float) -> str:
    """Plain decimal, never exponent notation (actions/stale's parseInt reads '5e-05' as 5)."""
    return f"{days:.6f}".rstrip("0").rstrip(".") or "0"


def scope_labels(extra: str) -> list[str]:
    """`triage: needs-info` plus the caller's extra labels (comma-separated; blanks dropped)."""
    if "\n" in extra or "\r" in extra:  # would forge GITHUB_OUTPUT keys
        raise SystemExit("--labels must not contain a line break")
    out = [NEEDS_INFO]
    for name in (s.strip() for s in extra.split(",")):
        if name and name not in out:
            out.append(name)
    return out


def stale_inputs(days: dict[str, float], labels: list[str]) -> dict[str, str]:
    """The `stale` job's inputs. Its clock starts at the ping (an update), hence `stale - ping`; actions/stale reads
    the close days as a whole number, rounded down."""
    return {
        "only_labels": ",".join([labels[0], NO_RESPONSE, *labels[1:]]),
        "stale_after": fmt_days(days["stale"] - days["ping"]),
        "close_after": str(int(round(days["close"] - days["stale"], 6))),  # 2.3 - 0.3 is 1.999...
        "stale_days": fmt_days(days["stale"]),
    }


def exempt(issue: dict[str, Any]) -> set[str]:
    return {lb["name"] for lb in issue.get("labels", [])} & EXEMPT


def decide(issue: dict[str, Any], comments: list[dict[str, Any]], ping_days: float, now: datetime) -> str:
    """'ping', or why not. `comments`: the issue's comments, any order."""
    if exempt(issue):
        return f"skip: {', '.join(sorted(exempt(issue)))}"
    ordered = sorted(comments, key=lambda c: parse_time(c["created_at"]))
    ours = [c for c in ordered if c["user"]["login"] == BOT]
    asks = [c for c in ours if (c.get("body") or "").startswith(NEEDS_INFO_MARKER)]
    if not asks:
        return "skip: no request for details from the bot"
    asked = parse_time(asks[-1]["created_at"])
    later = [c for c in ordered if parse_time(c["created_at"]) > asked]
    author = issue["user"]["login"]
    if any(c["user"]["login"] == author for c in later):
        return "skip: the reporter replied"
    if any(c["user"]["login"] == BOT and (c.get("body") or "").startswith(PING_MARKER) for c in later):
        return "skip: already pinged since the request"
    if (now - asked).total_seconds() < ping_days * DAY:
        return "skip: ping not due"
    return "ping"


def ping_body(maintainers: list[str], days: dict[str, float]) -> str:
    who = " ".join(f"@{m}" for m in maintainers)
    return (f"{PING_MARKER}\n{who} no reply from the reporter for {fmt_days(days['ping'])} days after the request "
            f"for details. Decide whether this bug is worth pursuing without them. Unless the reporter replies or "
            f"the issue gets `{KEEP_OPEN}`, it is labelled `stale` at day {fmt_days(days['stale'])} and closed at "
            f"day {fmt_days(days['close'])}.")


def open_issues(gh: GhRunner, repo: str, labels: list[str]) -> list[dict[str, Any]]:
    """Open issues (not PRs) carrying every label in `labels`."""
    wanted = quote(",".join(labels), safe=",")
    out = gh(["api", "--paginate", "--jq", ".[]", f"repos/{repo}/issues?state=open&labels={wanted}&per_page=100"])
    items = [json.loads(line) for line in out.splitlines() if line.strip()]
    return [i for i in items if "pull_request" not in i]


def run(gh: GhRunner, repo: str, cfg: dict[str, Any], labels: list[str], now: datetime) -> list[int]:
    """Ping every due issue; returns the issues pinged."""
    days = cfg["reporter_silence_days"]
    pinged = []
    for issue in open_issues(gh, repo, labels):
        n = issue["number"]
        verdict = decide(issue, [] if exempt(issue) else all_comments(gh, repo, n), days["ping"], now)
        print(f"#{n}: {verdict}")
        if verdict == "ping":
            publish.comment(gh, repo, n, ping_body(cfg["maintainers"], days))
            publish.add_labels(gh, repo, n, NO_RESPONSE)
            pinged.append(n)
    return pinged


def closed_numbers(raw: str) -> list[int]:
    """Issue numbers from actions/stale's `closed-issues-prs` output (a JSON list of issues); anything else is refused.
    Only the numbers are read, never titles or other text."""
    items = json.loads(raw or "[]")
    if not isinstance(items, list):
        raise SystemExit("closed-issues-prs is not a JSON list")
    out = []
    for item in items:
        n = item.get("number") if isinstance(item, dict) else None
        if type(n) is not int or n < 1:
            raise SystemExit("closed-issues-prs holds an item without a valid number")
        if not item.get("isPullRequest") and n not in out:
            out.append(n)
    return out


def unlabel_closed(gh: GhRunner, repo: str, numbers: list[int]) -> None:
    """Take the silence labels off issues the stale step closed; `triage: needs-info` stays (a reply reruns B2)."""
    for n in numbers:
        for label in (NO_RESPONSE, STALE):
            remove_label(gh, repo, n, label)


def cmd_closed(args: argparse.Namespace) -> int:
    numbers = closed_numbers(os.environ.get("AIWF_CLOSED") or "[]")
    unlabel_closed(config.run_gh, args.repo, numbers)
    print(f"reporter silence: took {NO_RESPONSE!r} and {STALE!r} off closed issue(s) {numbers} in {args.repo}")
    return 0


def cmd_ping(args: argparse.Namespace) -> int:
    cfg = json.loads(os.environ.get("AIWF_CONFIG") or "{}")
    labels = scope_labels(args.labels)
    out = args.github_output or os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.writelines(f"{k}={v}\n" for k, v in stale_inputs(cfg["reporter_silence_days"], labels).items())
    pinged = run(config.run_gh, args.repo, cfg, labels, datetime.now(timezone.utc))
    print(f"reporter silence: pinged {len(pinged)} issue(s) {pinged} in {args.repo} (scope {labels})")
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("silence-ping", help="B2 reporter silence: ping maintainers on silent needs-info issues "
                                            "(env AIWF_CONFIG); writes the stale step's inputs")
    p.add_argument("--repo", required=True)
    p.add_argument("--labels", default="", help="extra scope labels, comma-separated")
    p.add_argument("--github-output", default=None)
    p.set_defaults(func=cmd_ping)
    p = sub.add_parser("silence-closed", help="B2 reporter silence: after actions/stale, take the silence labels off "
                                              "the issues it closed (env AIWF_CLOSED), so a reopen is final")
    p.add_argument("--repo", required=True)
    p.set_defaults(func=cmd_closed)
