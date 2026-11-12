"""WP15 acceptance test. Done when: a reviewed PR's run records exactly one metrics line with the run, the PR and each
agent's turns, duration and tokens (spec: Guardrails, Usage per run).

Runs against the playground (AIWF_E2E=1) with the e2e slot (AIWF_E2E_SLOT=1): the PR comes from an `e2e/` branch, so
caller-e2e.yml reviews it with review.yml@e2e-target, which the slot points at the commit under test (ADR-0028/0029).
The metrics line is read from the run's `ai-workflows-metrics` artifact (`metrics.jsonl`); that location is the
recommended answer to an open WP15 decision, kept in one helper (`playground.metrics_lines`) so the gate can change it.
"""

from __future__ import annotations

import playground as pg
from test_wp2 import check_review, head_sha, review_run


def test_a_review_run_records_exactly_one_metrics_line(e2e_target, tmp_path):
    with pg.throwaway_pr("[e2e] WP15 usage metrics", e2e=True, wp="wp15", slug="metrics") as pr:
        number = pr["number"]
        sha = head_sha(number)
        run = review_run(sha, after="1970-01-01T00:00:00Z")  # the branch and its SHA are new: any run for it is ours
        review = check_review(number, sha, e2e_target)

        lines = pg.metrics_lines(run["id"], tmp_path)
        assert len(lines) == 1, f"run {run['id']}: expected exactly one metrics line, got {len(lines)}"
        pg.check_metrics(lines[0], run, number, sha, e2e_target, review["verdict"])
