"""B2 fix-check acceptance test (aiwf-1st). Done when: for a bug that was already fixed on the default branch, B1 names
the fix ("Possibly fixed on the default branch by ..."), and after the maintainer's `/reproduce` B2 confirms it: one
"Confirmed fixed" comment that cites the commit just before the fix, label `triage: fixed`, no question to the reporter,
no `triage: reproduced`, and the issue stays open (spec B2 step 4).

Runs against the playground (AIWF_E2E=1, AIWF_E2E_SLOT=any) like test_wp6. It needs the playground's seeded fixed bug
(esciara/ai-workflows-playground PR "an already-fixed bug in minicart (format_money)": a commit adding `format_money`
with a bug, then the commit `fix(money): format_money printed a negative amount ...` fixing it, merged by rebase so both
stay in history). The issue below reports that bug; it is opened by the tester App and `/reproduce` is posted by the
maintainer, as in test_wp6.
"""

from __future__ import annotations

from typing import Iterator

import pytest

import playground as pg
from triage_core import ERROR, NEEDS_HUMAN, NEEDS_INFO, NEEDS_INFO_MARKER, REPRODUCED, bot_comments, comment_run, \
    item_run, labels
from triage_fix import open_as_reporter

TRIAGE_MARKER = "<!-- ai-workflows:triage -->"
FIX_MARKER = "<!-- ai-workflows:fix-check -->"
FIXED = "triage: fixed"
FIX_SUBJECT = "fix(money): format_money printed a negative amount"  # the playground's seeded fix commit (prefix)
FIXED_BUG = (
    "format_money puts the minus sign after the dollar sign",
    "Steps:\n\n```python\nfrom minicart.money import format_money\nprint(format_money('-5'))\n```\n\n"
    "Expected: `-$5.00`.\nActual: `$-5.00`; the minus sign comes after the currency symbol (src/minicart/money.py).\n\n"
    "minicart, Python 3.12.",
)


@pytest.fixture
def opened() -> Iterator[list[int]]:
    """Issues this test opened; closed as not planned at teardown (never deleted)."""
    numbers: list[int] = []
    yield numbers
    for n in numbers:
        pg.api(f"repos/{pg.REPO}/issues/{n}", "state=closed", "state_reason=not_planned", method="PATCH")


def seeded_fix_parent() -> str:
    """Short SHA of the commit just before the playground's seeded fix on main (fails the test if it was not merged)."""
    commits = pg.api(f"repos/{pg.REPO}/commits?sha=main&path=src/minicart/money.py&per_page=30")
    fix = next((c for c in commits if c["commit"]["message"].startswith(FIX_SUBJECT)), None)
    assert fix, f"the playground has no commit starting {FIX_SUBJECT!r}: merge the seeded-fix PR first (not a pass)"
    return fix["parents"][0]["sha"][:7]


def test_an_already_fixed_bug_is_named_by_b1_and_confirmed_by_b2(e2e_target, tag, opened):
    before = seeded_fix_parent()
    issue = open_as_reporter("fixcheck", FIXED_BUG, tag, opened)
    run = item_run("issues", issue["title"], issue["created_at"])
    assert run["conclusion"] == "success", run["jobs"]
    triage = bot_comments(issue["number"], TRIAGE_MARKER)
    assert len(triage) == 1, [c["html_url"] for c in triage]
    assert "Possibly fixed on the default branch by" in triage[0]["body"], triage[0]["body"][:600]

    run = comment_run(issue, "/reproduce", as_tester=False)
    assert run["conclusion"] == "success", run["jobs"]
    got = labels(issue["number"])
    print(f"#{issue['number']}: labels {sorted(got)}")
    assert FIXED in got, sorted(got)
    assert not got & {REPRODUCED, NEEDS_INFO, NEEDS_HUMAN, ERROR}, sorted(got)
    notes = bot_comments(issue["number"], FIX_MARKER)
    assert len(notes) == 1, [c["html_url"] for c in notes]
    body = notes[0]["body"]
    print(body)
    assert "confirmed fixed" in body.lower(), body[:300]
    assert before in body, f"the comment does not cite the commit before the fix ({before})"
    assert run["html_url"] in body, "the comment does not link the run that confirmed it"
    assert not bot_comments(issue["number"], NEEDS_INFO_MARKER), "B2 asked the reporter questions"
    assert pg.api(f"repos/{pg.REPO}/issues/{issue['number']}")["state"] == "open", "the issue was closed"
