"""WP11a acceptance test. Done when: a `workflow_dispatch` test event sends one message with a working link, on both
channels (Slack and Telegram).

Runs against the playground (AIWF_E2E=1, AIWF_E2E_SLOT=1): the maintainer dispatches the playground's caller-e2e.yml,
whose `notify-test` job calls notify.yml at the ref under test (`e2e-target`, ADR-0028) with both channels. The notify
step prints one `AIWF_NOTIFY_RESULT {json}` line per message sent, holding what the provider answered (Slack: HTTP
status and body; Telegram: `ok` and `message_id`, plus the links Telegram parsed out of the message it stored). The
test reads those lines from the job log, checks there is exactly one per channel, then GETs each link anonymously.
The secrets (SLACK_WEBHOOK_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID) never reach this machine; the test also checks
that the log holds neither a Slack webhook URL nor a Telegram bot API URL.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import pytest

import playground as pg

E2E_WORKFLOW = "AI workflows (e2e)"  # name of the playground's caller-e2e.yml
NOTIFY_JOB = "notify-test / send"
RESULT_PREFIX = "AIWF_NOTIFY_RESULT "
CHANNELS = {"slack", "telegram"}


def dispatch_e2e() -> int:
    """Dispatch caller-e2e.yml on the playground's default branch as the maintainer; returns the run ID."""
    wf = next(w for w in pg.api(f"repos/{pg.REPO}/actions/workflows")["workflows"] if w["name"] == E2E_WORKFLOW)
    out = pg.gh(["api", "-X", "POST", f"repos/{pg.REPO}/actions/workflows/{wf['id']}/dispatches",
                 "-f", "ref=main", "-F", "return_run_details=true"], as_maintainer=True)  # the App has no actions write
    return json.loads(out)["workflow_run_id"]


def job_log(run_id: int, name: str) -> str:
    job = next((j for j in pg.api(f"repos/{pg.REPO}/actions/runs/{run_id}/jobs?per_page=100")["jobs"]
                if j["name"] == name), None)
    if job is None:
        pytest.fail(f"run {run_id} has no job {name!r} (not a pass)", pytrace=False)
    return pg.gh(["api", f"repos/{pg.REPO}/actions/jobs/{job['id']}/logs"])


def results(log: str) -> list[dict[str, Any]]:
    out = []
    for line in log.splitlines():
        at = line.find(RESULT_PREFIX)
        if at >= 0:
            out.append(json.loads(line[at + len(RESULT_PREFIX):]))
    return out


def http_status(url: str) -> int:
    """Anonymous GET, as someone clicking the link in the chat would do (public playground)."""
    req = urllib.request.Request(url, headers={"User-Agent": "ai-workflows-e2e"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_dispatch_test_event_sends_one_message_with_a_working_link_on_both_channels(e2e_target):
    run_id = dispatch_e2e()
    run = pg.completed(run_id)
    jobs = pg.jobs(run_id)
    print(f"notify test dispatch: run {run_id} {run['html_url']} -> {run['conclusion']}; jobs {jobs}")
    assert jobs.get(NOTIFY_JOB) == "success", jobs
    assert run["conclusion"] == "success", jobs

    log = job_log(run_id, NOTIFY_JOB)
    assert "hooks.slack.com" not in log and "api.telegram.org/bot" not in log, "a secret URL appears in the job log"
    got = results(log)
    for r in got:
        print(f"provider response: {json.dumps(r, sort_keys=True)}")

    # Ran the code under test, not main.
    assert {r["aiwf_sha"] for r in got} == {e2e_target}, got

    # One message per channel, on both channels.
    by_channel = {c: [r for r in got if r["channel"] == c] for c in CHANNELS}
    assert {c: len(v) for c, v in by_channel.items()} == {"slack": 1, "telegram": 1}, got
    assert not [r for r in got if r["channel"] not in CHANNELS], got

    # The providers accepted them.
    slack, telegram = by_channel["slack"][0], by_channel["telegram"][0]
    assert slack["status"] == 200 and slack["body"] == "ok", slack
    assert telegram["ok"] is True and isinstance(telegram["message_id"], int) and telegram["message_id"] > 0, telegram

    # The link points back to this run on GitHub and works. Telegram's links are the ones it parsed out of the stored
    # message (so the message really holds the link); Slack's webhook echoes nothing, so its link is the one sent.
    expected = run["html_url"]
    assert slack["links"] == [expected], slack
    assert telegram["links"] == [expected], telegram
    status = http_status(expected)
    print(f"GET {expected} -> {status}")
    assert status == 200
