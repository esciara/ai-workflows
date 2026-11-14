"""Publisher for Workflow B, B2 (reproduce), from the reproducer's checked JSON (spec B2, ADR-0037).

- Reproduced: label `triage: reproduced` and one sticky comment holding the failing test, its output and the commands
  run; that comment is the stored repro record. Job output `reproduced=true`: B3 runs next in this run.
- Either outcome removes `triage: awaiting-maintainer` and `fix: declined`; reproduced sets an earlier analysis
  comment to "re-analysing", not reproduced marks it superseded (spec B3). A failed run changes neither.
- Not reproduced: a new comment to the reporter (`@author`) with what was tried, the environment, what happened and two
  to four questions, label `triage: needs-info`; a reply from the reporter reruns B2. After `limits.info_requests` such
  requests since B2 last stopped, label `triage: needs-human` and stop instead (a maintainer's `/reproduce` restarts).

Agent text is untrusted: prose goes through `publish.clean`; code and output only inside fenced blocks, which GitHub
renders verbatim (no HTML, no mentions).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from aiwf import guard, publish, publish_analysis
from aiwf.ghapi import BOT, GhRunner, get_or_none, remove_label, upsert_marker_comment
from aiwf.publish_triage import NEEDS_HUMAN

MARKER = "<!-- ai-workflows:reproduce -->"
NEEDS_INFO_MARKER = "<!-- ai-workflows:needs-info -->"
STOP_MARKER = "<!-- ai-workflows:reproduce-stop -->"
REPRODUCED = "triage: reproduced"
NEEDS_INFO = "triage: needs-info"
SILENCE = ("triage: no-response", "stale")  # a reply restarts B2 (spec: Reporter silence)
DECISION = (publish_analysis.AWAITING, publish_analysis.DECLINED)  # any B2 outcome clears an earlier B4 decision (spec B3)
FALLBACK_QUESTIONS = (
    "What exact steps, code or commands make the bug happen, starting from a fresh checkout?",
    "Which version, operating system and language version do you use, and what is the full error message or output?",
)


def fence(text: str, lang: str = "") -> str:
    """A fenced block longer than any backtick run in `text`, so the text cannot close it."""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    ticks = "`" * max(3, longest + 1)
    return f"{ticks}{lang}\n{text.rstrip()}\n{ticks}"


def inline(text: str, limit: int = 200) -> str:
    """Inline code for a table cell: one line, no backticks, pipes escaped."""
    return "`" + " ".join(str(text).split())[:limit].replace("`", "'").replace("|", "\\|") + "`"


def commands_table(cmds: list[dict[str, Any]]) -> list[str]:
    if not cmds:
        return []
    rows = ["| Command | Exit code | Output (end) |", "|---|---|---|"]
    rows += [f"| {inline(c['command'])} | {c['exit_code']} | {publish.clean(c['output'][-300:], 300)} |" for c in cmds]
    return ["<details><summary>Commands run</summary>", "", *rows, "", "</details>"]


def tail(lines: list[str], data: dict[str, Any], run_url: str) -> list[str]:
    out = ["", *commands_table(data["commands"])]
    if data["environment"].strip():
        out += ["", f"Environment: {publish.clean(data['environment'], 500)}"]
    if data["suspicious_instructions"]:
        out += ["", publish.injection_line(data["suspicious_instructions"])]
    if run_url:
        out += ["", f"[Run]({run_url})"]
    return lines + out


def reproduced_body(data: dict[str, Any], run_url: str) -> str:
    t = data["test"]
    lines = [MARKER, f"**Reproduced.** {publish.clean(data['summary'], 400)}", "",
             f"**Test** {inline(t['path'])}, run with {inline(t['command'], 300)}:", "",
             fence(t["code"], "python" if t["path"].endswith(".py") else ""), "",
             "**Output**", "", fence(t["output"][-6000:])]
    return "\n".join(tail(lines, data, run_url))


def questions(data: dict[str, Any]) -> list[str]:
    qs = [publish.clean(q, 300) for q in data["questions"] if q.strip()][:4]
    for q in FALLBACK_QUESTIONS:
        if len(qs) >= 2:
            break
        qs.append(q)
    return qs


def needs_info_body(data: dict[str, Any], author: str, n: int, cap: int, run_url: str) -> str:
    lines = [NEEDS_INFO_MARKER, f"@{author} thanks for the report. The bug could not be reproduced yet "
             f"(request {n} of {cap}).", "",
             f"**Tried:** {publish.clean(data['tried'] or data['summary'], 1500)}", "",
             f"**What happened:** {publish.clean(data['happened'] or 'not stated', 1500)}", "",
             "Could you answer these?", ""]
    lines += [f"{i}. {q}" for i, q in enumerate(questions(data), 1)]
    lines += ["", "A reply here reruns the reproduction."]
    return "\n".join(tail(lines, data, run_url))


def stop_body(data: dict[str, Any], cap: int, run_url: str) -> str:
    lines = [STOP_MARKER, f"**Not reproduced after {cap} requests for details.** Labelled `{NEEDS_HUMAN}`; a person "
             "takes over. A maintainer can comment `/reproduce` to try again.", "",
             f"**Tried:** {publish.clean(data['tried'] or data['summary'], 1500)}", "",
             f"**What happened:** {publish.clean(data['happened'] or 'not stated', 1500)}"]
    return "\n".join(tail(lines, data, run_url))


def requests_since_stop(comments: list[dict[str, Any]]) -> int:
    """B2's needs-info comments since its last stop note (oldest first in `comments`)."""
    n = 0
    for c in comments:
        if c["user"]["login"] != BOT:
            continue
        body = c.get("body") or ""
        if body.startswith(STOP_MARKER):
            n = 0
        elif body.startswith(NEEDS_INFO_MARKER):
            n += 1
    return n


