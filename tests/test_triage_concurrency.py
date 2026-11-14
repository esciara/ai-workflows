"""aiwf-kbc: one B1/B2 run per issue at a time; runs that start nothing get their own group (no expression engine:
the group's shape and its link to the B1/B2 entry conditions)."""
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WF = yaml.safe_load((ROOT / ".github" / "workflows" / "triage.yml").read_text())
GROUP = " ".join(WF["concurrency"]["group"].split())


def test_runs_queue_never_cancel():
    assert WF["concurrency"]["cancel-in-progress"] is False


def test_issue_group_for_starting_runs_else_own_group():
    assert GROUP.startswith("aiwf-triage-${{ github.workflow }}-${{ ") and GROUP.endswith(" }}")
    assert GROUP.endswith("&& format('issue-{0}', github.event.issue.number) || format('run-{0}', github.run_id) }}")
    assert not GROUP.startswith("ai-workflows-")  # the caller's group prefix: sharing it would deadlock


def norm(text: str) -> str:
    return " ".join(text.split())


# The reporter's reply, as repro-context starts B2 on it. In both expressions: narrower in the group, a reply could run
# B2 beside a running one; wider, any comment by the reporter could replace a pending maintainer command.
REPLY = ["github.event_name == 'issue_comment'", "!github.event.issue.pull_request",
         "fromJSON(inputs.config).command == ''",
         "github.event.comment.user.login == github.event.issue.user.login",
         "contains(github.event.issue.labels.*.name, 'triage: needs-info')"]


def test_reply_clause_is_the_same_as_repro_contexts():
    starts = norm(WF["jobs"]["repro-context"]["if"])
    for cond in REPLY:
        assert cond in starts and cond in GROUP, cond


def test_every_b1_and_b2_command_and_new_issues_are_in_the_issue_group():
    jobs = WF["jobs"]
    starts = norm(jobs["context"]["if"] + " " + jobs["repro-context"]["if"])
    commands = set(re.findall(r"command == '([a-z-]+)'", starts))
    assert commands == {"retriage", "reproduce"}
    assert f"""contains(fromJSON('{json.dumps(sorted(commands, reverse=True))}'), fromJSON(inputs.config).command)""" in GROUP
    assert "github.event_name == 'issues'" in GROUP
