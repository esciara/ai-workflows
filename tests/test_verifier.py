import json

import pytest

from aiwf import verifier

PLAN = """| ID | Package | Depends on | Delivers | Done when |
| --- | --- | --- | --- | --- |
| WP0 | Repo bootstrap | — | Layout | Caller loads config in a green run |
| WP1 | Shared runtime | WP0 | Runtime | `/ping` gets a reply; all labels exist |
"""


def test_done_when_extracts_the_wp_cell():
    assert verifier.done_when(PLAN, "WP1") == "`/ping` gets a reply; all labels exist"


def test_done_when_from_real_plan():
    text = (verifier.ROOT / "docs" / "plan.md").read_text()
    assert "green run" in verifier.done_when(text, "WP0")


def test_done_when_unknown_wp():
    with pytest.raises(verifier.VerifyError):
        verifier.done_when(PLAN, "WP99")


def test_pack_holds_spec_done_when_and_test_source():
    pack = verifier.build_pack("WP1")
    assert "<spec>" in pack and '<done_when wp="WP1">' in pack
    assert '<file path="tests/e2e/test_wp1.py">' in pack and '<file path="tests/e2e/playground.py">' in pack
    assert "def test_non_maintainer_ping_is_ignored" in pack


def test_test_files_lists_test_first_then_helpers():
    names = [p.name for p in verifier.test_files("WP1")]
    assert names[0] == "test_wp1.py" and "playground.py" in names and "conftest.py" in names
    assert not any(n.startswith("test_") for n in names[1:])


def test_missing_acceptance_test_is_an_error():
    with pytest.raises(verifier.VerifyError, match="no acceptance test"):
        verifier.test_files("WP99")


def envelope(verdict):
    return json.dumps({"type": "result", "result": json.dumps(verdict), "structured_output": verdict})


def test_parse_verdict_pass_and_fail():
    ok = {"verdict": "pass", "gaps": [], "notes": "each condition asserted"}
    assert verifier.parse_verdict(envelope(ok)) == ok
    bad = {"verdict": "fail", "gaps": ["labels not compared"], "notes": ""}
    assert verifier.parse_verdict(envelope(bad)) == bad


def test_parse_verdict_falls_back_to_result_text():
    ok = {"verdict": "pass", "gaps": [], "notes": "x"}
    assert verifier.parse_verdict(json.dumps({"result": json.dumps(ok)})) == ok


@pytest.mark.parametrize(
    "verdict",
    [
        {"verdict": "maybe", "gaps": [], "notes": ""},
        {"verdict": "pass", "gaps": [], "notes": "", "extra": 1},
        {"verdict": "pass", "notes": ""},
        {"verdict": "pass", "gaps": ["x"], "notes": ""},
    ],
)
def test_parse_verdict_rejects_invalid(verdict):
    with pytest.raises(verifier.VerifyError):
        verifier.parse_verdict(envelope(verdict))


def test_parse_verdict_rejects_non_json():
    with pytest.raises(verifier.VerifyError):
        verifier.parse_verdict("not json")
