"""Secrets wiring of the reusable workflows and templates/caller.yml (checkpoint item 6b).

A reusable workflow declares only the secrets it reads, so a caller is never asked for (and never hands over) a secret
nothing uses. The template passes a called workflow only secrets it declares: GitHub refuses to start a run that passes
an undeclared secret.
"""

import re
from pathlib import Path

import pytest

from aiwf import policy

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
LOCAL_USES = re.compile(r"esciara/ai-workflows/\.github/workflows/([\w.-]+)@")


def declared_secrets(path: Path) -> set[str]:
    doc = policy.load_workflow(path.read_text())
    on = doc.get("on", doc.get(True)) or {}
    call = on.get("workflow_call") if isinstance(on, dict) else None
    return set((call or {}).get("secrets") or {})


REUSABLE = sorted(p for p in WORKFLOWS.glob("*.yml") if declared_secrets(p))


@pytest.mark.parametrize("path", REUSABLE, ids=lambda p: p.name)
def test_reusable_workflow_reads_every_secret_it_declares(path):
    text = path.read_text()
    unread = sorted(s for s in declared_secrets(path) if not re.search(rf"\bsecrets\.{s}\b", text))
    assert not unread, f"{path.name} declares secrets nothing reads: {unread}"


def test_template_passes_only_declared_secrets():
    jobs = policy.load_workflow((ROOT / "templates" / "caller.yml").read_text())["jobs"]
    called = {name: LOCAL_USES.search(job.get("uses", "")) for name, job in jobs.items()}
    assert all(called.values()), f"jobs not calling a workflow of this repo: {[n for n, m in called.items() if not m]}"
    for name, job in jobs.items():
        extra = set(job.get("secrets") or {}) - declared_secrets(WORKFLOWS / called[name].group(1))
        assert not extra, f"template job {name!r} passes undeclared secrets {sorted(extra)}"
