import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

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
    "agent-local-action-token.yml": "agent-secrets:",
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
    assert policy.pin_errors(re.sub(r"@[0-9a-f]{40}", "@v7", path.read_text(), count=1))


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
    # Sole exception (ADR-0059): the `verdict` job reruns earlier failed `verdict` jobs; it never cancels a run.
    for path in REAL:
        doc = policy.load_workflow(path.read_text())
        for name, job in (doc or {}).get("jobs", {}).items():
            perms = job.get("permissions")
            if isinstance(perms, dict) and perms.get("actions") == "write":
                assert (path.name, name) == ("ai-review.yml", "verdict"), f"{path.name}:{name}"
                allowed = (r'repos/\$REPO/statuses/\$HEAD_SHA', r'repos/\$REPO/actions/jobs/\$job/rerun')
                calls = 0
                for step in job.get("steps", []):
                    run = step.get("run", "")
                    assert not re.search(r"gh\s+run\b|--method\b|workflow_dispatch|/cancel", run), "no other write path"
                    for method, endpoint in re.findall(r'-X\s+(\w+)\s+"([^"]+)"', run):
                        calls += 1
                        assert method == "POST" and any(re.fullmatch(a, endpoint) for a in allowed), (method, endpoint)
                    assert len(re.findall(r"-X\b", run)) == len(re.findall(r'-X\s+\w+\s+"', run)), "unparsed -X call"
                assert calls >= 1


# --- limits (ADR-0050): every agent step has a fixed time limit and a turn limit -------------------------------------


AGENT_ACTION_YML = ROOT / ".github" / "actions" / "aiwf-agent" / "action.yml"
AGENT_USES = "./.ai-workflows/.github/actions/aiwf-agent"


def _args_run() -> str:
    """The aiwf-agent step that builds claude_args, found by its id."""
    return next(s["run"] for s in yaml.safe_load(AGENT_ACTION_YML.read_text())["runs"]["steps"] if s.get("id") == "args")


def _agent_steps():
    for path in REAL:
        doc = policy.load_workflow(path.read_text())
        for name, job in (doc or {}).get("jobs", {}).items():
            for step in job.get("steps", []):
                yield f"{path.relative_to(ROOT)}:{name}", job, step


def test_every_agent_step_has_a_time_and_turn_limit():
    seen = 0
    for where, job, step in _agent_steps():
        if str(step.get("uses", "")) != AGENT_USES:
            continue
        seen += 1
        turns = step["with"]["max-turns"]
        assert isinstance(turns, int) and turns > 0, where
        minutes = step.get("timeout-minutes")
        assert isinstance(minutes, int) and 0 < minutes < job["timeout-minutes"], where  # a step timeout fails
    assert seen >= 4  # extract, classify, review pass, verify
    assert yaml.safe_load(AGENT_ACTION_YML.read_text())["inputs"]["max-turns"]["required"] is True
    assert "--max-turns $MAX_TURNS" in _args_run()


# --- one shared agent action (CP8): agents run claude-code-action only through aiwf-agent ----------------------------


def test_agents_run_claude_code_action_only_through_the_shared_action():
    for where, _job, step in _agent_steps():
        assert policy.AGENT_ACTION not in str(step.get("uses", "")), f"{where}: use {AGENT_USES}"


def test_shared_agent_action_reads_no_github_token_and_no_secret():
    text = AGENT_ACTION_YML.read_text()
    assert not policy.TOKEN_RE.search(text) and not policy.SECRET_RE.search(text)
    steps = yaml.safe_load(text)["runs"]["steps"]
    agent = [s for s in steps if str(s.get("uses", "")).startswith(policy.AGENT_ACTION + "/base-action@")]
    assert len(agent) == 1 and set(agent[0]["with"]) == {"claude_code_oauth_token", "prompt_file", "claude_args"}


@pytest.mark.parametrize("path", sorted((ROOT / "schema").glob("*.json")), ids=lambda p: p.name)
def test_schemas_have_no_single_quote(path):
    # The schema goes to --json-schema single-quoted inside claude_args (shell-quote split): a ' would end the quote.
    assert "'" not in path.read_text()


@pytest.mark.parametrize("schema,model", [("{\"description\": \"it's\"}", ""), ("{}", "x' --tools 'Bash"), ("{}", "a\nb")])
def test_shared_agent_action_refuses_quotes(tmp_path, schema, model):
    (tmp_path / "s.json").write_text(schema)
    out = tmp_path / "out"
    run = _args_run()
    env = {**os.environ, "SCHEMA_FILE": str(tmp_path / "s.json"), "MAX_TURNS": "3", "MODEL": model, "GITHUB_OUTPUT": str(out)}
    assert subprocess.run(["bash", "-c", run], env=env, capture_output=True).returncode == 1
    assert not out.exists()


