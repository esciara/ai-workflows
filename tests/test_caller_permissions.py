"""The caller template's job permissions cover what each called reusable workflow's jobs declare.

A called job asking for a scope the caller job does not grant ends the run in startup_failure. Checked against this
checkout's workflows, i.e. the version the template pins once released.
"""

import re
from pathlib import Path

import pytest

from aiwf import policy

ROOT = Path(__file__).resolve().parents[1]
RANK = {"none": 0, "read": 1, "write": 2}
USES = re.compile(r"/\.github/workflows/([\w.-]+\.yml)@")
SCOPES = {
    "actions", "attestations", "checks", "contents", "deployments", "discussions", "id-token", "issues",
    "models", "packages", "pages", "pull-requests", "repository-projects", "security-events", "statuses",
}  # fmt: skip


def _expand(perms) -> dict | None:
    """Permissions as {scope: level}; read-all/write-all expand to every scope; None when not declared."""
    if perms is None:
        return None
    if perms in ("read-all", "write-all"):
        return dict.fromkeys(SCOPES, perms.split("-")[0])
    if not isinstance(perms, dict):
        raise AssertionError(f"unsupported permissions value: {perms!r}")
    for scope, level in perms.items():
        assert scope in SCOPES, f"unknown permission scope {scope!r}"
        assert level in RANK, f"unknown permission level {level!r} for scope {scope!r}"
    return perms


def _effective(job: dict, workflow: dict) -> dict | None:
    """A job's own permissions, else the workflow-level ones, else None (repository default, not checkable)."""
    own = _expand(job.get("permissions"))
    return own if own is not None else _expand(workflow.get("permissions"))


def uncovered(caller_perms: dict, called_jobs: dict, called_workflow: dict | None = None) -> list[str]:
    """Scopes a called job declares above what the caller grants, as 'job: scope'."""
    out = []
    for name, job in called_jobs.items():
        declared = _effective(job, called_workflow or {})
        for scope, level in (declared or {}).items():
            if RANK[level] > RANK[(caller_perms or {}).get(scope, "none")]:
                out.append(f"{name}: {scope}")
    return out


def _caller_jobs():
    caller = policy.load_workflow((ROOT / "templates" / "caller.yml").read_text())
    return [(n, j, caller) for n, j in caller["jobs"].items() if "uses" in j]


@pytest.mark.parametrize("name,job,caller", _caller_jobs())
def test_caller_job_covers_called_workflow(name, job, caller):
    target = USES.search(job["uses"]).group(1)
    called = policy.load_workflow((ROOT / ".github" / "workflows" / target).read_text())
    granted = _effective(job, caller) or {}
    assert uncovered(granted, called["jobs"], called) == []


def test_write_needed_but_read_granted_fails():
    assert uncovered({"pull-requests": "read"}, {"escalate": {"permissions": {"pull-requests": "write"}}}) == [
        "escalate: pull-requests"
    ]


def test_scope_missing_from_caller_fails():
    assert uncovered({}, {"j": {"permissions": {"issues": "read"}}}) == ["j: issues"]


def test_covered_and_empty_permissions_pass():
    called = {"j": {"permissions": {"issues": "read"}}, "k": {"permissions": {}}}
    assert uncovered({"issues": "write"}, called) == []


def test_write_all_shorthand_is_expanded():
    assert uncovered({"issues": "read"}, {"j": {"permissions": "write-all"}}) == [f"j: {s}" for s in _expand("write-all")]
    assert uncovered(_expand("write-all"), {"j": {"permissions": "read-all"}}) == []


def test_workflow_level_permissions_are_inherited():
    called_wf = {"permissions": {"issues": "write"}}
    assert uncovered({"issues": "read"}, {"j": {}}, called_wf) == ["j: issues"]
    assert uncovered({"issues": "read"}, {"j": {"permissions": {}}}, called_wf) == []


def test_unknown_scope_gives_clear_message():
    with pytest.raises(AssertionError, match="unknown permission scope 'issuse'"):
        uncovered({}, {"j": {"permissions": {"issuse": "read"}}})


def test_nested_workflow_jobs_are_covered_by_the_job_that_calls_them():
    """triage.yml calls fix.yml (aiwf-vqm) and, for chat alerts, notify.yml (WP11b2): the calling job's permissions are the ceiling of the called jobs, and the
    caller template covers the calling job (test_caller_job_covers_called_workflow), so by induction covers fix.yml."""
    triage = policy.load_workflow((ROOT / ".github" / "workflows" / "triage.yml").read_text())
    nested = {n: j for n, j in triage["jobs"].items() if str(j.get("uses", "")).startswith("./.github/workflows/")}
    assert set(nested) == {"fix", "notify-analysis", "notify-fix"}
    for name, job in nested.items():
        called = policy.load_workflow((ROOT / job["uses"]).read_text())
        assert uncovered(_effective(job, triage) or {}, called["jobs"], called) == [], name
