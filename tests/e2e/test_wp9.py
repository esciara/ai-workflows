"""WP9 acceptance test. Done when: a seeded bug is fixed in at most 3 rounds; a forced failure gives a draft PR,
`fix: needs-maintainer`, assignment and review request (spec: B4 `/fix`, B5).

Runs against the playground (AIWF_E2E=1) with an e2e slot (AIWF_E2E_SLOT=1|2|3|any, ADR-0056), as WP8: issues carry
the held slot's `e2e-target-<n>`, are opened by the tester App (an outside reporter), get the maintainer's `/reproduce`
(B2, then B3 and B4 in that run), then the maintainer's `/fix`. The `/fix` run is the one B5 runs in.

The build adds, in a maintainer-merged playground PR:

- `.github/ai-workflows-e2e-fix-fail.yml`: the e2e config with `limits.fix_rounds: 1` and a `test` command that always
  fails with a message saying so (e.g. `echo 'forced failure (e2e)'; exit 1`), so the orchestrator's exit-condition
  check fails every round, deterministically, whatever the implementer does;
- to the three slot callers, `config_path` set to that file when the issue carries `e2e-fix-fail` (like WP12a's
  `e2e-crash`, the product has no test hook, ADR-0050). The label is added after B4, so B2 and B3 ran on the normal
  e2e config;
- the repo setting that lets the workflow's `GITHUB_TOKEN` open pull requests, as the open decision on
  `docs/known-issues.md` ("Workflow B cannot open PRs ...") settles it.

1. `/fix <guidance>` to an approved fix: the coupon bug from WP8 (this scenario replaces WP8's first one, whose
   assertions it keeps). The `/fix <guidance>` run succeeds: `triage: awaiting-maintainer` gone, `triage: reproduced`
   kept, the status line says "fix approved" by the maintainer with a link to the comment and the guidance. B5 ran 1 to
   `fix_rounds` rounds (job names `round-<k>`), the last round's review succeeded and the escalation job was skipped:
   no `fix: needs-maintainer`, no draft PR. Branch `ai-fix/issue-<n>` exists, is ahead of the default branch, and
   changes the faulty module and a test file, and nothing under `.github/`.
2. Forced failure to the maintainer: the tax-rate bug from WP8, labelled `e2e-fix-fail` before plain `/fix`. The run
   succeeds (escalation is an exit, not `ai: error`) after exactly `fix_rounds` (1) rounds: `fix: needs-maintainer`,
   one escalation comment (hidden marker) that mentions each of `maintainers`, has each round's findings (the failing
   check's output) and links the draft PR; that PR is a draft from `ai-fix/issue-<n>`, and each maintainer is assigned
   to the issue and to the PR and requested as a reviewer on it.

Left to unit tests: the guidance reaching the implementer's brief (as data), the reviewer's fresh context, a reviewer
`reject` leading to the next round, a branch that already exists (B5 does not start), a person's push to the branch
(loop stops), a diff touching `.github/workflows/**` (round fails), a later B2 changing the status line (no push), and
the exit-condition check (setup, test, repro command) deciding the round. B6 (the fix PR and Workflow A on it) is
WP10's test; this file asserts no non-draft PR either way.
"""

from __future__ import annotations

import base64
import re
from typing import Any, Iterator

import pytest
import yaml

import playground as pg
from test_wp6 import ERROR, REPRODUCED, bot_comments, labels
from test_wp7 import e2e_config
from test_wp8 import (AWAITING, COUPON_BUG, COUPON_FILES, DECLINED, GUIDANCE, GUIDANCE_TEXT, TAX_BUG, TAX_FILES,
                      analysis, command, open_as_reporter, reproduce_and_analyse, status)

NEEDS_MAINTAINER = "fix: needs-maintainer"
FIX_MARKER = "<!-- ai-workflows:fix -->"
FAIL_LABEL = "e2e-fix-fail"
FAIL_CONFIG = ".github/ai-workflows-e2e-fix-fail.yml"
ESCALATE_JOB = "triage / escalate"
FIX_TIMEOUT = 5400  # up to 3 rounds of implementer (setup + tests in the sandbox), check and reviewer, cold runners
ROUND = re.compile(r"/ round-(\d+) / (\w+)$")


