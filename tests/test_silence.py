"""WP7: reporter silence (spec: Reporter silence). Ping selection, the stale step's inputs, silence.yml's shape, and the
caller template's job (no network)."""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from aiwf import cli, config, silence as s
from aiwf.ghapi import BOT
from aiwf.publish_reproduce import NEEDS_INFO, NEEDS_INFO_MARKER
from ghfake import RecordingGh

ROOT = Path(__file__).resolve().parents[1]
REPO = "o/r"
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
DAYS = {"ping": 4, "stale": 14, "close": 21}
CFG = {"maintainers": ["Boss", "Ann"], "reporter_silence_days": DAYS}


def at(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def issue(number=1, author="rep", labels=(NEEDS_INFO,)):
    return {"number": number, "user": {"login": author}, "labels": [{"name": n} for n in labels]}


def c(login, body, days_ago):
    return {"user": {"login": login}, "body": body, "created_at": at(days_ago)}


def ask(days_ago):
    return c(BOT, f"{NEEDS_INFO_MARKER}\n@rep thanks, could you say more?", days_ago)


# --- which issues get pinged -----------------------------------------------------------------------------------------

def test_due_silent_issue_is_pinged():
    assert s.decide(issue(), [ask(5)], 4, NOW) == "ping"


def test_ping_exactly_at_the_due_time_and_not_before():
    assert s.decide(issue(), [ask(4)], 4, NOW) == "ping"
    assert s.decide(issue(), [ask(3.99)], 4, NOW) == "skip: ping not due"


def test_decimal_days_count_in_seconds():
    assert s.decide(issue(), [ask(0.008)], 0.007, NOW) == "ping"
    assert s.decide(issue(), [ask(0.006)], 0.007, NOW) == "skip: ping not due"


@pytest.mark.parametrize("label", ["triage: no-response", "keep-open", "ai: off", "ai: error"])
def test_exempt_labels_skip(label):
    assert s.decide(issue(labels=(NEEDS_INFO, label)), [ask(30)], 4, NOW).startswith("skip: ")


def test_no_marker_comment_skips():
    """A needs-info label set by hand: no ask to count from."""
    assert s.decide(issue(), [c(BOT, "something else", 30), c("boss", "please add logs", 30)], 4, NOW) \
        == "skip: no request for details from the bot"


def test_forged_marker_from_someone_else_is_ignored():
    assert s.decide(issue(), [c("rep", f"{NEEDS_INFO_MARKER} fake", 30)], 4, NOW).startswith("skip: no request")


def test_reporter_reply_since_the_ask_skips():
    """The reply reruns B2, which asks again; until then the reporter is not silent."""
    assert s.decide(issue(), [ask(10), c("rep", "here are details", 9)], 4, NOW) == "skip: the reporter replied"


def test_clock_counts_from_the_latest_ask():
    comments = [ask(20), c("rep", "same", 6), ask(3)]
    assert s.decide(issue(), comments, 4, NOW) == "skip: ping not due"
    assert s.decide(issue(), [ask(20), c("rep", "same", 6), ask(5)], 4, NOW) == "ping"


def test_reply_before_the_ask_and_others_comments_do_not_count():
    comments = [c("rep", "report details", 10), ask(9), c("boss", "hmm", 2), c("someone", "+1", 1)]
    assert s.decide(issue(), comments, 4, NOW) == "ping"


def test_no_second_ping_for_the_same_ask():
    """A ping already posted since the ask (label removed by hand, or the label call failed): never ping twice."""
    comments = [ask(10), c(BOT, f"{s.PING_MARKER}\n@Boss ...", 5)]
    assert s.decide(issue(), comments, 4, NOW) == "skip: already pinged since the request"


def test_comment_order_does_not_matter():
    assert s.decide(issue(), [c("rep", "x", 9), ask(10)], 4, NOW) == "skip: the reporter replied"


def test_ping_body_starts_with_marker_and_mentions_every_maintainer():
    body = s.ping_body(["Boss", "Ann"], DAYS)
    assert body.startswith(s.PING_MARKER + "\n")
    assert "@Boss" in body and "@Ann" in body and "day 14" in body and "day 21" in body


# --- the run: one comment then one label per due issue ---------------------------------------------------------------

class Gh(RecordingGh):
    def __init__(self, issues, comments):
        super().__init__()
        self.issues, self.comments = issues, comments

    def respond(self, args):
        url = self.url(args)
        if self.method(args) != "GET":
            return "{}"
        if "/comments" in url:
            n = int(url.split("/issues/")[1].split("/")[0])
            return "\n".join(json.dumps(x) for x in self.comments.get(n, []))
        return "\n".join(json.dumps(x) for x in self.issues)


def test_run_pings_due_issues_only_and_labels_after_commenting():
    issues = [issue(1), issue(2), issue(3, labels=(NEEDS_INFO, "keep-open")), {**issue(4), "pull_request": {}}]
    gh = Gh(issues, {1: [ask(5)], 2: [ask(1)], 3: [ask(30)]})
    assert s.run(gh, REPO, CFG, [NEEDS_INFO, "e2e-target-1"], NOW) == [1]
    writes = gh.writes()
    assert [gh.url(w) for w in writes] == [f"repos/{REPO}/issues/1/comments", f"repos/{REPO}/issues/1/labels"]
    assert "labels[]=triage: no-response" in writes[1]
    assert not any("/issues/3/comments" in gh.url(x) for x in gh.calls), "exempt issue: comments not even read"
    listing = gh.url(gh.calls[0])
    assert "state=open" in listing and "labels=triage%3A%20needs-info,e2e-target-1" in listing


def test_cli_writes_the_stale_inputs_before_pinging(tmp_path, monkeypatch):
    out = tmp_path / "out"
    monkeypatch.setenv("AIWF_CONFIG", json.dumps(CFG))
    monkeypatch.setattr(config, "run_gh", Gh([], {}))
    assert cli.main(["silence-ping", "--repo", REPO, "--labels", " e2e-target-1, ,e2e-wp7-cycle,",
                     "--github-output", str(out)]) == 0
    got = dict(line.split("=", 1) for line in out.read_text().splitlines())
    assert got == {"only_labels": "triage: needs-info,triage: no-response,e2e-target-1,e2e-wp7-cycle",
                   "stale_after": "10", "close_after": "7", "stale_days": "14"}


# --- after the stale step: a maintainer's reopen is final (aiwf-9ni) ---------------------------------------------------

def test_closed_numbers_reads_numbers_only_and_skips_prs():
    raw = json.dumps([{"number": 7, "title": "x\nstale_after=0"}, {"number": 9, "isPullRequest": True},
                      {"number": 7, "title": "dup"}])
    assert s.closed_numbers(raw) == [7]
    assert s.closed_numbers("") == [] and s.closed_numbers("[]") == []


@pytest.mark.parametrize("raw", ['{"number": 1}', '[{"number": "1"}]', '[{"number": 0}]', '[{"title": "t"}]',
                                 '[{"number": true}]', '[3]'])
def test_closed_numbers_refuses_anything_else(raw):
    with pytest.raises(SystemExit):
        s.closed_numbers(raw)


def test_closed_issues_lose_no_response_and_stale_but_keep_needs_info():
    gh = Gh([], {})
    s.unlabel_closed(gh, REPO, [7, 8])
    assert [gh.url(w) for w in gh.writes("DELETE")] == [
        f"repos/{REPO}/issues/7/labels/triage%3A%20no-response", f"repos/{REPO}/issues/7/labels/stale",
        f"repos/{REPO}/issues/8/labels/triage%3A%20no-response", f"repos/{REPO}/issues/8/labels/stale"]
    assert len(gh.writes()) == 4


def test_reopened_issue_is_not_pinged_again():
    """After silence-closed, a reopened issue keeps only `triage: needs-info`: out of the stale scope, and the ping
    step already pinged for that request, so nothing closes it again until a new request for details."""
    comments = [ask(25), c(BOT, f"{s.PING_MARKER}\n@Boss ...", 21), c("Boss", "reopening", 1)]
    assert s.decide(issue(), comments, 4, NOW) == "skip: already pinged since the request"
    assert s.NO_RESPONSE in s.stale_inputs(DAYS, [NEEDS_INFO])["only_labels"].split(",")


def test_cli_closed_reads_the_env(monkeypatch):
    gh = Gh([], {})
    monkeypatch.setattr(config, "run_gh", gh)
    monkeypatch.setenv("AIWF_CLOSED", json.dumps([{"number": 5, "title": "t"}]))
    assert cli.main(["silence-closed", "--repo", REPO]) == 0
    assert len(gh.writes("DELETE")) == 2


# --- the stale step's inputs -----------------------------------------------------------------------------------------

def test_scope_labels_always_start_with_needs_info():
    assert s.scope_labels("") == [NEEDS_INFO]
    assert s.scope_labels("a, b ,,a") == [NEEDS_INFO, "a", "b"]


def test_stale_inputs_with_test_minutes():
    """{ping: 0.007, stale: 0.0105, close: 0.011}: stale 5 minutes after the ping, close in the same run (0 days)."""
    got = s.stale_inputs({"ping": 0.007, "stale": 0.0105, "close": 0.011}, [NEEDS_INFO])
    assert got["stale_after"] == "0.0035" and got["close_after"] == "0" and got["stale_days"] == "0.0105"
    assert got["only_labels"] == "triage: needs-info,triage: no-response"


@pytest.mark.parametrize("days,text", [(0.00005, "0.00005"), (10.0, "10"), (2.5, "2.5"), (1e-9, "0")])
def test_days_never_use_exponent_notation(days, text):
    assert s.fmt_days(days) == text


def test_close_days_round_down():
    assert s.stale_inputs({"ping": 1, "stale": 2, "close": 9.9}, [NEEDS_INFO])["close_after"] == "7"
    assert s.stale_inputs({"ping": 0.1, "stale": 0.3, "close": 2.3}, [NEEDS_INFO])["close_after"] == "2"


def test_labels_with_a_line_break_are_refused():
    with pytest.raises(SystemExit):
        s.scope_labels("a\nstale_after=0")


# --- silence.yml -----------------------------------------------------------------------------------------------------

WF = yaml.safe_load((ROOT / ".github/workflows/silence.yml").read_text())
SPEC = (ROOT / "docs/spec.md").read_text()


def test_two_jobs_in_order_with_issues_write_only():
    jobs = WF["jobs"]
    assert list(jobs) == ["ping", "stale"] and jobs["stale"]["needs"] == "ping"
    assert WF["permissions"] == {} and all(j["permissions"] == {"issues": "write"} for j in jobs.values())


def test_stale_never_runs_without_its_scope():
    assert WF["jobs"]["stale"]["if"] == "needs.ping.outputs.only_labels != ''"


def test_stale_step_matches_the_spec():
    step = WF["jobs"]["stale"]["steps"][0]
    assert step["uses"].startswith("actions/stale@") and step["id"] == "stale"
    w = step["with"]
    fixed = {k: v for k, v in w.items() if "${{" not in str(v)}
    assert fixed == {"exempt-issue-labels": "keep-open,ai: off,ai: error", "stale-issue-label": "stale",
                     "remove-stale-when-updated": True, "close-issue-reason": "not_planned",
                     "close-issue-message": "Closed for lack of a reply. Add the requested details in a comment and "
                                            "a maintainer will reopen it.",
                     "days-before-pr-stale": -1, "days-before-pr-close": -1}
    for key in ("exempt-issue-labels", "close-issue-reason", "stale-issue-label"):
        assert f"{key}: '{w[key]}'" in SPEC, key
    message = w["stale-issue-message"]
    assert "will close in" in message and "{{ needs.ping.outputs.close_after }}" in message


def test_closed_issues_lose_the_silence_labels_after_the_stale_step():
    """aiwf-9ni: only when the stale step closed something; numbers reach the script through env only."""
    steps = WF["jobs"]["stale"]["steps"]
    cond = "steps.stale.outputs.closed-issues-prs != '' && steps.stale.outputs.closed-issues-prs != '[]'"
    assert [x.get("if") for x in steps[1:]] == [cond] * 3
    last = steps[-1]
    assert last["run"] == 'aiwf silence-closed --repo "$REPO"' and "${{" not in last["run"]
    assert last["env"]["AIWF_CLOSED"] == "${{ steps.stale.outputs.closed-issues-prs }}"


def test_ping_job_reads_extra_labels_through_env_only():
    step = WF["jobs"]["ping"]["steps"][-1]
    assert "inputs." not in step["run"] and step["env"]["EXTRA_LABELS"] == "${{ inputs.labels }}"
    assert WF[True]["workflow_call"]["inputs"]["labels"]["default"] == ""


# --- caller template -------------------------------------------------------------------------------------------------

TEMPLATE = (ROOT / "templates/caller.yml").read_text()


def _silence_job() -> dict:
    """The template's `silence` job: live, or commented out until the pinned release ships silence.yml."""
    live = (yaml.safe_load(TEMPLATE)["jobs"] or {}).get("silence")
    if live:
        return live
    block = re.search(r"^  # silence:\n((?:  #  .*\n)+)", TEMPLATE, re.M)
    assert block, "no silence job in the template"
    text = "silence:\n" + "".join(line.replace("  # ", "", 1) + "\n" for line in block.group(1).splitlines())
    return yaml.safe_load(text)["silence"]


def test_template_silence_job_runs_daily_and_on_manual_runs_when_triage_is_on():
    job = _silence_job()
    assert job["permissions"] == {"issues": "write"} and "secrets" not in job
    assert job["if"] == ("needs.config.outputs.triage == 'true' && "
                         "(github.event_name == 'schedule' || github.event_name == 'workflow_dispatch')")
    assert job["uses"].startswith("esciara/ai-workflows/.github/workflows/silence.yml@")
    assert job["with"] == {"config": "${{ needs.config.outputs.config }}"}


def test_template_silence_job_is_live_from_the_next_release():
    """silence.yml is not in v0.1.0, so the job stays commented out until the pins move to a later release."""
    tag = re.search(r"# (v\d+\.\d+\.\d+)$", TEMPLATE, re.M).group(1)
    live = "silence" in (yaml.safe_load(TEMPLATE)["jobs"] or {})
    want = "live" if tag != "v0.1.0" else "commented out"
    assert live is (tag != "v0.1.0"), f"template pins {tag}: the silence job must be {want}"
