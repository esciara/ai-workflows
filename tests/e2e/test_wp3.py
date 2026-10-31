"""WP3 acceptance test. Done when: a seeded-bug PR gets an inline comment and Request changes; a nit on a low-risk path
stays in the summary.

Runs against the playground (AIWF_E2E=1) with the e2e slot (AIWF_E2E_SLOT=1): the PR comes from an `e2e/` branch, so
caller-e2e.yml reviews it with review.yml@e2e-target, which the slot points at the commit under test (ADR-0028/0029).
The playground's e2e config (tests/e2e/config/playground.yml) makes only `.github/**` high risk, so `src/` is low risk.

One PR carries both seeds, committed before the PR is opened so the `opened` event reviews them: a blocking bug in a
new `Cart.apply_bulk_discount` (the percent is not divided by 100) and typos in a docstring of `money.py` (a nit).
A second push then fixes the bug, which reruns the review on a PR with findings (the last run's findings marked
resolved or still open, the Request changes review dismissed); that rerun must complete, its outcome is only printed.
"""

from __future__ import annotations

import base64
import contextlib
import json
import re
import time
from typing import Any, Iterator

import playground as pg

E2E_WORKFLOW = "AI workflows (e2e)"  # the playground's caller-e2e.yml
MARKER = "<!-- ai-review:summary v1 -->"  # the spec's hidden marker (review comment template)
STATE_RE = re.compile(r"<!-- ai-review:state (\{.*?\}) -->", re.S)
DETAILS_RE = re.compile(r"<details>(.*?)</details>", re.S)  # summary-only nits are collapsed (spec: placement table)
CHANGES = "ai-review: changes-requested"
REVIEW_TIMEOUT = 1800  # CI wait + 4 passes + verify, on a cold runner

CART = "src/minicart/cart.py"
MONEY = "src/minicart/money.py"
BUG_LINE = "        self.discount = round_money(self.subtotal() * to_decimal(percent))\n"
FIX_LINE = "        self.discount = round_money(self.subtotal() * to_decimal(percent) / 100)\n"
METHOD = (
    "\n"
    "    def apply_bulk_discount(self, min_items: int, percent: Decimal | str) -> Decimal:\n"
    '        """Take `percent` % off the subtotal when the cart holds at least `min_items` items; return the discount."""\n'
    "        if self.item_count() < min_items:\n"
    '            return Decimal("0")\n'
    + BUG_LINE +
    "        return self.discount\n"
)
DOC_OLD = '    """Convert a number to Decimal without float artefacts."""\n'
DOC_NIT = '    """Convert a numbr to Decimal without flaot artefacts."""\n'


def read_file(path: str, ref: str) -> tuple[str, str]:
    data = pg.api(f"repos/{pg.REPO}/contents/{path}?ref={ref}")
    return base64.b64decode(data["content"]).decode(), data["sha"]


def put_file(path: str, branch: str, text: str, blob_sha: str, message: str) -> str:
    """Commit `text` to `path` on `branch` as the agent App; returns the new commit SHA."""
    out = pg.api(f"repos/{pg.REPO}/contents/{path}", f"message={message}", f"branch={branch}", f"sha={blob_sha}",
                 f"content={base64.b64encode(text.encode()).decode()}", method="PUT")
    return out["commit"]["sha"]