def test_shared_agent_action_builds_the_claude_args(tmp_path):
    (tmp_path / "s.json").write_text(json.dumps({"$schema": "x", "type": "object", "description": "a $b"}))
    out = tmp_path / "out"
    run = _args_run()
    for model, tail in (("", ""), ("claude-sonnet-4-5", " --model 'claude-sonnet-4-5'")):
        env = {**os.environ, "SCHEMA_FILE": str(tmp_path / "s.json"), "MAX_TURNS": "3", "MODEL": model, "GITHUB_OUTPUT": str(out)}
        subprocess.run(["bash", "-c", run], env=env, check=True)
        want = """claude_args=--max-turns 3 --tools StructuredOutput --json-schema '{"type":"object","description":"a $b"}'"""
        assert out.read_text().splitlines()[-1] == want + tail


# --- verdict check (ADR-0053, states ADR-0055): check-run plus a `verdict` commit status of the same name -----------


def test_verdict_job_is_read_only_and_reruns_on_reviews():
    doc = _doc(".github/workflows/ai-review.yml")
    assert doc[True]["pull_request_review"] == {"types": ["submitted", "dismissed"]}
    assert "ready_for_review" in doc[True]["pull_request"]["types"], "a draft made ready gets its verdict"
    job = doc["jobs"]["verdict"]
    assert job["permissions"] == {"pull-requests": "read", "statuses": "write", "actions": "write"}  # ADR-0059
    assert "pull_request_review" in job["if"] and "always()" in job["if"]
    assert "!github.event.pull_request.draft" in job["if"], "drafts are skipped (ADR-0055)"
    assert "review.state" not in job["if"], "a skipped required check counts as passing: filter review states in the step"
    assert "secrets" not in job and all("uses" not in s for s in job["steps"])
    assert "pull_request_review" in doc["jobs"]["config"]["if"], "no config/review job on review events"
    assert "pull_request'" in doc["jobs"]["review"]["if"] and "pull_request_review" not in doc["jobs"]["review"]["if"]
    for step in job["steps"]:
        assert "${{" not in step["run"], "event fields go through env, never into run:"
        assert "approve" not in step["run"].lower().replace("approved", ""), "verdict never approves"


def test_only_the_verdict_job_writes_statuses():
    for path in REAL:
        for name, job in (policy.load_workflow(path.read_text()) or {}).get("jobs", {}).items():
            perms = job.get("permissions")
            if isinstance(perms, dict) and perms.get("statuses") == "write":
                assert (path.name, name) == ("ai-review.yml", "verdict"), f"{path.name}:{name}"


def _st(state, description, creator="github-actions[bot]"):
    return {"context": "verdict", "state": state, "description": description, "creator": {"login": creator}}


def _run_verdict(tmp_path, event, review, reviews, labels, state="", current="none", author="app[bot]", statuses=None, post_rc=0):
    """Runs the verdict step with a fake gh. `statuses` (newest first) or `current` fill the head commit's statuses."""
    step = _doc(".github/workflows/ai-review.yml")["jobs"]["verdict"]["steps"][0]
    fake = tmp_path / "gh"
    posted = tmp_path / "posted"
    posted.unlink(missing_ok=True)
    if statuses is None:
        statuses = [] if current == "none" else [_st(current, "x")]
    statuses = [{"context": "other", "state": "failure", "description": "", "creator": {"login": "x"}}, *statuses]
    data = {"statuses": statuses, "reviews": reviews, "labels": [{"name": x} for x in labels]}
    for name, value in data.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
    fake.write_text(
        "#!/bin/bash\n"
        'q=.; prev=; for a in "$@"; do [ "$prev" = --jq ] && q=$a; prev=$a; done\n'
        'case "$*" in\n'
        f"  *-X\\ POST*statuses*) printf '%s\\n' \"$*\" >> {posted}; exit {post_rc} ;;\n"
        f"  *commits/*/statuses*) f={tmp_path}/statuses.json ;;\n"
        f"  *pulls/*/reviews*) f={tmp_path}/reviews.json ;;\n"
        f"  *issues/*/labels*) f={tmp_path}/labels.json ;;\n"
        "esac\n"
        'jq -r "$q" "$f"\n'
    )
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "REPO": "o/r", "PR": "1", "AUTHOR": author,
           "HEAD_SHA": "new4567890", "EVENT": event, "REVIEW": review, "REVIEW_STATE": state,
           "GITHUB_STEP_SUMMARY": str(tmp_path / "summary")}
    run = subprocess.run(["bash", "-e", "-c", step["run"]], env=env, capture_output=True, text=True)
    _run_verdict.stdout = run.stdout
    return run.returncode, posted.read_text() if posted.exists() else ""


