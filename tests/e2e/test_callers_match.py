"""The playground's callers stay consistent with templates/caller.yml (read-only, no runs, no e2e slot).

Compared (aiwf.callers_match): top-level `permissions`, `permissions` of every job present in both files, and
`concurrency` (cancel-in-progress and group, after `ai-workflows-e2e-` -> `ai-workflows-` for caller-e2e.yml).
Jobs absent from the playground's ai-workflows.yml (review, triage) are skipped on purpose; caller-e2e.yml must
contain config, review, review-fork-push and triage. Past bugs this guards: a review job without `actions: read`
(startup_failure) and a missing comment-concurrency group.
"""

from __future__ import annotations

import base64

import pytest

import playground as pg
from aiwf.callers_match import compare, jobs_of

TEMPLATE = (pg.ROOT / "templates" / "caller.yml").read_text()
E2E_REQUIRED = {"config", "review", "review-fork-push", "triage"}
# Known, accepted gap: caller-e2e.yml's triage job has contents/pull-requests write for the unreleased WP6 e2e tests,
# the template has read. Drop this when WP6 lands and the template catches up.
ALLOWED_DRIFT = ("job 'triage' permissions differ: caller {'contents': 'write', 'issues': 'write', "
                 "'pull-requests': 'write'}, template {'contents': 'read', 'issues': 'write', 'pull-requests': 'read'}",)


def playground_file(name: str) -> str:
    f = pg.api(f"repos/{pg.REPO}/contents/.github/workflows/{name}")
    return base64.b64decode(f["content"]).decode()


def test_normal_caller_matches_template():
    problems = compare(TEMPLATE, playground_file("ai-workflows.yml"))
    assert not problems, "\n".join(problems)


def test_e2e_caller_matches_template():
    text = playground_file("caller-e2e.yml")
    missing = E2E_REQUIRED - jobs_of(text)
    assert not missing, f"caller-e2e.yml lacks jobs {sorted(missing)}"
    problems = [p for p in compare(TEMPLATE, text, ("ai-workflows-e2e-", "ai-workflows-"))
                if p not in ALLOWED_DRIFT]
    assert not problems, "\n".join(problems)