@pytest.fixture
def tag(testrun_uid: str) -> str:
    return testrun_uid[:8]


@pytest.fixture
def opened() -> Iterator[list[int]]:
    """Issues this test opened. At teardown: their `ai-fix/issue-<n>` PRs closed and branches deleted (as the agent
    App, test cleanup only), then the issues closed as not planned (never deleted)."""
    numbers: list[int] = []
    yield numbers
    for n in numbers:
        branch = fix_branch(n)
        for pr in fix_prs(n):
            if pr["state"] == "open":
                pg.api(f"repos/{pg.REPO}/pulls/{pr['number']}", "state=closed", method="PATCH")
        if branch_sha(branch):
            pg.api(f"repos/{pg.REPO}/git/refs/heads/{branch}", method="DELETE")
        pg.api(f"repos/{pg.REPO}/issues/{n}", "state=closed", "state_reason=not_planned", method="PATCH")


def fix_branch(number: int) -> str:
    return f"ai-fix/issue-{number}"


def branch_sha(branch: str) -> str | None:
    refs = pg.api(f"repos/{pg.REPO}/git/matching-refs/heads/{branch}")
    hit = [r for r in refs if r["ref"] == f"refs/heads/{branch}"]
    return hit[0]["object"]["sha"] if hit else None


def fix_prs(number: int) -> list[dict[str, Any]]:
    owner = pg.REPO.split("/")[0]
    return pg.api(f"repos/{pg.REPO}/pulls?head={owner}:{fix_branch(number)}&state=all&per_page=10")


def rounds(run: dict[str, Any]) -> dict[int, dict[str, str]]:
    """Round number -> {job: conclusion} from the run's `round-<k>` jobs (skipped rounds left out)."""
    got: dict[int, dict[str, str]] = {}
    for name, conclusion in run["jobs"].items():
        m = ROUND.search(name)
        if m and conclusion != "skipped":
            got.setdefault(int(m.group(1)), {})[m.group(2)] = conclusion
    print(f"rounds: {got}")
    return got


def fail_config() -> dict[str, Any]:
    raw = pg.api(f"repos/{pg.REPO}/contents/{FAIL_CONFIG}")
    cfg = yaml.safe_load(base64.b64decode(raw["content"]))
    if "exit 1" not in str(cfg.get("test", "")):
        pytest.fail(f"{FAIL_CONFIG} has no always-failing test command; not a pass", pytrace=False)
    return cfg


