"""WP3 acceptance test. Done when: a seeded-bug PR gets an inline comment and Request changes; a nit on a low-risk path
stays in the summary.

Runs against the playground (AIWF_E2E=1) with the e2e slot (AIWF_E2E_SLOT=1): the PR comes from an `e2e/` branch, so
caller-e2e.yml reviews it with review.yml@e2e-target, which the slot points at the commit under test (ADR-0028/0029).
The playground's e2e config (.github/ai-workflows-e2e.yml in the playground) makes only `.github/**` high risk, so `src/` is low risk.

One PR carries both seeds, committed before the PR is opened so the `opened` event reviews them: a blocking bug in a
new `Cart.apply_bulk_discount` (the percent is not divided by 100) and typos in a docstring of `money.py` (a nit).
A second push then fixes the bug, which reruns the review on a PR with findings (the last run's findings marked
resolved or still open, the Request changes review dismissed); that rerun must complete, its outcome is only printed.
"""

from __future__ import annotations

import json
import re
import time

import playground as pg
from playground import labels
from review_seeded import (BUG_LINE, CART, FIX_LINE, MONEY, bot_review_comments, head_sha, paged, put_file, read_file,
                           review_run, seeded_pr, summary)

STATE_RE = re.compile(r"<!-- ai-review:state (\{.*?\}) -->", re.S)
DETAILS_RE = re.compile(r"<details>(.*?)</details>", re.S)  # summary-only nits are collapsed (spec: placement table)
CHANGES = "ai-review: changes-requested"


def bot_reviews(number: int) -> list[dict]:
    return [r for r in paged(f"repos/{pg.REPO}/pulls/{number}/reviews") if r["user"]["login"] == pg.BOT]


def test_seeded_bug_gets_inline_comment_and_request_changes_and_a_low_risk_nit_stays_in_the_summary(e2e_target):
    with seeded_pr() as pr:
        number = pr["number"]
        sha1 = head_sha(number)
        review_run(sha1, after="1970-01-01T00:00:00Z")  # the branch and its SHAs are new: any run for it is ours

        body = summary(number)
        state = json.loads(STATE_RE.search(body).group(1))
        assert state["sha"] == sha1 and state["aiwf_sha"] == e2e_target, state
        print(body)

        # Seeded bug: exactly one review from this run, Request changes, on the reviewed commit, verdict label to match.
        reviews = bot_reviews(number)
        print("reviews:", [(r["id"], r["state"], r["commit_id"][:7]) for r in reviews])
        assert len(reviews) == 1, f"expected exactly one bot review after the first run, got {len(reviews)}"
        (rv,) = reviews
        assert rv["state"] == "CHANGES_REQUESTED" and rv["commit_id"] == sha1, (rv["state"], rv["commit_id"])
        assert CHANGES in labels(number), f"verdict label is not {CHANGES!r}: {sorted(labels(number))}"

        # ... carrying an inline comment on the seeded method in cart.py.
        comments = bot_review_comments(number)
        for c in comments:
            print(f"inline: {c['path']}:{c.get('start_line')}-{c.get('line')} review {c['pull_request_review_id']} "
                  f"suggestion={'```suggestion' in c['body']} {c['html_url']}")
        lo, hi = pr["method"]
        on_bug = [c for c in comments if c["pull_request_review_id"] == rv["id"] and c["path"] == CART
                  and c.get("line") and (c.get("start_line") or c["line"]) <= hi and c["line"] >= lo]
        assert on_bug, f"no inline comment of review {rv['id']} on {CART} lines {lo}-{hi} (bug at {pr['bug_line']})"

        # Nit on a low-risk path: listed in the summary's collapsed section, with no inline thread.
        collapsed = "\n".join(DETAILS_RE.findall(body))
        nit_rows = [ln for ln in collapsed.splitlines() if re.match(rf"\| \d+ \| nit \| {re.escape(MONEY)}(:\d+)? \|", ln)]
        assert nit_rows, f"no collapsed nit row for {MONEY} in the summary"
        assert not [c for c in comments if c["path"] == MONEY], f"a finding on low-risk {MONEY} was posted inline"

        # Rerun with findings: fix the bug; the rerun must complete (exercises resolved/still open and the dismissal).
        pushed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 5))
        cart, cart_sha = read_file(CART, pr["branch"])
        sha2 = put_file(CART, pr["branch"], cart.replace(BUG_LINE, FIX_LINE), cart_sha, "fix: percent is out of 100")
        pg.poll(lambda: True if head_sha(number) == sha2 else None, f"PR #{number} head to move to {sha2[:7]}",
                timeout=300)
        review_run(sha2, after=pushed_at)
        body2 = summary(number)
        print(body2)
        print("labels after fix:", sorted(labels(number)))
        final = bot_reviews(number)
        print("reviews after fix:", [(r["id"], r["state"], r["commit_id"][:7]) for r in final])
        assert not [r for r in final if r["state"] == "APPROVED"], "the bot approved the PR"  # never Approve
