from pathlib import Path

import pytest

from aiwf import policy

ROOT = Path(__file__).resolve().parents[1]
BAD = Path(__file__).parent / "fixtures" / "policy"
REAL = sorted([*(ROOT / ".github" / "workflows").glob("*.yml"), *(ROOT / "templates").glob("*.yml")])

# fixture file -> rule prefix that must fire on it
EXPECTED = {
    "unpinned-tag.yml": "unpinned:",
    "unpinned-no-version-comment.yml": "unpinned:",
    "job-without-permissions.yml": "permissions:",
    "job-write-all.yml": "permissions:",
    "top-level-write.yml": "permissions:",
    "agent-github-token.yml": "agent-secrets:",
    "agent-other-secret.yml": "agent-secrets:",
    "agent-write-permissions.yml": "agent-permissions:",
    "agent-marker-token.yml": "agent-secrets:",
    "pull-request-target-head.yml": "pull-request-target:",
    "secrets-inherit.yml": "secrets-inherit:",
}


def test_real_workflows_found():
    names = {p.name for p in REAL}
    assert {"ci.yml", "config.yml", "caller.yml"} <= names


@pytest.mark.parametrize("path", REAL, ids=lambda p: str(p.relative_to(ROOT)))
def test_real_workflow_passes_policy(path):
    assert policy.check_file(path) == []


def test_every_fixture_has_an_expectation():
    assert {p.name for p in BAD.glob("*.yml")} == set(EXPECTED)


@pytest.mark.parametrize("name,rule", sorted(EXPECTED.items()))
def test_rule_fires_on_bad_fixture(name, rule):
    errors = policy.check_file(BAD / name)
    assert errors, f"{name}: no violation found"
    assert all(e.startswith(rule) for e in errors), errors


def test_config_example_is_not_a_workflow():
    assert policy.load_workflow((ROOT / "templates" / "ai-workflows.example.yml").read_text()) is None


def test_marker_only_flags_the_marked_job():
    errors = policy.check_file(BAD / "agent-marker-token.yml")
    assert all("'agent'" in e for e in errors)


def test_bare_on_key_parsed_as_true():
    assert policy.triggers({True: {"pull_request_target": None}}) == {"pull_request_target"}
    assert policy.triggers({"on": ["push", "pull_request"]}) == {"push", "pull_request"}


def test_exemptions():
    text = """on: push
jobs:
  local:
    uses: ./.github/workflows/x.yml
    permissions: {contents: read}
  own:
    uses: esciara/ai-workflows/.github/workflows/config.yml@main
    permissions: {contents: read}
"""
    assert policy.check_text(text) == []


def test_pull_request_target_without_head_checkout_is_allowed():
    text = """on: [pull_request_target]
jobs:
  label:
    runs-on: ubuntu-latest
    permissions: {pull-requests: write}
    steps:
      - run: echo ${{ github.event.pull_request.number }}
"""
    assert policy.check_text(text) == []
