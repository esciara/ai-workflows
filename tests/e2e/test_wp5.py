"""WP5 acceptance test. Done when: 3 test issues get `type: bug`, `feature`, `question`; a duplicate gets `triage: duplicate`.

Runs against the playground (AIWF_E2E=1, AIWF_E2E_SLOT=1): issues are opened by the tester App (the outside reporter)
with the `e2e-target` label at creation, so the playground's caller-e2e.yml runs triage.yml at the ref under test
(ADR-0028, ADR-0029). Each test opens fresh issues whose titles carry this run's id, and closes them as "not planned"
at teardown so later runs do not see them as duplicates.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterator

import pytest

import playground as pg

E2E_WORKFLOW = pg.E2E_WORKFLOW  # the held slot's playground caller, caller-e2e-<n>.yml (ADR-0056)
TRIAGE_MARKER = "<!-- ai-workflows:triage -->"
TYPE_LABELS = {"type: bug", "type: feature", "type: question"}
DUPLICATE = "triage: duplicate"
TITLE_PREFIX = "[e2e] WP5"

BUG = (
    "Fractional quantity is accepted, then total() fails",
    "Steps:\n\n```python\nfrom minicart.cart import Cart\ncart = Cart()\ncart.add('A', '10.00', quantity=1.5)\n"
    "print(cart.total())\n```\n\nExpected: `add` refuses the quantity with a ValueError, since it must be a whole "
    "number.\nActual: `add` accepts it, and `total()` then raises `TypeError: unsupported operand type(s) for *: "
    "'decimal.Decimal' and 'float'`.\n\nminicart from main, Python 3.12.",
)
FEATURE = (
    "Support gift cards as a payment method",
    "It would be great if minicart could hold gift cards: a code with a balance that is subtracted from the total "
    "after tax, with the remaining balance kept on the card. Today only coupons exist, and they change the taxable "
    "amount. This is a request for new functionality; nothing is broken.",
)
QUESTION = (
    "How should I pass the tax rate for a 7.5% tax?",
    "I'm new to minicart. Should I write `Cart(tax_rate='7.5')`, `Cart(tax_rate='0.075')` or "
    "`Cart(tax_rate=7.5)`? The README does not say which form the constructor expects. Thanks!",
)
DUP_ORIGINAL = (
    "Cart(tax_rate='8%') crashes with decimal.InvalidOperation",
    "Steps:\n\n```python\nfrom minicart.cart import Cart\nCart(tax_rate='8%')\n```\n\nExpected: a clear ValueError "
    "saying the rate must be a number between 0 and 1.\nActual: `decimal.InvalidOperation: "
    "[<class 'decimal.ConversionSyntax'>]` with a traceback from minicart/money.py.\n\nminicart from main, Python 3.12.",
)
DUP_COPY = (
    "Percent sign in tax rate raises an obscure decimal error",
    "Creating a cart with the tax rate written as a percentage, e.g. `Cart(tax_rate=\"8%\")`, blows up with "
    "`decimal.InvalidOperation` (ConversionSyntax) raised from `to_decimal` in money.py instead of a ValueError "
    "with a helpful message. Seen on main today.",
)


@pytest.fixture
def run_tag(testrun_uid: str) -> str:
    """Unique per test run (shared by xdist workers), so titles never collide with earlier runs."""
    return testrun_uid[:8]


@pytest.fixture
def opened(run_tag: str) -> Iterator[list[int]]:
    """Issues this test opened, closed as "not planned" at teardown (pg.close_issue); also closes open WP5 issues left
    by earlier crashed runs."""
    pg.close_left_over(TITLE_PREFIX, keep=run_tag)
    numbers: list[int] = []
    yield numbers
    for n in numbers:
        pg.close_issue(n)


def open_as_reporter(kind: str, report: tuple[str, str], run_tag: str, opened: list[int]) -> dict[str, Any]:
    title, body = report
    issue = pg.open_as_reporter(f"{TITLE_PREFIX} {kind} {run_tag}: {title}", body)
    opened.append(issue["number"])
    return issue


def triage_run(issue: dict[str, Any]) -> dict[str, Any]:
    """The completed e2e `issues` run for this issue; its triage jobs succeeded."""
    run = pg.issues_run(issue, E2E_WORKFLOW)
    jobs = pg.jobs(run["id"])
    assert run["conclusion"] == "success", jobs
    triage_jobs = {k: v for k, v in jobs.items() if k.startswith("triage / ")}
    assert triage_jobs and all(v in {"success", "skipped"} for v in triage_jobs.values()), jobs
    assert any(v == "success" for v in triage_jobs.values()), jobs
    return run


def state(number: int) -> dict[str, Any]:
    """Labels, open/closed state and the bot's triage comments on the issue, read after the run completed."""
    issue = pg.api(f"repos/{pg.REPO}/issues/{number}")
    out = pg.gh(["api", "--paginate", f"repos/{pg.REPO}/issues/{number}/comments?per_page=100", "--jq", ".[]"])
    comments = [json.loads(line) for line in out.splitlines() if line.strip()]
    triage = [c for c in comments if c["user"]["login"] == pg.BOT and TRIAGE_MARKER in (c["body"] or "")]
    return {"labels": {lb["name"] for lb in issue["labels"]}, "state": issue["state"], "comments": triage}


