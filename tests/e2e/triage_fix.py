"""Workflow B (analysis and fix loop) e2e helpers shared by test_wp8, test_wp9 and test_wp10 (moved out of test_wp8.py and test_wp9.py)."""

from __future__ import annotations

import base64
import os
import re
from typing import Any, Iterator

import pytest
import yaml

import playground as pg
from triage_core import (ERROR, NEEDS_HUMAN, NEEDS_INFO, REPRODUCE_JOB, REPRODUCED, bot_comments, e2e_config, item_run,
                         labels)

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


def reproduce_and_analyse(issue: dict[str, Any], files: str, runs: list[dict[str, Any]] | None = None) -> str:
    """Wait for B1, post `/reproduce`, and check the B2 + B3 + B4 outcome; return the analysis comment. The
    `/reproduce` run is appended to `runs` when given."""
    item_run("issues", issue["title"], issue["created_at"])
    _, run = command(issue, "/reproduce", timeout=ANALYSE_TIMEOUT)
    if runs is not None:
        runs.append(run)
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
    link = rf"https://github\.com/{re.escape(pg.REPO)}/blob/[0-9a-f]{{40}}/{files}(?:#L\d+)?"
    assert re.search(rf"^\*\*Root cause\*\*.*{link}", body, re.M), f"no root-cause line link into {files}"
    assert re.search(r"\*\*Risk tier:\*\* low\b", body), "risk tier is not low (src/ only)"
    assert re.search(r"\*\*Confidence:\*\* (high|medium|low)\b", body), "no confidence"
    assert re.search(r"\*\*Size:\*\* [SML]\b", body), "no size"
    for cmd in ("`/fix`", "`/fix <guidance>`", "`/no-fix <reason>`"):
        assert cmd in body, f"the analysis does not offer {cmd}"
    assert status(body).lower().startswith("waiting"), status(body)
    return body


NEEDS_MAINTAINER = "fix: needs-maintainer"
FIX_MARKER = "<!-- ai-workflows:fix -->"
ESCALATE_JOB = "triage / fix / escalate"
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


FAIL_LABEL = "e2e-fix-fail"
FAIL_CONFIG = ".github/ai-workflows-e2e-fix-fail.yml"
def fail_config() -> dict[str, Any]:
    raw = pg.api(f"repos/{pg.REPO}/contents/{FAIL_CONFIG}")
    cfg = yaml.safe_load(base64.b64decode(raw["content"]))
    if "exit 1" not in str(cfg.get("test", "")):
        pytest.fail(f"{FAIL_CONFIG} has no always-failing test command; not a pass", pytrace=False)
    return cfg
