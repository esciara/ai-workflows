"""WP11b acceptance test (notification events, ADR-0024), slice 2 part (plan row WP11b1). Done when: a new issue
triaged by B1 sends one "issue triaged" message with a working link to the issue, on both channels (Slack and
Telegram). Later slices add their events (B4 analysis, reporter silent, `fix: needs-maintainer`, verdict, `ai: error`)
to this file.

Runs against the playground (AIWF_E2E=1, AIWF_E2E_SLOT=1|2|3|any): the tester App (the outside reporter) opens a bug
report labelled with the held slot's `e2e-target-<n>` at creation, so the slot's caller runs triage.yml at the ref
under test (ADR-0043, ADR-0056). The slot caller already passes SLACK_WEBHOOK_URL, TELEGRAM_BOT_TOKEN and
TELEGRAM_CHAT_ID to triage; the build adds `notify: slack,telegram` to the playground's .github/ai-workflows-e2e.yml
(maintainer-merged playground PR). The notify step prints one `AIWF_NOTIFY_RESULT {json}` line per message sent (WP11a),
with the message `text` it sent added by this WP. The test reads those lines from every triage job of the run (so the
alert may live in its own job or a step), checks exactly one per channel, that the message names the issue and the
type B1 gave it, then GETs the link anonymously. The secrets never reach this machine; the test checks that the logs
hold neither a Slack webhook URL nor a Telegram bot API URL. The issue is closed as "not planned" at teardown.
"""

from __future__ import annotations

import json
import re
from typing import Iterator

import pytest

import playground as pg

TITLE_PREFIX = "[e2e] WP11b"
CHANNELS = {"slack", "telegram"}
TYPE_LABELS = {"type: bug", "type: feature", "type: question"}

BUG = (
    "Cart.remove() of an unknown item raises KeyError instead of ValueError",
    "Steps:\n\n```python\nfrom minicart.cart import Cart\ncart = Cart()\ncart.add('A', '10.00')\ncart.remove('B')\n```"
    "\n\nExpected: a ValueError saying item 'B' is not in the cart.\nActual: a bare `KeyError: 'B'` from the internal "
    "dict, with no message.\n\nminicart from main, Python 3.12.",
)


@pytest.fixture
def opened(testrun_uid: str) -> Iterator[list[int]]:
    """Issues this test opened, closed at teardown; also closes WP11b issues left by earlier crashed runs."""
    pg.close_left_over(TITLE_PREFIX, keep=testrun_uid[:8])
    numbers: list[int] = []
    yield numbers
    for n in numbers:
        pg.close_issue(n)


def triage_logs(run_id: int) -> str:
    """Logs of every triage job of the run that ran (skipped jobs have no log)."""
    data = pg.api(f"repos/{pg.REPO}/actions/runs/{run_id}/jobs?per_page=100")
    ran = [j for j in data["jobs"] if j["name"].startswith("triage / ") and j["conclusion"] not in (None, "skipped")]
    return "\n".join(pg.job_log(j["id"]) for j in ran)


def test_new_issue_triaged_sends_one_message_with_a_working_link_on_both_channels(e2e_target, testrun_uid, opened):
    title, body = BUG
    issue = pg.open_as_reporter(f"{TITLE_PREFIX} {testrun_uid[:8]}: {title}", body)
    opened.append(issue["number"])
    run = pg.issues_run(issue, pg.E2E_WORKFLOW)
    jobs = pg.jobs(run["id"])
    assert run["conclusion"] == "success", jobs

    labels = {lb["name"] for lb in pg.api(f"repos/{pg.REPO}/issues/{issue['number']}")["labels"]}
    print(f"#{issue['number']}: labels {sorted(labels)}")
    assert "ai: error" not in labels, labels
    types = labels & TYPE_LABELS
    assert len(types) == 1, f"#{issue['number']} was not triaged: labels {sorted(labels)}"
    kind = types.pop().split(": ")[1]

    log = triage_logs(run["id"])
    assert "hooks.slack.com" not in log and "api.telegram.org/bot" not in log, "a secret URL appears in a job log"
    got = pg.notify_results(log)
    for r in got:
        print(f"provider response: {json.dumps(r, sort_keys=True)}")

    # Ran the code under test, not main.
    assert {r["aiwf_sha"] for r in got} == {e2e_target}, got

    # One message per channel, on both channels, for this run.
    by_channel = {c: [r for r in got if r["channel"] == c] for c in CHANNELS}
    assert {c: len(v) for c, v in by_channel.items()} == {"slack": 1, "telegram": 1}, got
    assert not [r for r in got if r["channel"] not in CHANNELS], got

    # The providers accepted them.
    slack, telegram = by_channel["slack"][0], by_channel["telegram"][0]
    assert slack["status"] == 200 and slack["body"] == "ok", slack
    assert telegram["ok"] is True and isinstance(telegram["message_id"], int) and telegram["message_id"] > 0, telegram

    # The message names the issue and the type B1 gave it (spec: Chat notifications, "Issue triaged").
    for r in (slack, telegram):
        text = r["text"]
        assert re.search(rf"#{issue['number']}\b", text), f"{r['channel']} message does not name #{issue['number']}: {text}"
        assert re.search(rf"\b{kind}\b", text.lower()), f"{r['channel']} message does not state the type {kind!r}: {text}"

    # The link points to the issue and works. Telegram's links are the ones it parsed out of the stored message;
    # Slack's webhook echoes nothing, so its link is the one sent.
    expected = issue["html_url"]
    assert slack["links"] == [expected], slack
    assert telegram["links"] == [expected], telegram
    status = pg.http_status(expected)
    print(f"GET {expected} -> {status}")
    assert status == 200
