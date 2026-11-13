"""Offline tests of the caller-vs-template comparison (the network part is tests/e2e/test_callers_match.py)."""

from aiwf.callers_match import compare, jobs_of

TEMPLATE = """
on: push
concurrency:
  group: ai-workflows-${{ github.event.number }}${{ github.run_id }}
  cancel-in-progress: false
permissions: {}
jobs:
  config:
    uses: x/y/.github/workflows/config.yml@abc
    permissions:
      contents: read
  review:
    uses: x/y/.github/workflows/review.yml@abc
    permissions:
      contents: read
      actions: read
"""


def caller(**over):
    t = TEMPLATE
    for old, new in over.items():
        t = t.replace(old.replace("__", " "), new)
    return t


def test_identical_matches():
    assert compare(TEMPLATE, TEMPLATE) == []


def test_missing_job_permission_detected():
    bad = TEMPLATE.replace("      actions: read\n", "")
    problems = compare(TEMPLATE, bad)
    assert len(problems) == 1 and "'review'" in problems[0]


def test_job_absent_in_caller_is_skipped():
    only_config = TEMPLATE.split("  review:")[0]
    assert compare(TEMPLATE, only_config) == []
    assert jobs_of(only_config) == {"config"}


def test_top_level_permissions_differ():
    assert "top-level" in compare(TEMPLATE, TEMPLATE.replace("permissions: {}", "permissions:\n  contents: read"))[0]


def test_cancel_in_progress_differs():
    assert "cancel-in-progress" in compare(TEMPLATE, TEMPLATE.replace("false", "true"))[0]


def test_group_difference_detected_and_prefix_normalised():
    prefixed = TEMPLATE.replace("group: ai-workflows-", "group: ai-workflows-e2e-")
    assert compare(TEMPLATE, prefixed)  # without normalising, it differs
    assert compare(TEMPLATE, prefixed, ("ai-workflows-e2e-", "ai-workflows-")) == []
    missing_part = TEMPLATE.replace("${{ github.run_id }}", "")
    assert "group differs" in compare(TEMPLATE, missing_part)[0]
