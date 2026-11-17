"""WP8 acceptance test. Done when: a reproduced bug gets one analysis comment and `triage: awaiting-maintainer`;
`/fix <guidance>` (now asserted in test_wp9) and `/no-fix <reason>` do what the spec says; a non-maintainer's `/fix`
changes nothing (spec: B3, B4).

Runs against the playground (AIWF_E2E=1) with an e2e slot (AIWF_E2E_SLOT=1|2|3|any, ADR-0056). Issues carry the held
slot's `e2e-target-<n>` at creation, so its caller-e2e-<n>.yml runs triage.yml at the commit under test with the
playground's .github/ai-workflows-e2e.yml, as in WP6. Every issue is opened by the tester App (an outside reporter), so
B2 needs the maintainer's `/reproduce` first (WP6); B3 and B4 follow in that same run. Commands are posted by the
maintainer through scripts/dev/as-maintainer, the non-maintainer's `/fix` by the tester App. No playground PR is needed:
the slot callers already pass every issue comment to triage.yml.

Both bugs are real bugs in the playground's minicart, reported clearly so B2 reproduces them:

1. `/fix <guidance>`, the coupon discount kept after an item is removed: moved to `tests/e2e/test_wp9.py` (scenario 1)
   with all its assertions, since WP9 makes that `/fix` run B5 (longer than COMMAND_TIMEOUT, and it leaves an
   `ai-fix/issue-<n>` branch to clean up). The analysis checks it shared with scenario 2 stay in
   `reproduce_and_analyse`; the bug and guidance constants stay here, test_wp9 imports them.
2. `/no-fix <reason>` and the permission check: a percent tax rate crashes with decimal.InvalidOperation. After the
   analysis, the tester App's `/fix` changes nothing (labels and status as before). The maintainer's `/no-fix <reason>`
   labels `fix: declined`, removes `triage: awaiting-maintainer`, and sets the status to "fix declined" with the reason.

Whether `/fix` starts B5 is WP9's test (`tests/e2e/test_wp9.py`), not asserted here; the tester App's `/fix` below is
not a command, so it starts nothing. Plain `/fix` (no guidance), a command on an issue without
`triage: awaiting-maintainer`, the risk-tier and link rules (a path not in the tree gets no link), the path rules
for the analyst's code, a B3 rerun updating the same comment (earlier decision kept as "previously") and a
non-reproducing B2 marking it superseded are left to the build PR's unit tests (none exist yet: this file is the gate).
"""

from __future__ import annotations

import re
from typing import Iterator

import pytest

import playground as pg
from triage_core import ERROR, REPRODUCED, labels
from triage_fix import (ANALYSE_JOB, AWAITING, DECLINED, TAX_BUG, TAX_FILES, analysis, command, open_as_reporter,
                        reproduce_and_analyse, status)

REASON_TEXT = "not worth changing before the 1.0 release"
REASON = f"/no-fix {REASON_TEXT}"


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
    assert REASON_TEXT in line, "the status does not carry the /no-fix reason"
