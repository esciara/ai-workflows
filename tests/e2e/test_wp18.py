"""WP18 acceptance test (ADR-0057 points 2-3). Done when: on a seeded-bug PR a fixing push gets A's reply and the thread
resolved, and the summary says 0 threads open; a non-fixing push leaves the thread open (and no reply).

Runs against the playground (AIWF_E2E=1) with the e2e slot (AIWF_E2E_SLOT=any|1|2|3): the PR comes from an `e2e/` branch,
so the e2e caller reviews it with review.yml@e2e-target, which the slot points at the commit under test (ADR-0028/0029).
The seeded PR is the WP3 one (a blocking bug in `Cart.apply_bulk_discount`, committed before the PR is opened).

One scenario, three runs on one PR:

1. First run: the bug gets an inline thread opened by the bot, unresolved; the summary says 1 thread open.
2. A push that does not touch the bug (an unrelated new file): the thread stays unresolved, the bot adds no reply to it,
   the summary still says 1 thread open.
3. A push that fixes the bug: the bot replies in its own thread with `resolved in <short sha>: <reason>`, the thread is
   resolved, and the summary says 0 threads open.

Assumption this test verifies at build: the GraphQL mutation `resolveReviewThread` works with the publish job's
`GITHUB_TOKEN` (`pull-requests: write`), so the bot can resolve its own thread. If it does not, the build stops and
the maintainer decides (the ADR assumed it works). The build also settles how A matches a finding to its thread
(the thread it opened for that finding, by the first inline comment's id); the test only checks the outcome.

Expected to fail until WP18 is built.
"""

from __future__ import annotations

import base64
import json
import re
import time

import playground as pg
from test_wp3 import (BUG_LINE, CART, FIX_LINE, bot_review_comments, head_sha, put_file, read_file,
                      review_run, seeded_pr, summary)

THREADS_OPEN_RE = re.compile(r"(\d+) threads? open")
RESOLVED_RE = re.compile(r"^resolved in ([0-9a-f]{7,40}): \S")
THREADS_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        nodes { id isResolved path comments(first: 50) { nodes { databaseId body author { login } } } }
      }
    }
  }
}
"""


def threads(number: int) -> list[dict]:
    """All review threads of the PR (read-only GraphQL), each with its comments in order."""
    owner, name = pg.REPO.split("/")
    out = pg.gh(["api", "graphql", "-f", f"query={THREADS_QUERY}", "-F", f"owner={owner}", "-F", f"name={name}",
                 "-F", f"number={number}"])
    nodes = json.loads(out)["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    return [{"id": t["id"], "resolved": t["isResolved"], "path": t["path"],
             "comments": [{"id": c["databaseId"], "body": c["body"], "author": (c["author"] or {}).get("login")}
                          for c in t["comments"]["nodes"]]} for t in nodes]


def bug_thread(number: int, bug_range: tuple[int, int]) -> dict:
    """The thread the bot opened on the seeded method in cart.py (its first comment is the bot's)."""
    lo, hi = bug_range
    inline = {c["id"] for c in bot_review_comments(number)
              if c["path"] == CART and c.get("line") and (c.get("start_line") or c["line"]) <= hi and c["line"] >= lo}
    assert inline, f"no bot inline comment on {CART} lines {lo}-{hi}"
    hits = [t for t in threads(number) if t["comments"] and t["comments"][0]["id"] in inline]
    assert hits, f"no bot thread on the seeded bug at {CART} lines {lo}-{hi}"
    bug = [t for t in hits if "100" in t["comments"][0]["body"]]
    assert bug, f"no bot thread mentions the missing `/ 100`: {[t['comments'][0]['body'][:80] for t in hits]}"
    assert bug[0]["comments"][0]["author"] == pg.BOT.removesuffix("[bot]"), bug[0]["comments"][0]["author"]
    return bug[0]


def threads_open(number: int) -> int:
    m = THREADS_OPEN_RE.search(summary(number))
    assert m, "the summary's 'Since last run' line has no 'N threads open'"
    return int(m.group(1))


def push(number: int, branch: str, path: str, text: str, blob_sha: str | None, message: str) -> tuple[str, str]:
    """Commit to the PR branch; returns (sha, timestamp to look for the rerun from)."""
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 5))
    if blob_sha is None:  # new file
        out = pg.api(f"repos/{pg.REPO}/contents/{path}", f"message={message}", f"branch={branch}",
                     f"content={base64.b64encode(text.encode()).decode()}", method="PUT")
        sha = out["commit"]["sha"]
    else:
        sha = put_file(path, branch, text, blob_sha, message)
    pg.poll(lambda: True if head_sha(number) == sha else None, f"PR #{number} head to move to {sha[:7]}", timeout=300)
    return sha, at


