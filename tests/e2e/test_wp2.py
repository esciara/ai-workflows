"""WP2 acceptance test. Done when: a dummy PR gets one comment + one label; a new push updates the same comment.

Runs against the playground (AIWF_E2E=1) with the e2e slot (AIWF_E2E_SLOT=1): the PR comes from an `e2e/` branch, so
caller-e2e.yml reviews it with review.yml@e2e-target, which the slot points at the commit under test (ADR-0028/0029).
"""

from __future__ import annotations

import base64
import time

import playground as pg
from review_core import check_review, head_sha, review_run


def test_dummy_pr_gets_one_comment_and_one_label_and_a_push_updates_the_same_comment(e2e_target):
    with pg.throwaway_pr("[e2e] WP2 core review", e2e=True, wp="wp2", slug="core-review") as pr:
        number = pr["number"]
        sha1 = head_sha(number)
        review_run(sha1, after="1970-01-01T00:00:00Z")  # the branch and its SHA are new: any run for it is ours
        first = check_review(number, sha1, e2e_target)

        pushed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 5))
        content = base64.b64encode(f"second push {time.time_ns()}\n".encode()).decode()
        put = pg.api(f"repos/{pg.REPO}/contents/e2e/{pr['branch'].replace('/', '-')}-2.md",
                     "message=test: e2e second push", f"content={content}", f"branch={pr['branch']}", method="PUT")
        sha2 = put["commit"]["sha"]  # the pulls API can serve a stale head right after the PUT
        assert sha2 != sha1, "the push did not create a new commit"
        pg.poll(lambda: True if head_sha(number) == sha2 else None, f"PR #{number} head to move to {sha2[:7]}",
                timeout=300)
        review_run(sha2, after=pushed_at)
        second = check_review(number, sha2, e2e_target)

        assert second["id"] == first["id"], f"push created a new summary comment ({first['id']} -> {second['id']})"
        assert second["updated_at"] > first["updated_at"], "summary comment was not updated after the push"
        assert second["body"] != first["body"], "summary comment body unchanged after the push"
        assert "**Since last run:**" in second["body"], "rerun does not report findings since the last run"
