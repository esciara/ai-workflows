"""Seeded-PR e2e helpers shared by test_wp3 and test_wp18 (moved out of test_wp3.py)."""

from __future__ import annotations

import base64
import contextlib
import json
from typing import Any, Iterator

import playground as pg

E2E_WORKFLOW = pg.E2E_WORKFLOW  # the held slot's playground caller, caller-e2e-<n>.yml (ADR-0056)
MARKER = "<!-- ai-review:summary v1 -->"  # the spec's hidden marker (review comment template)
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


def bot_review_comments(number: int) -> list[dict]:
    return [c for c in paged(f"repos/{pg.REPO}/pulls/{number}/comments") if c["user"]["login"] == pg.BOT]


def summary(number: int) -> str:
    own = [c for c in paged(f"repos/{pg.REPO}/issues/{number}/comments")
           if c["user"]["login"] == pg.BOT and (c["body"] or "").startswith(MARKER)]
    assert len(own) == 1, f"expected exactly one summary comment on #{number}, got {[c['html_url'] for c in own]}"
    return own[0]["body"]


def head_sha(number: int) -> str:
    return pg.api(f"repos/{pg.REPO}/pulls/{number}")["head"]["sha"]