def test_a_fixing_push_gets_a_reply_and_the_thread_resolved_a_non_fixing_push_leaves_it_open(e2e_target):
    with seeded_pr() as pr:
        number = pr["number"]
        sha1 = head_sha(number)
        review_run(sha1, after="1970-01-01T00:00:00Z")  # the branch and its SHAs are new: any run for it is ours

        # 1. The seeded bug has a bot thread, unresolved, and the summary counts it.
        t1 = bug_thread(number, pr["method"])
        assert not t1["resolved"], "the bug thread is already resolved after the first run"
        assert len(t1["comments"]) == 1, f"unexpected replies in the new thread: {t1['comments']}"
        open1 = [t for t in threads(number) if not t["resolved"]]
        pre_fix = {t["id"] for t in open1}  # every one of these must be closed by the fixing push
        assert threads_open(number) == len(open1), (threads_open(number), len(open1))
        print(f"first run: thread {t1['id']} open, summary says {threads_open(number)} threads open")

        # 2. Non-fixing push (an unrelated new file): the thread stays open, with no reply from the bot.
        sha2, at = push(number, pr["branch"], f"e2e/{pr['branch'].replace('/', '-')}-unrelated.md",
                        f"unrelated {time.time_ns()}\n", None, "docs: unrelated note (e2e non-fixing push)")
        review_run(sha2, after=at)
        t2 = next(t for t in threads(number) if t["id"] == t1["id"])
        assert not t2["resolved"], "a push that does not fix the bug resolved its thread"
        assert len(t2["comments"]) == 1, f"the bot replied in a thread whose finding is still open: {t2['comments']}"
        assert threads_open(number) >= 1, "the summary says 0 threads open while the bug thread is open"
        print(f"non-fixing push {sha2[:7]}: thread still open, no reply, summary {threads_open(number)} open")

        # 3. Fixing push: the bot replies in its own thread, resolves it; the summary says 0 threads open.
        cart, cart_sha = read_file(CART, pr["branch"])
        assert BUG_LINE in cart, "the seeded bug line is gone before the fixing push"
        sha3, at = push(number, pr["branch"], CART, cart.replace(BUG_LINE, FIX_LINE), cart_sha,
                        "fix: percent is out of 100")
        review_run(sha3, after=at)
        t3 = next(t for t in threads(number) if t["id"] == t1["id"])
        print(f"fixing push {sha3[:7]}: thread comments {[(c['author'], c['body'][:80]) for c in t3['comments']]}")
        assert t3["resolved"], "the thread of the fixed bug is not resolved (resolveReviewThread with GITHUB_TOKEN?)"
        replies = t3["comments"][1:]
        assert len(replies) == 1 and replies[0]["author"] == t3["comments"][0]["author"], t3["comments"]
        m = RESOLVED_RE.match(replies[0]["body"])
        assert m, f"reply is not 'resolved in <short sha>: <reason>': {replies[0]['body'][:200]!r}"
        assert sha3.startswith(m.group(1)), f"reply names {m.group(1)}, the fixing commit is {sha3[:7]}"
        after = threads(number)
        not_closed = [t["id"] for t in after if t["id"] in pre_fix and not t["resolved"]]
        assert not not_closed, f"pre-fix bot threads not resolved by the fixing push: {not_closed}"
        left = [t for t in after if not t["resolved"]]
        for t in left:
            print(f"unresolved after fix: {t['id']} {t['path']} {[(c['author'], c['body'][:80]) for c in t['comments']]}")
        assert threads_open(number) == len(left), (threads_open(number), len(left))
        assert not left, f"{len(left)} unresolved threads remain on the fixed PR (new findings, or a missed resolve)"
        assert threads_open(number) == 0, f"the summary does not say 0 threads open: {summary(number)}"
