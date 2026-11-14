"""WP8 acceptance test. Done when: a reproduced bug gets one analysis comment and `triage: awaiting-maintainer`;
`/fix <guidance>` and `/no-fix <reason>` do what the spec says; a non-maintainer's `/fix` changes nothing
(spec: B3, B4).

Runs against the playground (AIWF_E2E=1) with an e2e slot (AIWF_E2E_SLOT=1|2|3|any, ADR-0056). Issues carry the held
slot's `e2e-target-<n>` at creation, so its caller-e2e-<n>.yml runs triage.yml at the commit under test with the
playground's .github/ai-workflows-e2e.yml, as in WP6. Every issue is opened by the tester App (an outside reporter), so
B2 needs the maintainer's `/reproduce` first (WP6); B3 and B4 follow in that same run. Commands are posted by the
maintainer through scripts/dev/as-maintainer, the non-maintainer's `/fix` by the tester App. No playground PR is needed:
the slot callers already pass every issue comment to triage.yml.

Both bugs are real bugs in the playground's minicart, reported clearly so B2 reproduces them:

1. `/fix <guidance>`: the coupon discount kept after an item is removed. After `/reproduce`, the run's analyst job
   succeeds: `triage: reproduced` and `triage: awaiting-maintainer`, and one analysis comment (hidden marker) that
   mentions each of `maintainers`, links the run, has the root cause with a line link into the faulty module at a
   full commit SHA, the blast radius, the proposed fix, risk tier `low` (the e2e config's only high path is
   `.github/**`), a confidence and a size, the three commands, and the status "waiting". The maintainer's
   `/fix <guidance>` removes `triage: awaiting-maintainer`, adds no `fix: declined`, keeps `triage: reproduced`, and
   sets the same comment's status to "fix approved" by the maintainer, linking their comment and carrying the guidance.
2. `/no-fix <reason>` and the permission check: a percent tax rate crashes with decimal.InvalidOperation. After the
   analysis, the tester App's `/fix` changes nothing (labels and status as before). The maintainer's `/no-fix <reason>`
   labels `fix: declined`, removes `triage: awaiting-maintainer`, and sets the status to "fix declined".

Whether `/fix` starts B5 is WP9's test, not asserted here; WP9 updates this file (its `/fix` run then runs B5, longer
than COMMAND_TIMEOUT, and leaves an `ai-fix/issue-<n>` branch to clean up). Plain `/fix` (no guidance), a command on
an issue without `triage: awaiting-maintainer`, the risk-tier and link rules (a path not in the tree gets no link), the
path rules for the analyst's code, a B3 rerun updating the same comment (earlier decision kept as "previously") and a
non-reproducing B2 marking it superseded are left to the build PR's unit tests (none exist yet: this file is the gate).
"""

from __future__ import annotations

import os
import re
from typing import Any, Iterator

import pytest

import playground as pg
from test_wp6 import ERROR, NEEDS_HUMAN, NEEDS_INFO, REPRODUCE_JOB, REPRODUCED, bot_comments, item_run, labels
from test_wp7 import e2e_config

ANALYSIS_MARKER = "<!-- ai-workflows:analysis -->"
AWAITING = "triage: awaiting-maintainer"
DECLINED = "fix: declined"
ANALYSE_JOB = "triage / analyse"
ANALYSE_TIMEOUT = 2100  # the /reproduce run: setup + tests in the sandbox, then the analyst, on a cold runner
COMMAND_TIMEOUT = 600

COUPON_BUG = (
    "Coupon discount stays after removing an item",
    "Steps:\n\n```python\nfrom minicart.cart import Cart\nfrom minicart.discounts import apply_coupon\n"
    "cart = Cart()\ncart.add('A', '15.00')\ncart.add('B', '10.00')\napply_coupon(cart, 'FIVEOFF')  # needs 20.00\n"
    "cart.remove('B')\nprint(cart.total())\n```\n\nExpected: 15.00, since FIVEOFF needs a subtotal of at least 20.00 "
    "and the cart is now at 15.00.\nActual: 10.00; the 5.00 discount is still applied.\n\nminicart from main, Python 3.12.",
)
COUPON_FILES = r"src/minicart/(cart|discounts)\.py"
TAX_BUG = (
    "A percent tax rate crashes with decimal.InvalidOperation",
    "Steps:\n\n```python\nfrom minicart.cart import Cart\nCart(tax_rate='8%')\n```\n\n"
    "Expected: a clear ValueError saying the rate must be a number between 0 and 1.\n"
    "Actual: `decimal.InvalidOperation` raised from `to_decimal` in minicart/money.py.\n\nminicart from main, Python 3.12.",
)
TAX_FILES = r"src/minicart/(cart|money)\.py"
GUIDANCE_TEXT = "keep the public signature of Cart.total unchanged"
GUIDANCE = f"/fix {GUIDANCE_TEXT}"
REASON = "/no-fix not worth changing before the 1.0 release"


@pytest.fixture
def tag(testrun_uid: str) -> str:
    return testrun_uid[:8]


@pytest.fixture
def opened() -> Iterator[list[int]]:
    """Issues this test opened; closed as not planned at teardown (never deleted)."""
    numbers: list[int] = []
    yield numbers
    for n in numbers:
        pg.api(f"repos/{pg.REPO}/issues/{n}", "state=closed", "state_reason=not_planned", method="PATCH")


