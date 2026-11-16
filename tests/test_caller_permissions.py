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


def _level(perms: dict, scope: str) -> int:
    return RANK[(perms or {}).get(scope, "none")]


def uncovered(caller_perms: dict, called_jobs: dict) -> list[str]:
    """Scopes a called job declares above what the caller grants, as 'job: scope'."""
    return [
        f"{name}: {scope}"
        for name, job in called_jobs.items()
        if isinstance(job.get("permissions"), dict)
        for scope, level in job["permissions"].items()
        if RANK[level] > _level(caller_perms, scope)
    ]


def _caller_jobs():
    caller = policy.load_workflow((ROOT / "templates" / "caller.yml").read_text())
    return [(n, j) for n, j in caller["jobs"].items() if "uses" in j]


@pytest.mark.parametrize("name,job", _caller_jobs())
def test_caller_job_covers_called_workflow(name, job):
    target = USES.search(job["uses"]).group(1)
    called = policy.load_workflow((ROOT / ".github" / "workflows" / target).read_text())
    assert uncovered(job.get("permissions") or {}, called["jobs"]) == []


def test_write_needed_but_read_granted_fails():
    assert uncovered({"pull-requests": "read"}, {"escalate": {"permissions": {"pull-requests": "write"}}}) == [
        "escalate: pull-requests"
    ]
    assert uncovered({}, {"j": {"permissions": {"issues": "read"}}}) == ["j: issues"]
    assert uncovered({"issues": "write"}, {"j": {"permissions": {"issues": "read"}}, "k": {"permissions": {}}}) == []
