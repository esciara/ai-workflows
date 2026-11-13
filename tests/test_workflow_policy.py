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
    "unpinned-own-ref.yml": "unpinned:",
    "job-without-permissions.yml": "permissions:",
    "job-write-all.yml": "permissions:",
    "top-level-write.yml": "permissions:",
    "top-level-missing.yml": "permissions:",
    "top-level-read.yml": "permissions:",
    "agent-github-token.yml": "agent-secrets:",
    "agent-other-secret.yml": "agent-secrets:",
    "agent-write-permissions.yml": "agent-permissions:",
    "agent-read-permissions.yml": "agent-permissions:",
    "agent-marker-token.yml": "agent-secrets:",
    "pull-request-target-head.yml": "pull-request-target:",
    "pull-request-target-checkout.yml": "pull-request-target:",
    "pull-request-target-run-text.yml": "pull-request-target:",
    "pull-request-target-secret.yml": "pull-request-target:",
    "secrets-inherit.yml": "secrets-inherit:",
}


def test_real_workflows_found():
    names = {p.name for p in REAL}
    assert {"ci.yml", "config.yml", "review.yml", "triage.yml", "labels.yml", "caller.yml"} <= names


@pytest.mark.parametrize("path", REAL, ids=lambda p: str(p.relative_to(ROOT)))
def test_real_workflow_passes_policy(path):
    assert policy.check_file(path) == []


@pytest.mark.parametrize("path", sorted((ROOT / ".github" / "actions").glob("*/action.yml")), ids=lambda p: p.parent.name)
def test_composite_actions_pin_their_actions(path):
    assert policy.pin_errors(path.read_text()) == []
    assert policy.pin_errors(path.read_text().replace("@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0", "@v7"))


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


OWN_MAIN = """on: push
permissions: {}
jobs:
  local:
    uses: ./.github/workflows/x.yml
    permissions: {contents: read}
  own:
    uses: esciara/ai-workflows/.github/workflows/config.yml@main
    permissions: {contents: read}
"""


def test_exemptions():
    # Local refs only; own reusable workflows are pinned like any action (ADR-0040, WP14).
    assert policy.is_exempt("./.github/workflows/x.yml")
    assert not policy.is_exempt("esciara/ai-workflows/.github/workflows/review.yml@main")
    assert [e for e in policy.check_text(OWN_MAIN) if "line 8" in e and e.startswith("unpinned:")]
    assert not [e for e in policy.check_text(OWN_MAIN) if "line 5" in e]


def test_own_main_only_in_this_repos_workflows():
    # ADR-0051: this repo's Workflow A calls main's copy; templates and other repos must pin.
    assert policy.check_text(OWN_MAIN, own_main=True) == []
    assert policy.check_text(OWN_MAIN.replace("@main", "@v1"), own_main=True)
    assert policy.check_file(ROOT / ".github" / "workflows" / "ai-review.yml") == []
    assert policy.pin_errors((ROOT / ".github" / "workflows" / "ai-review.yml").read_text())


def test_pull_request_target_without_head_checkout_is_allowed():
    text = """on: [pull_request_target]
permissions: {}
jobs:
  label:
    runs-on: ubuntu-latest
    permissions: {pull-requests: write}
    steps:
      - env:
          PR: ${{ github.event.pull_request.number }}
        run: echo "$PR"
"""
    assert policy.check_text(text) == []


def test_agent_job_with_empty_permissions_passes():
    text = """on: push
permissions: {}
jobs:
  agent:
    runs-on: ubuntu-latest
    permissions: {}
    steps:
      - uses: anthropics/claude-code-action/base-action@0000000000000000000000000000000000000000 # v1
        with:
          claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
"""
    assert policy.check_text(text) == []


# --- fork PRs (ADR-0044): the only code that runs on pull_request_target --------------------------------------------


def _doc(path: str) -> dict:
    return policy.load_workflow((ROOT / path).read_text())


def test_fork_push_workflow_is_api_only():
    doc = _doc(".github/workflows/review-fork-push.yml")
    assert policy.triggers(doc) == {"workflow_call"}
    assert "secrets" not in (doc[True]["workflow_call"] or {}), "declares no secrets"
    for name, job in doc["jobs"].items():
        assert "pull_request_target" in job["if"] and "head.repo.full_name != github.repository" in job["if"], name
        assert job["permissions"] == {"pull-requests": "write"}, name
        for step in job["steps"]:
            assert "uses" not in step, f"{name}: no actions at all, API calls only"
            assert "${{" not in step["run"], f"{name}: PR fields go through env, never into run:"


def test_caller_runs_only_the_fork_push_job_on_pull_request_target():
    doc = _doc("templates/caller.yml")
    assert doc[True]["pull_request_target"] == {"types": ["synchronize"]}
    job = doc["jobs"]["review-fork-push"]
    assert job["permissions"] == {"pull-requests": "write"} and "secrets" not in job and "with" not in job
    assert job["uses"].startswith("esciara/ai-workflows/.github/workflows/review-fork-push.yml@")
    assert "head.repo.full_name != github.repository" in job["if"]
    for name, other in doc["jobs"].items():
        if name in ("config", "review-fork-push"):
            continue
        cond = other["if"]
        assert "pull_request_target" not in cond and "github.event_name ==" in cond, (name, cond)


# --- ai: off (ADR-0045): a gate and a pre-write re-check, no cancel; no job may cancel runs ---------------------------


def test_no_job_has_actions_write():
    for path in REAL:
        doc = policy.load_workflow(path.read_text())
        for name, job in (doc or {}).get("jobs", {}).items():
            perms = job.get("permissions")
            assert not (isinstance(perms, dict) and perms.get("actions") == "write"), f"{path.name}:{name}"


# --- limits (ADR-0050): every agent step has a fixed time limit and a turn limit -------------------------------------


def test_every_agent_step_has_a_time_and_turn_limit():
    seen = 0
    for path in REAL:
        doc = policy.load_workflow(path.read_text())
        for name, job in (doc or {}).get("jobs", {}).items():
            for step in job.get("steps", []):
                if "anthropics/claude-code-action" not in str(step.get("uses", "")):
                    continue
                seen += 1
                where = f"{path.relative_to(ROOT)}:{name}"
                assert "--max-turns " in step["with"]["claude_args"], where
                minutes = step.get("timeout-minutes")
                assert isinstance(minutes, int) and 0 < minutes < job["timeout-minutes"], where  # a step timeout fails
    assert seen >= 4  # extract, classify, review pass, verify
