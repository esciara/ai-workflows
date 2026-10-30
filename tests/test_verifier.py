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


def test_run_links_dedup_and_order():
    body = (
        "green https://github.com/esciara/ai-workflows-playground/actions/runs/41087000415\n"
        "red https://github.com/esciara/ai-workflows-playground/actions/runs/41087013620/job/1 and again "
        "https://github.com/esciara/ai-workflows-playground/actions/runs/41087000415 "
        "pr https://github.com/esciara/ai-workflows/pull/2"
    )
    assert verifier.run_links(body) == [
        ("esciara/ai-workflows-playground", "41087000415"),
        ("esciara/ai-workflows-playground", "41087013620"),
    ]


def test_truncate_keeps_head_and_tail():
    text = "a" * 10 + "b" * 100 + "c" * 10
    out = verifier.truncate(text, head=10, tail=10)
    assert out.startswith("a" * 10) and out.endswith("c" * 10) and "100 chars cut" in out
    assert verifier.truncate("short", head=10, tail=10) == "short"


def envelope(verdict):
    return json.dumps({"type": "result", "result": json.dumps(verdict), "structured_output": verdict})


def test_parse_verdict_pass_and_fail():
    ok = {"verdict": "pass", "unmet": [], "notes": "green run shown"}
    assert verifier.parse_verdict(envelope(ok)) == ok
    bad = {"verdict": "fail", "unmet": ["no run link"], "notes": ""}
    assert verifier.parse_verdict(envelope(bad)) == bad


def test_parse_verdict_falls_back_to_result_text():
    ok = {"verdict": "pass", "unmet": [], "notes": "x"}
    assert verifier.parse_verdict(json.dumps({"result": json.dumps(ok)})) == ok


@pytest.mark.parametrize(
    "verdict",
    [
        {"verdict": "maybe", "unmet": [], "notes": ""},
        {"verdict": "pass", "unmet": [], "notes": "", "extra": 1},
        {"verdict": "pass", "notes": ""},
        {"verdict": "pass", "unmet": ["x"], "notes": ""},
    ],
)
def test_parse_verdict_rejects_invalid(verdict):
    with pytest.raises(verifier.VerifyError):
        verifier.parse_verdict(envelope(verdict))


def test_parse_verdict_rejects_non_json():
    with pytest.raises(verifier.VerifyError):
        verifier.parse_verdict("not json")