def _description(posted):
    return posted.split("description=", 1)[1].rstrip("\n")


def _rv(state="APPROVED", sha="new4567890", user="m", assoc="OWNER", body=""):
    return {"state": state, "commit_id": sha, "user": {"login": user}, "author_association": assoc, "body": body}


AI = _rv("COMMENTED", user="github-actions[bot]", assoc="NONE", body="Summary\n\n**Verdict:** risk tier high; no linked issue.\n")
PR, RV = "pull_request", "pull_request_review"


@pytest.mark.parametrize(
    "event, review, reviews, labels, state, status",
    [
        (PR, "success", [], ["ai-review: merge"], "", "success"),
        (PR, "success", [AI], ["ai-review: human-review"], "", "pending"),
        (PR, "success", [AI], ["ai-review: changes-requested"], "", "failure"),
        (PR, "success", [], [], "", "pending"),  # no label
        (PR, "failure", [], ["ai-review: merge"], "", "failure"),  # review errored
        (PR, "skipped", [], [], "", "pending"),  # review did not run
        (PR, "skipped", [_rv()], ["ai-review: human-review"], "", "success"),  # approval alone
        (RV, "skipped", [_rv()], ["ai-review: changes-requested"], "approved", "success"),
        (RV, "skipped", [], ["ai-review: merge"], "dismissed", "pending"),  # label may be from an older head
        (RV, "skipped", [_rv(sha="old")], ["ai-review: human-review"], "approved", "pending"),  # new push
        (RV, "skipped", [_rv(), _rv("CHANGES_REQUESTED")], [], "approved", "pending"),  # later review wins
        (RV, "skipped", [_rv(), _rv("COMMENTED")], [], "approved", "success"),
        (RV, "skipped", [_rv(assoc="CONTRIBUTOR")], [], "approved", "pending"),  # not the owner
        (RV, "skipped", [_rv("DISMISSED")], [], "dismissed", "pending"),
    ],
)
def test_verdict_rule(tmp_path, event, review, reviews, labels, state, status):
    if not shutil.which("jq"):
        pytest.skip("jq missing")
    rc, posted = _run_verdict(tmp_path, event, review, reviews, labels, state)
    assert f"state={status}" in posted and "context=verdict" in posted and posted.count("statuses") == 1
    assert (rc == 0) is (status == "success"), "waiting stays red until ADR-0055 Decision 2 is verified"


def test_verdict_waiting_names_the_commit_and_the_reason(tmp_path):
    if not shutil.which("jq"):
        pytest.skip("jq missing")
    rc, posted = _run_verdict(tmp_path, PR, "success", [AI], ["ai-review: human-review"])
    assert rc == 1 and "waiting for maintainer approval of new4567 (risk tier high; no linked issue)" in posted
    rc, posted = _run_verdict(tmp_path, PR, "failure", [], [], author="dependabot[bot]")
    assert rc == 1 and "state=pending" in posted and "Dependabot" in posted


@pytest.mark.parametrize("current", ["success", "pending", "failure", "none"])
@pytest.mark.parametrize("state", ["commented"])
def test_verdict_other_review_states_keep_the_answer(tmp_path, state, current):
    # Green with no new status (ADR-0059): every run is its own check suite and a red suite still blocks the PR.
    if not shutil.which("jq"):
        pytest.skip("jq missing")
    rc, posted = _run_verdict(tmp_path, RV, "skipped", [_rv()], [], state, current)
    assert posted == "", "no new status"
    assert rc == 0


APPROVAL = _st("success", "approved on new4567 by m")
RED = _st("failure", "changes requested on new4567: risk tier high")
WAIT = _st("pending", "waiting for maintainer approval of new4567 (risk tier high)")
MERGE = _st("success", "ai-review: merge on new4567")