def assert_classified(number: int, expected: str) -> dict[str, Any]:
    s = state(number)
    print(f"#{number}: labels {sorted(s['labels'])}; triage comment: {[c['html_url'] for c in s['comments']]}")
    assert s["labels"] & TYPE_LABELS == {expected}, f"#{number}: type labels {sorted(s['labels'] & TYPE_LABELS)}"
    assert "ai: error" not in s["labels"], s["labels"]
    assert s["state"] == "open", f"#{number} was closed; triage never closes"
    assert len(s["comments"]) == 1, f"#{number}: expected one triage comment, got {len(s['comments'])}"
    return s


@pytest.mark.parametrize(
    "kind,report,expected",
    [("bug", BUG, "type: bug"), ("feature", FEATURE, "type: feature"), ("question", QUESTION, "type: question")],
)
def test_issue_gets_its_type_label(kind, report, expected, e2e_target, run_tag, opened):
    issue = open_as_reporter(kind, report, run_tag, opened)
    triage_run(issue)
    s = assert_classified(issue["number"], expected)
    assert DUPLICATE not in s["labels"], f"#{issue['number']} is not a duplicate of anything: {sorted(s['labels'])}"
    body = s["comments"][0]["body"]
    assert expected.split(": ")[1] in body.lower(), f"triage comment does not state the class {expected}: {body[:300]}"


def test_duplicate_gets_triage_duplicate_with_link(e2e_target, run_tag, opened):
    original = open_as_reporter("dup-original", DUP_ORIGINAL, run_tag, opened)
    triage_run(original)
    orig = state(original["number"])
    assert DUPLICATE not in orig["labels"], f"original #{original['number']} flagged as a duplicate: {sorted(orig['labels'])}"

    dup = open_as_reporter("dup-copy", DUP_COPY, run_tag, opened)
    triage_run(dup)
    s = state(dup["number"])
    print(f"#{dup['number']}: labels {sorted(s['labels'])}; triage comment: {[c['html_url'] for c in s['comments']]}")
    assert DUPLICATE in s["labels"], f"#{dup['number']} not labelled {DUPLICATE}: {sorted(s['labels'])}"
    assert "ai: error" not in s["labels"], s["labels"]
    assert s["state"] == "open", f"#{dup['number']} was closed; a duplicate is labelled, never closed"
    assert len(s["comments"]) == 1, f"#{dup['number']}: expected one triage comment, got {len(s['comments'])}"
    body = s["comments"][0]["body"]
    link = re.compile(rf"(#{original['number']}\b|{re.escape(original['html_url'])}(?!\d))")
    assert link.search(body), f"triage comment does not link the original #{original['number']}: {body[:300]}"