def all_comments(gh: GhRunner, repo: str, issue: int) -> list[dict[str, Any]]:
    out = gh(["api", "--paginate", f"repos/{repo}/issues/{issue}/comments?per_page=100", "--jq", ".[]"])
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def set_labels(gh: GhRunner, repo: str, issue: int, current: set[str], add: str, drop: tuple[str, ...]) -> None:
    for label in drop:
        if label in current:
            remove_label(gh, repo, issue, label)
    publish.add_labels(gh, repo, issue, add)


SANDBOX_START_ERROR = re.compile(r"^\s*(apply-seccomp|bwrap):", re.MULTILINE)


def sandbox_failed(cmds: list[dict[str, Any]]) -> bool:
    """Every command failed with the sandbox's own start-up error (bubblewrap/seccomp), so nothing ran at all."""
    return bool(cmds) and all(c["exit_code"] != 0 and SANDBOX_START_ERROR.search(c["output"]) for c in cmds)


def publish_reproducer(data: dict[str, Any], repo: str, issue: int, run_url: str, gh: GhRunner) -> None:
    publish_result(data, repo, issue, run_url, gh)
    guard.clear_error(gh, repo, issue, run_url)  # published: an earlier run's sticky error comment no longer applies


def publish_result(data: dict[str, Any], repo: str, issue: int, run_url: str, gh: GhRunner) -> None:
    item = get_or_none(gh, f"repos/{repo}/issues/{issue}") or {}
    current = {lb["name"] for lb in item.get("labels", [])}
    stale = (publish.ERROR_LABEL, *SILENCE, *DECISION)
    t = data["test"]
    if data["reproduced"]:
        if not t["code"].strip() or not t["output"].strip():
            raise RuntimeError("reproducer says reproduced but returned no test code or output")  # job fails: ai: error
        set_labels(gh, repo, issue, current, REPRODUCED, (*stale, NEEDS_INFO, NEEDS_HUMAN))
        upsert_marker_comment(gh, repo, issue, MARKER, reproduced_body(data, run_url))
        publish_analysis.reanalyse(gh, repo, issue, run_url)  # an earlier decision stops being current
        out = os.environ.get("GITHUB_OUTPUT")
        if out:  # B3 runs next in this run and updates the analysis comment
            with open(out, "a", encoding="utf-8") as fh:
                fh.write("reproduced=true\n")
        print(f"reproduced {repo}#{issue}")
        return
    if sandbox_failed(data["commands"]):  # a runner problem, not the reporter's: ask them nothing
        raise RuntimeError("the sandbox could not start: every command failed before running")  # job fails: ai: error
    publish_analysis.supersede(gh, repo, issue, run_url)  # the analysis no longer stands (spec B3)
    cap = int(json.loads(os.environ.get("AIWF_CONFIG") or "{}").get("limits", {}).get("info_requests", 2))
    asked = requests_since_stop(all_comments(gh, repo, issue))
    if asked >= cap:
        set_labels(gh, repo, issue, current, NEEDS_HUMAN, (*stale, NEEDS_INFO, REPRODUCED))
        publish.comment(gh, repo, issue, stop_body(data, cap, run_url))
        print(f"not reproduced {repo}#{issue}: {asked} requests made, {NEEDS_HUMAN}")
        return
    set_labels(gh, repo, issue, current, NEEDS_INFO, (*stale, NEEDS_HUMAN, REPRODUCED))
    publish.comment(gh, repo, issue, needs_info_body(data, item["user"]["login"], asked + 1, cap, run_url))
    print(f"not reproduced {repo}#{issue}: request {asked + 1} of {cap}")


PUBLISHERS = {"reproducer": publish_reproducer}