@pytest.mark.parametrize(
    "state, reviews, statuses, status, text",
    [
        ("dismissed", [_rv("DISMISSED")], [APPROVAL, RED], "failure", RED["description"]),  # failure stays red
        ("approved", [_rv(assoc="CONTRIBUTOR")], [RED], "failure", RED["description"]),
        ("changes_requested", [_rv(), _rv("CHANGES_REQUESTED")], [APPROVAL, WAIT], "pending", WAIT["description"]),
        ("changes_requested", [_rv(), _rv("CHANGES_REQUESTED")], [APPROVAL, RED], "failure", RED["description"]),
        ("dismissed", [_rv("DISMISSED")], [APPROVAL, MERGE], "success", MERGE["description"]),
        ("dismissed", [], [], "pending", "waiting for maintainer approval of new4567 (no owner approval)"),
        ("dismissed", [], [_st("failure", "spoof", creator="eve")], "pending",
         "waiting for maintainer approval of new4567 (no owner approval)"),  # only this workflow's statuses count
    ],
)
def test_verdict_review_event_restores_the_ai_verdict(tmp_path, state, reviews, statuses, status, text):
    if not shutil.which("jq"):
        pytest.skip("jq missing")
    rc, posted = _run_verdict(tmp_path, RV, "skipped", reviews, [], state, statuses=statuses)
    assert f"state={status}" in posted and _description(posted) == text
    assert (rc == 0) is (status == "success"), "never green with no approval"


def test_verdict_failure_texts_and_annotation(tmp_path):
    if not shutil.which("jq"):
        pytest.skip("jq missing")
    rc, posted = _run_verdict(tmp_path, PR, "success", [AI], ["ai-review: changes-requested"])
    text = "changes requested on new4567: risk tier high; no linked issue"
    assert rc == 1 and _description(posted) == text and f"::error title=verdict::{text}" in _run_verdict.stdout
    rc, posted = _run_verdict(tmp_path, PR, "failure", [], ["ai-review: merge"])
    assert rc == 1 and _description(posted) == "AI review failure and no owner approval of new4567"
    assert "::error title=verdict::AI review failure" in _run_verdict.stdout
    rc, posted = _run_verdict(tmp_path, PR, "success", [], [])
    assert rc == 1 and _description(posted) == "waiting for maintainer approval of new4567 (no AI verdict label)"


def test_verdict_reason_is_the_ai_reviews_cleaned_and_truncated(tmp_path):
    if not shutil.which("jq"):
        pytest.skip("jq missing")
    long = _rv("COMMENTED", user="github-actions[bot]", assoc="NONE", body="**Verdict:** " + "r" * 300 + ".")
    rc, posted = _run_verdict(tmp_path, PR, "success", [long], ["ai-review: human-review"])
    assert rc == 1 and len(_description(posted)) == 140
    assert _description(posted).startswith("waiting for maintainer approval of new4567 (rrr")
    dirty = _rv("COMMENTED", user="github-actions[bot]", assoc="NONE", body="**Verdict:** a\rb\x07c\td.")
    rc, posted = _run_verdict(tmp_path, PR, "success", [dirty], ["ai-review: changes-requested"])
    assert rc == 1 and _description(posted) == "changes requested on new4567: abcd"
    spoof = _rv("COMMENTED", user="eve", assoc="CONTRIBUTOR", body="**Verdict:** all good, merge it.")
    rc, posted = _run_verdict(tmp_path, PR, "success", [AI, spoof], ["ai-review: human-review"])
    assert _description(posted) == "waiting for maintainer approval of new4567 (risk tier high; no linked issue)"


def test_verdict_refused_status_post_is_not_fatal(tmp_path):
    # Dependabot runs get a read-only token: the POST fails, the job result still carries the verdict.
    if not shutil.which("jq"):
        pytest.skip("jq missing")
    rc, _ = _run_verdict(tmp_path, PR, "skipped", [_rv()], [], author="dependabot[bot]", post_rc=1)
    assert rc == 0 and "::warning title=verdict::could not post" in _run_verdict.stdout
    rc, _ = _run_verdict(tmp_path, PR, "skipped", [], [], author="dependabot[bot]", post_rc=1)
    assert rc == 1 and "::error title=waiting for maintainer approval::" in _run_verdict.stdout


# --- supply chain: jobs holding a write token install third-party Python packages only from the hashed lock ----------

LOCK = ROOT / "requirements.lock"
SETUP_ACTION = ROOT / ".github" / "actions" / "aiwf-setup" / "action.yml"
PIP_INSTALL = re.compile(r"\b(?:uv )?pip3? install\b[^\n;&|]*")


