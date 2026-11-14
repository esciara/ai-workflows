"""WP7 acceptance test. Done when: with days shortened in config, ping, stale and close happen in order; a reply resets
them; `keep-open` exempts an issue (spec: Reporter silence).

Runs against the playground (AIWF_E2E=1) with an e2e slot (AIWF_E2E_SLOT=1|2|3|any, ADR-0056). Issues carry the held
slot's `e2e-target-<n>` at creation, so its caller-e2e-<n>.yml runs triage.yml at the commit under test, as in WP6. The
build adds, in a maintainer-merged playground PR:

- to the three slot callers, a `workflow_dispatch` with a `labels` input that runs the reporter-silence workflow at
  `e2e-target-<n>`, scoped to issues carrying `e2e-target-<n>` and the input's labels (caller job `silence`, with jobs
  `ping` then `stale`);
- to .github/ai-workflows-e2e.yml, `reporter_silence_days` in minutes, e.g. {ping: 0.007, stale: 0.0105,
  close: 0.011} (about 10, 15 and 16 minutes). The test reads the values from there, and fails if they are not shortened.
  `actions/stale` rounds `close - stale` down to whole days, so with under a day it closes the issue in the same run that
  labels it `stale` (spec: Reporter silence); the test expects that. The stale step handles only issues already pinged
  (`triage: no-response`), so a short `stale - ping` cannot stale an issue before its ping.

The daily schedule is stood in for by that dispatch (as the maintainer, through scripts/dev/as-maintainer): the test
waits until a step is due, dispatches once, and checks the result. Each test scopes its dispatches with its own label
(`e2e-wp7-cycle`, `e2e-wp7-reset`), so it never touches another test's issues, in this run or in another slot. Issues are
opened by the tester App (an outside reporter), so B2 needs the maintainer's `/reproduce` first (WP6); `keep-open` is
added by the agent App (the product reads only the label). Issues still open are closed as not planned at teardown.

1. Ping, stale, close, and `keep-open`: two vague bugs get `triage: needs-info`; one of them gets `keep-open`. A dispatch
   before `ping` is due changes nothing. Once due, the silent issue gets `triage: no-response` and one ping comment
   mentioning the maintainers, still open, not `stale`. `stale - ping` later one dispatch labels it `stale`, posts the
   "will close" comment, then closes it as not planned with the "reopen" comment. The `keep-open` issue stays open with
   none of these labels or comments.
2. A reply resets the clock: a vague bug is pinged; the reporter replies without the details. That reply reruns B2
   (WP6), which asks again (request 2 of 2, `limits.info_requests` default): still `triage: needs-info`, and
   `triage: no-response` is gone. A dispatch right after pings nobody (the clock restarted at the new ask); once `ping`
   has passed since the new ask, a dispatch pings again.

The ping's other selection rules (an author reply with no new ask yet, no marker comment, `ai: off`, `ai: error`) and the
`stale` removal on a reply are unit-tested or left to `actions/stale` (`remove-stale-when-updated`).
"""

from __future__ import annotations

import base64
import json
import time
from datetime import datetime
from typing import Any, Iterator

import pytest
import yaml

import playground as pg
from test_wp6 import NEEDS_INFO, NEEDS_INFO_MARKER, REPRODUCE_JOB, REPRODUCED, bot_comments, comment_run, item_run, \
    labels

E2E_CONFIG = ".github/ai-workflows-e2e.yml"  # the slot callers' config (ADR-0050)
NO_RESPONSE = "triage: no-response"
STALE = "stale"
KEEP_OPEN = "keep-open"
PING_MARKER = "<!-- ai-workflows:no-response -->"
SILENCE_JOBS = ("silence / ping", "silence / stale")
MAX_SHORT_DAYS = 0.05  # 72 minutes: anything longer is a production config, not a shortened one
MARGIN = 45  # seconds past a due time before dispatching (runner clock, API timestamps)

SILENT_BUG = (
    "The app stopped working after I updated",
    "I updated yesterday and now nothing happens when I use it. No message at all. It worked before. Please help.",
)
RESET_BUG = (
    "Error message when I start it",
    "When I start it I get an error message and then it stops. I don't remember the exact text. It's annoying.",
)
UNHELPFUL_REPLY = "Any news? It still happens to me, same as before."
KEPT_BUG = (
    "Weird behaviour since last week",
    "Since last week something feels off, results are not what I expect. I can't say more right now, sorry.",
)


@pytest.fixture
def tag(testrun_uid: str) -> str:
    return testrun_uid[:8]


@pytest.fixture
def opened() -> Iterator[list[int]]:
    """Issues this test opened; those still open are closed as not planned at teardown (never deleted)."""
    numbers: list[int] = []
    yield numbers
    for n in numbers:
        if pg.api(f"repos/{pg.REPO}/issues/{n}")["state"] == "open":
            pg.api(f"repos/{pg.REPO}/issues/{n}", "state=closed", "state_reason=not_planned", method="PATCH")


