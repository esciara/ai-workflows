"""Shape of the reusable workflows (aiwf-6qs): one prompt-fetch step per file, reused by every agent job; one way to
call the aiwf CLI. Behaviour, not security policy (that is tests/test_workflow_policy.py)."""

import re
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github/workflows"
AGENT_ACTION = "./.ai-workflows/.github/actions/aiwf-agent"
FETCH = {
    "name": "Fetch ai-workflows",
    "env": {"AIWF_REPO": "${{ job.workflow_repository }}", "AIWF_SHA": "${{ job.workflow_sha }}"},
    "run": 'git init --quiet .ai-workflows\n'
           'git -C .ai-workflows fetch --quiet --depth 1 "https://github.com/$AIWF_REPO.git" "$AIWF_SHA"\n'
           'git -C .ai-workflows checkout --quiet FETCH_HEAD\n',
}


def jobs(name):
    return yaml.safe_load((WORKFLOWS / name).read_text())["jobs"]


@pytest.mark.parametrize("name,agents", [("review.yml", {"pass", "verify"}),
                                         ("triage.yml", {"extract", "classify", "reproduce", "analyse"})])
def test_every_agent_job_fetches_with_the_one_shared_step(name, agents):
    text = (WORKFLOWS / name).read_text()
    assert text.count("&fetch-aiwf") == 1 and text.count("*fetch-aiwf") == len(agents) - 1
    found = set()
    for job_name, job in jobs(name).items():
        steps = job.get("steps", [])
        uses_agent = [i for i, s in enumerate(steps) if s.get("uses") == AGENT_ACTION]
        fetches = [i for i, s in enumerate(steps) if "git init" in s.get("run", "")]
        if uses_agent:
            found.add(job_name)
            assert len(fetches) == 1 and fetches[0] < uses_agent[0], job_name
            assert steps[fetches[0]] == FETCH, job_name
        else:
            assert not fetches, job_name
    assert found == agents


@pytest.mark.parametrize("name", sorted(p.name for p in WORKFLOWS.glob("*.yml")))
def test_aiwf_is_called_one_way(name):
    """aiwf-setup puts the venv on PATH; workflows call `aiwf`, never the venv path."""
    assert "aiwf-venv/bin/aiwf" not in (WORKFLOWS / name).read_text()


@pytest.mark.parametrize("name", sorted(p.name for p in WORKFLOWS.glob("*.yml")))
def test_every_job_calling_aiwf_sets_it_up_first(name):
    """`aiwf` is on PATH only after aiwf-setup, in a later step of the same job."""
    for job_name, job in (jobs(name) or {}).items():
        setup = None
        for i, step in enumerate(job.get("steps", [])):
            if str(step.get("uses", "")).endswith("/.github/actions/aiwf-setup"):
                setup = i if setup is None else setup
            if re.search(r"(^|[\s;&|(])aiwf ", step.get("run", "")):
                assert setup is not None and setup < i, f"{name}:{job_name} step {i} calls aiwf before aiwf-setup"
