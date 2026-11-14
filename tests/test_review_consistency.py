"""Single sources of truth that review.yml cannot import from Python: the checks below keep the copies in step."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from aiwf import labels, metrics, review

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"
REVIEW_YML = (WF / "review.yml").read_text()
LABEL_LITERAL = re.compile(r"ai-review: [a-z-]+|ai: error")


def test_pass_list_is_the_same_in_python_and_the_workflow():
    wf = yaml.safe_load(REVIEW_YML)
    assert tuple(wf["jobs"]["pass"]["strategy"]["matrix"]["pass"]) == review.PASSES
    loop = re.search(r"for p in ([a-z ]+); do", REVIEW_YML).group(1).split()  # the verifier's candidate ids
    assert tuple(loop) == review.PASSES
    assert metrics.AGENTS == (*review.PASSES, "verify")


def test_label_constants_are_in_the_label_set_and_the_workflows_use_no_other():
    known = {label["name"] for label in labels.load()}
    assert {labels.PENDING, *labels.VERDICTS, labels.ERROR} <= known
    for path in WF.glob("*.yml"):
        for literal in LABEL_LITERAL.findall(path.read_text()):
            assert literal in known, f"{path.name}: unknown label {literal!r}"


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq not installed")
def test_workflow_candidate_ids_match_review_candidates(tmp_path):
    """review.yml builds `<pass>-<n>` ids with jq for the verifier; review.candidates() rebuilds them to join decisions."""
    answers = {"correctness": {"findings": [{"title": "a"}, {"title": "b"}]}, "security": {"findings": []},
               "maintainability": {"findings": [{"title": "c"}]}, "tests": {}}
    for name, answer in answers.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(answer))
    jq_line = re.search(r"jq -c --arg p \"\$p\" '([^']+)'", REVIEW_YML).group(1)
    out = []
    for name in review.PASSES:
        res = subprocess.run(["jq", "-c", "--arg", "p", name, jq_line, str(tmp_path / f"{name}.json")],
                             capture_output=True, text=True, check=True)
        out += json.loads(res.stdout)
    assert out == review.candidates(answers)