def e2e_config() -> dict[str, Any]:
    raw = pg.api(f"repos/{pg.REPO}/contents/{E2E_CONFIG}")
    return yaml.safe_load(base64.b64decode(raw["content"]))


def silence_seconds(cfg: dict[str, Any]) -> dict[str, float]:
    days = cfg.get("reporter_silence_days") or {}
    if set(days) != {"ping", "stale", "close"} or max(days.values()) > MAX_SHORT_DAYS:
        pytest.fail(f"{E2E_CONFIG} has no shortened reporter_silence_days ({days}); not a pass", pytrace=False)
    return {k: v * 86400 for k, v in days.items()}


def ts(stamp: str) -> float:
    return datetime.fromisoformat(stamp).timestamp()


def wait_until(due: float, what: str) -> None:
    pause = due + MARGIN - time.time()
    print(f"waiting {max(pause, 0):.0f}s for {what}")
    if pause > 0:
        time.sleep(pause)


def scope_label(kind: str) -> str:
    name = f"e2e-wp7-{kind}"
    pg.ensure_label(name, description="e2e: scopes WP7 reporter-silence dispatches")
    return name


def open_scoped(kind: str, report: tuple[str, str], tag: str, scope: str, opened: list[int]) -> dict[str, Any]:
    title, body = report
    issue = pg.open_issue(f"[e2e] WP7 {kind} {tag}: {title}", body, e2e=True, as_tester=True)
    opened.append(issue["number"])
    full = pg.api(f"repos/{pg.REPO}/issues/{issue['number']}")
    assert full["user"]["login"].endswith("[bot]") and full["user"]["login"] != pg.BOT, full["user"]["login"]
    pg.api(f"repos/{pg.REPO}/issues/{issue['number']}/labels", f"labels[]={scope}", method="POST")
    return {**issue, "created_at": full["created_at"]}


def ask_for_details(issues: list[dict[str, Any]]) -> dict[int, float]:
    """B1 ran; the maintainer's `/reproduce` gets each issue `triage: needs-info`. Returns the ask's time per issue."""
    for issue in issues:
        item_run("issues", issue["title"], issue["created_at"])
    posted = [(issue, pg.comment(issue["number"], "/reproduce")) for issue in issues]
    asked = {}
    for issue, c in posted:
        run = item_run("issue_comment", issue["title"], c["created_at"])
        assert run["jobs"].get(REPRODUCE_JOB) == "success", run["jobs"]
        got = labels(issue["number"])
        assert NEEDS_INFO in got and REPRODUCED not in got, f"#{issue['number']}: B2 did not ask for details: {sorted(got)}"
        asks = bot_comments(issue["number"], NEEDS_INFO_MARKER)
        assert len(asks) == 1, [a["html_url"] for a in asks]
        asked[issue["number"]] = ts(asks[0]["created_at"])
    return asked


def dispatch_silence(scope: str) -> dict[str, Any]:
    """Run the slot caller's reporter-silence jobs once, scoped to `scope`; returns the completed run."""
    wf = next(w for w in pg.api(f"repos/{pg.REPO}/actions/workflows?per_page=100")["workflows"]
              if w["name"] == pg.E2E_WORKFLOW)
    out = pg.gh(["api", "-X", "POST", f"repos/{pg.REPO}/actions/workflows/{wf['id']}/dispatches", "-f", "ref=main",
                 "-f", f"inputs[labels]={scope}", "-F", "return_run_details=true"], as_maintainer=True)
    run = pg.completed(int(json.loads(out)["workflow_run_id"]))
    run_jobs = pg.jobs(run["id"])
    print(f"silence run {run['id']} {run['html_url']} -> {run['conclusion']}, jobs {run_jobs}")
    assert run["conclusion"] == "success" and all(run_jobs.get(j) == "success" for j in SILENCE_JOBS), run_jobs
    return run


def issue_state(number: int) -> dict[str, Any]:
    return pg.api(f"repos/{pg.REPO}/issues/{number}")


def bot_texts(number: int, needle: str) -> list[str]:
    """Bodies of github-actions[bot] comments containing `needle` (the stale step's messages carry no marker)."""
    comments = pg.api(f"repos/{pg.REPO}/issues/{number}/comments?per_page=100")
    return [c["body"] for c in comments if c["user"]["login"] == pg.BOT and needle in (c["body"] or "")]


def assert_untouched(number: int) -> None:
    got = labels(number)
    assert not got & {NO_RESPONSE, STALE}, f"#{number}: {sorted(got)}"
    assert issue_state(number)["state"] == "open"
    assert not bot_comments(number, PING_MARKER) and not bot_texts(number, "will close"), f"#{number} was pinged or warned"