def fix(issue: dict[str, Any], body: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The maintainer's `/fix` and its completed run, which ran the decision and B5."""
    c, run = command(issue, body, timeout=FIX_TIMEOUT)
    assert run["conclusion"] == "success", run["jobs"]
    got = labels(issue["number"])
    print(f"#{issue['number']}: labels {sorted(got)}")
    assert REPRODUCED in got and not got & {AWAITING, DECLINED, ERROR}, sorted(got)
    line = status(analysis(issue["number"]))
    print(line)
    assert re.match(rf"fix approved by @{re.escape(c['user'])}\b", line, re.I), line
    assert f"issuecomment-{c['id']}" in line, "the status does not link the maintainer's /fix comment"
    return c, run


def test_fix_with_guidance_runs_the_fix_loop_to_an_approved_branch(e2e_target, tag, opened):
    issue = open_as_reporter("fix", COUPON_BUG, tag, opened)
    reproduce_and_analyse(issue, COUPON_FILES)

    _, run = fix(issue, GUIDANCE)
    assert GUIDANCE_TEXT in status(analysis(issue["number"])), "the status does not carry the /fix guidance"
    done = rounds(run)
    cap = e2e_config().get("limits", {}).get("fix_rounds", 3)
    assert done and max(done) <= cap and sorted(done) == list(range(1, max(done) + 1)), done
    assert done[max(done)].get("review") == "success", done
    assert run["jobs"].get(ESCALATE_JOB) in (None, "skipped"), run["jobs"]
    assert NEEDS_MAINTAINER not in labels(issue["number"])
    assert not [p for p in fix_prs(issue["number"]) if p["draft"]], "an approved fix opened a draft PR"

    branch = fix_branch(issue["number"])
    assert branch_sha(branch), f"no {branch} branch"
    default = pg.api(f"repos/{pg.REPO}")["default_branch"]
    cmp = pg.api(f"repos/{pg.REPO}/compare/{default}...{branch}")
    files = [f["filename"] for f in cmp["files"]]
    print(f"{branch}: {cmp['ahead_by']} commit(s) ahead, files {files}")
    assert cmp["ahead_by"] >= 1, cmp["ahead_by"]
    assert any(re.fullmatch(COUPON_FILES, f) for f in files), f"the fix does not touch {COUPON_FILES}: {files}"
    assert any(re.fullmatch(r"tests/.+\.py", f) for f in files), f"no test file in the fix: {files}"
    assert not [f for f in files if f.startswith(".github/")], f"the fix touches .github/: {files}"


def test_a_forced_failure_escalates_to_a_draft_pr_and_the_maintainer(e2e_target, tag, opened):
    cap = fail_config()["limits"]["fix_rounds"]
    issue = open_as_reporter("fix-fail", TAX_BUG, tag, opened)
    reproduce_and_analyse(issue, TAX_FILES)
    pg.ensure_label(FAIL_LABEL, "d93f0b", "e2e only: the e2e caller loads a config whose test command always fails")
    pg.api(f"repos/{pg.REPO}/issues/{issue['number']}/labels", f"labels[]={FAIL_LABEL}", method="POST")

    _, run = fix(issue, "/fix")
    done = rounds(run)
    assert sorted(done) == list(range(1, cap + 1)), f"expected exactly {cap} round(s): {done}"
    # A failed check skips the reviewer (spec B5): `rounds` leaves skipped jobs out.
    assert all(j.get("check") == "failure" and "review" not in j for j in done.values()), done
    assert run["jobs"].get(ESCALATE_JOB) == "success", run["jobs"]
    assert NEEDS_MAINTAINER in labels(issue["number"])

    maintainers = e2e_config()["maintainers"]
    [pr] = [p for p in fix_prs(issue["number"]) if p["state"] == "open"]
    pr = pg.api(f"repos/{pg.REPO}/pulls/{pr['number']}")
    print(f"draft PR {pr['html_url']}: draft={pr['draft']}")
    assert pr["draft"], "the escalation PR is not a draft"
    assert pr["head"]["ref"] == fix_branch(issue["number"]), pr["head"]["ref"]
    reviewers = {u["login"] for u in pr["requested_reviewers"]}
    pr_assignees = {u["login"] for u in pr["assignees"]}
    issue_assignees = {u["login"] for u in pg.api(f"repos/{pg.REPO}/issues/{issue['number']}")["assignees"]}
    for login in maintainers:
        assert login in reviewers, f"{login} not requested as reviewer: {reviewers}"
        assert login in pr_assignees, f"{login} not assigned to the PR: {pr_assignees}"
        assert login in issue_assignees, f"{login} not assigned to the issue: {issue_assignees}"

    notes = bot_comments(issue["number"], FIX_MARKER)
    assert len(notes) == 1, [c["html_url"] for c in notes]
    body = notes[0]["body"]
    print(body)
    for login in maintainers:
        assert f"@{login}" in body, f"the escalation comment does not mention {login}"
    assert pr["html_url"] in body or f"#{pr['number']}" in body, "the escalation comment does not link the draft PR"
    for k in range(1, cap + 1):
        assert re.search(rf"\bRound {k}\b", body), f"no findings for round {k}"
    assert "forced failure (e2e)" in body, "the round's findings do not carry the failing check's output"