@contextlib.contextmanager
def seeded_pr() -> Iterator[dict[str, Any]]:
    """A test-fixture PR whose first commit already holds both seeds; branch deleted, PR closed on exit."""
    branch = pg.pr_branch(e2e=True, wp="wp3", slug="placement")
    base = pg.api(f"repos/{pg.REPO}")["default_branch"]
    sha = pg.api(f"repos/{pg.REPO}/git/ref/heads/{base}")["object"]["sha"]
    pg.api(f"repos/{pg.REPO}/git/refs", f"ref=refs/heads/{branch}", f"sha={sha}", method="POST")
    pr = None
    try:
        cart, cart_sha = read_file(CART, branch)
        assert cart.endswith('        self.discount = Decimal("0")\n'), "playground cart.py changed; update the seed"
        cart += METHOD
        put_file(CART, branch, cart, cart_sha, "feat: bulk discount (e2e seeded bug)")
        money, money_sha = read_file(MONEY, branch)
        assert DOC_OLD in money, "playground money.py changed; update the seed"
        put_file(MONEY, branch, money.replace(DOC_OLD, DOC_NIT), money_sha, "docs: reword to_decimal (e2e seeded nit)")
        # No PR exists while the seeds are pushed, so only the PR's `opened` event starts a review.
        title = f"[e2e] WP3 add a bulk discount to Cart ({branch})"
        pr = pg.api(f"repos/{pg.REPO}/pulls", f"title={title}", f"head={branch}", f"base={base}",
                    "body=Adds `Cart.apply_bulk_discount`. Throwaway e2e PR from esciara/ai-workflows tests "
                    "(seeded bug and nit); closed by its teardown.", method="POST")
        pg.api(f"repos/{pg.REPO}/issues/{pr['number']}/labels", *[f"labels[]={lb}" for lb in pg._labels(True)],
               method="POST")
        bug_line = cart.splitlines().index(BUG_LINE.rstrip("\n")) + 1
        start = cart.splitlines().index(METHOD.splitlines()[1]) + 1
        yield {"number": pr["number"], "branch": branch, "bug_line": bug_line, "method": (start, start + 5),
               "cart": cart}
    finally:
        pg.api(f"repos/{pg.REPO}/git/refs/heads/{branch}", method="DELETE")
        if pr and pg.api(f"repos/{pg.REPO}/pulls/{pr['number']}")["state"] == "open":
            pg.api(f"repos/{pg.REPO}/pulls/{pr['number']}", "state=closed", method="PATCH")


def review_run(sha: str, after: str) -> dict:
    """The completed pull_request run of the e2e caller for head `sha`, created at or after `after`; must succeed."""

    def find() -> int | None:
        runs = pg.api(f"repos/{pg.REPO}/actions/runs?event=pull_request&head_sha={sha}&per_page=50")["workflow_runs"]
        hits = [r for r in runs if r["name"] == E2E_WORKFLOW and r["created_at"] >= after]
        return min(hits, key=lambda r: (r["created_at"], r["id"]))["id"] if hits else None

    run_id = pg.poll(find, f"the {E2E_WORKFLOW} pull_request run for {sha[:7]}", timeout=REVIEW_TIMEOUT)

    def done() -> dict | None:
        run = pg.api(f"repos/{pg.REPO}/actions/runs/{run_id}")
        return run if run["status"] == "completed" else None

    run = pg.poll(done, f"run {run_id} to complete", timeout=REVIEW_TIMEOUT)
    jobs = pg.jobs(run_id)
    print(f"review of {sha[:7]}: run {run_id} {run['html_url']} -> {run['conclusion']}, jobs {jobs}")
    assert run["conclusion"] == "success", jobs
    assert jobs.get("review / publish") == "success", jobs
    return run


def paged(path: str) -> list[dict]:
    out = pg.gh(["api", "--paginate", f"{path}?per_page=100", "--jq", ".[]"])
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def bot_reviews(number: int) -> list[dict]:
    return [r for r in paged(f"repos/{pg.REPO}/pulls/{number}/reviews") if r["user"]["login"] == pg.BOT]


def bot_review_comments(number: int) -> list[dict]:
    return [c for c in paged(f"repos/{pg.REPO}/pulls/{number}/comments") if c["user"]["login"] == pg.BOT]


def summary(number: int) -> str:
    own = [c for c in paged(f"repos/{pg.REPO}/issues/{number}/comments")
           if c["user"]["login"] == pg.BOT and (c["body"] or "").startswith(MARKER)]
    assert len(own) == 1, f"expected exactly one summary comment on #{number}, got {[c['html_url'] for c in own]}"
    return own[0]["body"]


def labels(number: int) -> set[str]:
    return {lb["name"] for lb in pg.api(f"repos/{pg.REPO}/issues/{number}/labels?per_page=100")}


def head_sha(number: int) -> str:
    return pg.api(f"repos/{pg.REPO}/pulls/{number}")["head"]["sha"]


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