def test_silent_reporter_is_pinged_then_stale_then_closed_and_keep_open_is_exempt(e2e_target, tag, opened):
    cfg = e2e_config()
    secs = silence_seconds(cfg)
    scope = scope_label("cycle")
    silent = open_scoped("silent", SILENT_BUG, tag, scope, opened)
    kept = open_scoped("kept", KEPT_BUG, tag, scope, opened)
    asked = ask_for_details([silent, kept])
    pg.api(f"repos/{pg.REPO}/issues/{kept['number']}/labels", f"labels[]={KEEP_OPEN}", method="POST")

    early = dispatch_silence(scope)  # before the ping is due: nothing happens
    if ts(early["updated_at"]) >= asked[silent["number"]] + secs["ping"]:
        pytest.fail("the early dispatch ended after the ping was due, so 'too early' was not checked (not a pass); "
                    "lengthen `ping` in the e2e config", pytrace=False)
    assert_untouched(silent["number"])

    wait_until(max(asked.values()) + secs["ping"], "the ping")
    dispatch_silence(scope)
    got = labels(silent["number"])
    print(f"#{silent['number']} after the ping: {sorted(got)}")
    assert NO_RESPONSE in got and STALE not in got and NEEDS_INFO in got, sorted(got)
    pings = bot_comments(silent["number"], PING_MARKER)
    assert len(pings) == 1, pings
    print(pings[0]["body"])
    assert all(f"@{m}" in pings[0]["body"] for m in cfg["maintainers"]), "the ping does not mention the maintainers"
    assert issue_state(silent["number"])["state"] == "open"
    assert_untouched(kept["number"])

    wait_until(ts(issue_state(silent["number"])["updated_at"]) + secs["stale"] - secs["ping"], "the stale label")
    dispatch_silence(scope)  # close - stale is under a day: stale and close in one run
    closed = issue_state(silent["number"])
    print(f"#{silent['number']} after stale: {sorted(labels(silent['number']))}, {closed['state']}")
    assert STALE in labels(silent["number"])
    assert closed["state"] == "closed" and closed["state_reason"] == "not_planned", (closed["state"], closed["state_reason"])
    warned, reopen = bot_texts(silent["number"], "will close"), bot_texts(silent["number"], "reopen")
    assert len(warned) == 1 and len(reopen) == 1, (warned, reopen)
    order = [c["body"] for c in pg.api(f"repos/{pg.REPO}/issues/{silent['number']}/comments?per_page=100")]
    assert order.index(warned[0]) < order.index(reopen[0]), "the close comment came before the stale comment"
    assert len(bot_comments(silent["number"], PING_MARKER)) == 1, "pinged more than once"
    assert_untouched(kept["number"])
    assert KEEP_OPEN in labels(kept["number"])


def test_reporter_reply_restarts_the_clock(e2e_target, tag, opened):
    secs = silence_seconds(e2e_config())
    scope = scope_label("reset")
    issue = open_scoped("reset", RESET_BUG, tag, scope, opened)
    asked = ask_for_details([issue])

    wait_until(asked[issue["number"]] + secs["ping"], "the ping")
    dispatch_silence(scope)
    assert NO_RESPONSE in labels(issue["number"]) and len(bot_comments(issue["number"], PING_MARKER)) == 1

    rerun = comment_run(issue, UNHELPFUL_REPLY, as_tester=True)  # the reporter's reply reruns B2 (WP6)
    assert rerun["jobs"].get(REPRODUCE_JOB) == "success", rerun["jobs"]
    got = labels(issue["number"])
    print(f"#{issue['number']} after the reply: {sorted(got)}")
    assert NEEDS_INFO in got and not got & {NO_RESPONSE, STALE, REPRODUCED}, sorted(got)
    asks = bot_comments(issue["number"], NEEDS_INFO_MARKER)
    assert len(asks) == 2, [a["html_url"] for a in asks]
    new_ask = max(ts(a["created_at"]) for a in asks)

    right_after = dispatch_silence(scope)  # the clock restarted at the new ask: no ping yet
    assert ts(right_after["updated_at"]) < new_ask + secs["ping"], "dispatch too slow to check the restart (not a pass)"
    assert not labels(issue["number"]) & {NO_RESPONSE, STALE}
    assert len(bot_comments(issue["number"], PING_MARKER)) == 1, "pinged again before `ping` had passed since the new ask"

    wait_until(new_ask + secs["ping"], "the second ping")
    dispatch_silence(scope)
    assert NO_RESPONSE in labels(issue["number"]) and STALE not in labels(issue["number"])
    assert len(bot_comments(issue["number"], PING_MARKER)) == 2, "no ping after `ping` days since the new ask"
    assert issue_state(issue["number"])["state"] == "open"
