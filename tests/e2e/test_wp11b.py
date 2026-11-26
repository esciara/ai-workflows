"""WP11b acceptance test (notification events, ADR-0024), slice 2 part (plan row WP11b1). Done when: a new issue
triaged by B1 sends one "issue triaged" message with a working link to the issue, on both channels (Slack and
Telegram). WP11b2 adds the B4 analysis and `fix: needs-maintainer` alerts (one issue: `/reproduce` gives the analysis
and its alert, a forced-failure `/fix` gives the escalation and its alert; the playground's fix-fail config also sets
`notify: slack,telegram`). Later slices add reporter silent, the verdict and `ai: error` to this file.

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
from triage_core import labels
from triage_fix import (ESCALATE_JOB, FAIL_LABEL, NEEDS_MAINTAINER, TAX_BUG, TAX_FILES, fail_config, fix,
                        open_as_reporter, reproduce_and_analyse)
from triage_fix import opened as fix_opened, tag  # noqa: F401 (fixtures)

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


def alert_messages(run_id: int, job_prefix: str, number: int, e2e_target: str) -> dict[str, dict]:
    """The one message per channel the run's `job_prefix` jobs sent, checked as accepted by the providers, sent by the
    code under test and holding no secret URL; returns them by channel."""
    data = pg.api(f"repos/{pg.REPO}/actions/runs/{run_id}/jobs?per_page=100")
    ran = [j for j in data["jobs"] if j["name"].startswith(job_prefix) and j["conclusion"] not in (None, "skipped")]
    log = "\n".join(pg.job_log(j["id"]) for j in ran)
    assert "hooks.slack.com" not in log and "api.telegram.org/bot" not in log, "a secret URL appears in a job log"
    got = pg.notify_results(log)
    assert {r["aiwf_sha"] for r in got} == {e2e_target}, got
    by_channel = {c: [r for r in got if r["channel"] == c] for c in CHANNELS}
    assert {c: len(v) for c, v in by_channel.items()} == {"slack": 1, "telegram": 1}, got
    slack, telegram = by_channel["slack"][0], by_channel["telegram"][0]
    assert slack["status"] == 200 and slack["body"] == "ok", slack
    assert telegram["ok"] is True and isinstance(telegram["message_id"], int) and telegram["message_id"] > 0, telegram
    url = f"https://github.com/{pg.REPO}/issues/{number}"
    for r in (slack, telegram):
        print(f"{r['channel']}: {r['text']}")
        assert re.search(rf"#{number}\b", r["text"]), r
    assert slack["links"] == [url] and telegram["links"] == [url], (slack, telegram)
    assert pg.http_status(url) == 200
    return {"slack": slack, "telegram": telegram}


def test_analysis_and_needs_maintainer_alerts_name_the_issue_and_link_it_on_both_channels(e2e_target, tag, fix_opened):
    cap = fail_config()["limits"]["fix_rounds"]
    issue = open_as_reporter("notify-fix", TAX_BUG, tag, fix_opened)
    reproduce_and_analyse(issue, TAX_FILES)
    runs: list[dict] = []
    reproduce_and_analyse(issue, TAX_FILES, runs)
    n = issue["number"]

    # The /reproduce run that posted the analysis sent the analysis alert: bug, issue number, reply to give.
    assert runs[0]["jobs"].get("triage / notify-analysis / send") == "success", runs[0]["jobs"]
    for r in alert_messages(runs[0]["id"], "triage / notify-analysis", n, e2e_target).values():
        assert re.search(r"\bBug #%d analysed: \S" % n, r["text"]), r
        assert "/fix" in r["text"] and "/no-fix" in r["text"], r
        assert "https://" not in r["text"], r

    # A forced-failure `/fix` escalates; that run sent the needs-maintainer alert.
    pg.ensure_label(FAIL_LABEL, "d93f0b", "e2e only: the e2e caller loads a config whose test command always fails")
    pg.api(f"repos/{pg.REPO}/issues/{n}/labels", f"labels[]={FAIL_LABEL}", method="POST")
    _, run = fix(issue, "/fix")
    assert run["jobs"].get(ESCALATE_JOB) == "success" and NEEDS_MAINTAINER in labels(n), run["jobs"]
    assert run["jobs"].get("triage / notify-fix / send") == "success", run["jobs"]
    for r in alert_messages(run["id"], "triage / notify-fix", n, e2e_target).values():
        assert re.search(rf"#{n}: fix failed after {cap} round\(s\), needs a maintainer", r["text"]), r
