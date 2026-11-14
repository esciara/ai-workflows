"""aiwf-kbc: one B1/B2 run per issue at a time; runs that start nothing get their own group (no expression engine:
the group's shape and its link to the B1/B2 entry conditions)."""
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


def test_every_b1_and_b2_start_is_in_the_issue_group():
    """Each command that starts B1 or B2 and the reporter's reply clause must queue in the issue's group."""
    jobs = WF["jobs"]
    starts = jobs["context"]["if"] + " " + jobs["repro-context"]["if"]
    commands = set(re.findall(r"command == '([a-z-]+)'", starts))
    assert commands == {"retriage", "reproduce"}
    assert all(f'"{c}"' in GROUP for c in commands)
    assert "github.event_name == 'issues'" in GROUP
    assert "github.event.comment.user.login == github.event.issue.user.login" in GROUP
    assert "fromJSON(inputs.config).command == ''" in GROUP and "!github.event.issue.pull_request" in GROUP


def test_reply_clause_is_exactly_repro_contexts():
    """Narrower than repro-context's: a reply could run B2 beside a running one. Wider: any comment by the reporter
    could take the pending slot and cancel a pending maintainer command."""
    clause = WF["jobs"]["repro-context"]["if"].split("||")[-1]
    conds = []
    for c in clause.split("&&"):
        c = " ".join(c.split()).lstrip("( ").rstrip(") }")  # drop the clause's own parentheses and the closing }}
        conds.append(c + ")" * (c.count("(") - c.count(")")))
    assert len(conds) == 5 and "contains(github.event.issue.labels.*.name, 'triage: needs-info')" in conds
    for cond in conds:
        assert cond in GROUP, cond