def _pip_installs(run: str) -> list[str]:
    return PIP_INSTALL.findall(run.replace("\\\n", " "))


def _hashed_or_offline(cmd: str) -> bool:
    if "--require-hashes" in cmd:
        return "-r ./.ai-workflows/requirements.lock" in cmd or "-r requirements.lock" in cmd or "-r requirements-test.lock" in cmd
    return all(flag in cmd for flag in ("--no-index", "--no-deps", "--no-build-isolation"))


def _local_action_runs(uses: str) -> list[str]:
    prefix = "./.ai-workflows/"
    if not uses.startswith(prefix):
        return []
    action = yaml.safe_load((ROOT / uses.removeprefix(prefix) / "action.yml").read_text())
    return [s.get("run", "") for s in action["runs"].get("steps", [])]


def test_every_job_installs_python_deps_only_from_the_hashed_lock():
    # Every job, whatever its permissions: write tokens can come from the top-level block or a calling workflow.
    seen: dict[str, int] = {}
    for path in REAL:
        doc = policy.load_workflow(path.read_text())
        for name, job in (doc or {}).get("jobs", {}).items():
            for step in job.get("steps", []):
                runs = [step.get("run", ""), *_local_action_runs(str(step.get("uses", "")))]
                for cmd in (c for run in runs for c in _pip_installs(run)):
                    key = f"{path.name}:{name}"
                    seen[key] = seen.get(key, 0) + 1
                    assert _hashed_or_offline(cmd), f"{path.relative_to(ROOT)}:{name}: {cmd}"
    # the write-token jobs were really scanned, each with the locked deps then aiwf itself offline
    for key in ("ci.yml:test", "review.yml:publish", "triage.yml:publish", "labels.yml:sync", "notify.yml:send"):
        assert seen.get(key) == 2, (key, seen)


def test_ci_test_job_installs_only_from_the_hashed_test_lock():
    steps = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())["jobs"]["test"]["steps"]
    cmds = [c for s in steps for c in _pip_installs(s.get("run", ""))]
    assert len(cmds) == 2 and all(_hashed_or_offline(c) for c in cmds), cmds
    assert any("-r requirements-test.lock" in c and "--only-binary :all:" in c for c in cmds), cmds


def test_setup_action_installs_from_the_lock_and_caches_on_it():
    text = SETUP_ACTION.read_text()
    cmds = [c for s in yaml.safe_load(text)["runs"]["steps"] for c in _pip_installs(s.get("run", ""))]
    assert cmds and all(_hashed_or_offline(c) for c in cmds), cmds
    assert any("--require-hashes" in c and "--only-binary :all:" in c for c in cmds), cmds
    assert "hashFiles('.ai-workflows/requirements.lock', '.ai-workflows/pyproject.toml')" in text


def test_checks_reject_unhashed_installs():
    assert not _hashed_or_offline("pip install -e ./.ai-workflows")
    assert not _hashed_or_offline("pip install --require-hashes -r other.txt")
    assert not _hashed_or_offline("pip install --no-deps -e .")
    assert _pip_installs("python -m venv v && v/bin/pip install pyyaml && echo ok") == ["pip install pyyaml "]


def test_lock_pins_every_dependency_with_hashes():
    entries = re.split(r"\n(?=[a-z0-9])", re.sub(r"(?m)^\s*#.*\n?", "", LOCK.read_text()).strip())
    pinned = {}
    for entry in entries:
        m = re.match(r"([a-z0-9][a-z0-9._-]*)==\S+", entry)
        assert m and "--hash=sha256:" in entry, entry.splitlines()[0]
        pinned[m.group(1)] = entry
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    wanted = [*project["project"]["dependencies"], *project["build-system"]["requires"]]
    for req in wanted:
        assert re.match(r"[A-Za-z0-9._-]+", req).group(0).lower() in pinned, f"{req} not in requirements.lock"


def test_test_lock_pins_the_test_extra_with_hashes():
    text = (ROOT / "requirements-test.lock").read_text()
    pinned = set(re.findall(r"(?m)^([a-z0-9][a-z0-9._-]*)==", text))
    assert text.count("--hash=sha256:") >= len(pinned)
    for req in tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["optional-dependencies"]["test"]:
        assert re.match(r"[A-Za-z0-9._-]+", req).group(0).lower() in pinned, f"{req} not in requirements-test.lock"
    assert pinned >= set(re.findall(r"(?m)^([a-z0-9][a-z0-9._-]*)==", LOCK.read_text()))