def open_as_reporter(kind: str, report: tuple[str, str], tag: str, opened: list[int]) -> dict[str, Any]:
    if not os.environ.get("AI_WORKFLOWS_TESTER_APP_ID"):
        pytest.fail("AI_WORKFLOWS_TESTER_APP_ID is not set; cannot open issues as the tester App (not a pass)",
                    pytrace=False)
    title, body = report
    issue = pg.open_issue(f"[e2e] WP8 {kind} {tag}: {title}", body, e2e=True, as_tester=True)
    opened.append(issue["number"])
    full = pg.api(f"repos/{pg.REPO}/issues/{issue['number']}")
    author = full["user"]["login"]
    assert author.endswith("[bot]") and author != pg.BOT, f"#{issue['number']} not opened by the tester App: {author}"
    return {**issue, "created_at": full["created_at"]}


def command(issue: dict[str, Any], body: str, *, as_tester: bool = False,
            timeout: int = COMMAND_TIMEOUT) -> tuple[dict[str, Any], dict[str, Any]]:
    """Post a comment (maintainer by default) and return it with its completed run."""
    c = pg.comment(issue["number"], body, as_tester=as_tester)
    run = item_run("issue_comment", issue["title"], c["created_at"], timeout=timeout)
    if body != "/reproduce":
        assert run["jobs"].get(REPRODUCE_JOB) in (None, "skipped"), f"a command reran B2: {run['jobs']}"
    return c, run


def analysis(number: int) -> str:
    notes = bot_comments(number, ANALYSIS_MARKER)
    assert len(notes) == 1, [c["html_url"] for c in notes]
    return notes[0]["body"]


def status(body: str) -> str:
    m = re.search(r"^\*\*Status:\*\* (.+)$", body, re.M)
    assert m, "no status line in the analysis comment"
    return m.group(1)


def reproduce_and_analyse(issue: dict[str, Any], files: str) -> str:
    """Wait for B1, post `/reproduce`, and check the B2 + B3 + B4 outcome; return the analysis comment."""
    item_run("issues", issue["title"], issue["created_at"])
    _, run = command(issue, "/reproduce", timeout=ANALYSE_TIMEOUT)
    assert run["jobs"].get(REPRODUCE_JOB) == "success" and run["jobs"].get(ANALYSE_JOB) == "success", run["jobs"]
    assert run["conclusion"] == "success", run["jobs"]
    got = labels(issue["number"])
    print(f"#{issue['number']}: labels {sorted(got)}")
    assert {"type: bug", REPRODUCED, AWAITING} <= got, sorted(got)
    assert not got & {NEEDS_INFO, NEEDS_HUMAN, ERROR, DECLINED}, sorted(got)

    body = analysis(issue["number"])
    print(body)
    for login in e2e_config()["maintainers"]:
        assert f"@{login}" in body, f"the analysis does not mention maintainer {login}"
    assert run["html_url"] in body, "the analysis does not link the run that made it"
    for section in ("Root cause", "Blast radius", "Proposed fix"):
        assert re.search(rf"\*\*{section}\*\*", body), f"no {section} section"
    link = rf"https://github\.com/{re.escape(pg.REPO)}/blob/[0-9a-f]{{40}}/{files}#L\d+"
    assert re.search(rf"^\*\*Root cause\*\*.*{link}", body, re.M), f"no root-cause line link into {files}"
    assert re.search(r"\*\*Risk tier:\*\* low\b", body), "risk tier is not low (src/ only)"
    assert re.search(r"\*\*Confidence:\*\* (high|medium|low)\b", body), "no confidence"
    assert re.search(r"\*\*Size:\*\* [SML]\b", body), "no size"
    for cmd in ("`/fix`", "`/fix <guidance>`", "`/no-fix <reason>`"):
        assert cmd in body, f"the analysis does not offer {cmd}"
    assert status(body).lower().startswith("waiting"), status(body)
    return body


def test_reproduced_bug_is_analysed_and_fix_with_guidance_is_accepted(e2e_target, tag, opened):
    issue = open_as_reporter("fix", COUPON_BUG, tag, opened)
    reproduce_and_analyse(issue, COUPON_FILES)

    c, run = command(issue, GUIDANCE)
    assert run["conclusion"] == "success", run["jobs"]
    got = labels(issue["number"])
    print(f"#{issue['number']}: labels {sorted(got)}")
    assert REPRODUCED in got and not got & {AWAITING, DECLINED, ERROR}, sorted(got)
    line = status(analysis(issue["number"]))
    print(line)
    assert re.match(rf"fix approved by @{re.escape(c['user'])}\b", line, re.I), line
    assert f"issuecomment-{c['id']}" in line, "the status does not link the maintainer's /fix comment"
    assert GUIDANCE_TEXT in line, "the status does not carry the /fix guidance"


def test_no_fix_declines_and_a_non_maintainer_fix_changes_nothing(e2e_target, tag, opened):
    issue = open_as_reporter("no-fix", TAX_BUG, tag, opened)
    before = status(reproduce_and_analyse(issue, TAX_FILES))

    _, run = command(issue, "/fix", as_tester=True)  # the reporter is not a maintainer: not a command
    assert run["conclusion"] == "success", run["jobs"]
    assert run["jobs"].get(ANALYSE_JOB) in (None, "skipped"), run["jobs"]
    got = labels(issue["number"])
    assert AWAITING in got and DECLINED not in got, sorted(got)
    assert status(analysis(issue["number"])) == before

    c, run = command(issue, REASON)
    assert run["conclusion"] == "success", run["jobs"]
    got = labels(issue["number"])
    print(f"#{issue['number']}: labels {sorted(got)}")
    assert DECLINED in got and REPRODUCED in got and not got & {AWAITING, ERROR}, sorted(got)
    line = status(analysis(issue["number"]))
    print(line)
    assert re.match(rf"fix declined by @{re.escape(c['user'])}\b", line, re.I), line
    assert f"issuecomment-{c['id']}" in line, "the status does not link the maintainer's /no-fix comment"
