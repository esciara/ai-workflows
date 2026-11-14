import json
import subprocess

from aiwf import metrics

RESULT = {"type": "result", "subtype": "success", "result": "agent text, never kept", "duration_ms": 41000,
          "num_turns": 2, "total_cost_usd": 0.0123,
          "usage": {"input_tokens": 12, "output_tokens": 900, "cache_read_input_tokens": 5000,
                    "cache_creation_input_tokens": 3000, "server_tool_use": {"web_search_requests": 0}}}


def test_usage_keeps_numbers_only_from_the_last_result():
    log = [{"type": "system"}, {"type": "assistant", "message": "x"}, {**RESULT, "num_turns": 1}, RESULT]
    assert metrics.usage_from_execution(log) == {
        "duration_ms": 41000, "num_turns": 2, "input_tokens": 12, "output_tokens": 900,
        "cache_read_input_tokens": 5000, "cache_creation_input_tokens": 3000, "cost_usd": 0.0123}


def test_usage_without_result_or_with_junk():
    assert metrics.usage_from_execution([{"type": "assistant"}]) is None
    assert metrics.usage_from_execution({"type": "result"}) is None
    got = metrics.usage_from_execution([{"type": "result", "num_turns": True, "duration_ms": -1, "usage": "x"}])
    assert got == {"duration_ms": 0, "num_turns": 0, "input_tokens": 0, "output_tokens": 0,
                   "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "cost_usd": 0.0}


def test_workflow_jq_reduces_the_execution_file(tmp_path):
    """The jq filter in review.yml keeps the numbers and drops the agent's text; metrics reads its output."""
    import yaml
    from pathlib import Path
    wf = yaml.safe_load((Path(__file__).resolve().parents[1] / ".github/workflows/review.yml").read_text())
    src = tmp_path / "exec.json"
    src.write_text(json.dumps([{"type": "system"}, RESULT]))
    out = subprocess.run(["jq", "-c", wf["env"]["USAGE_JQ"], str(src)], capture_output=True, text=True, check=True)
    assert "agent text" not in out.stdout
    (tmp_path / "verify.json").write_text(out.stdout)
    assert metrics.agents(tmp_path) == [{"agent": "verify", **metrics.usage_from_execution([RESULT])}]


def test_line_has_the_run_facts_and_agents_in_order(tmp_path):
    for name in ("verify", "security", "correctness"):
        (tmp_path / f"{name}.json").write_text(json.dumps([RESULT]))
    (tmp_path / "tests.json").write_text("not json")
    text = metrics.line(repo="o/r", run_id=7, run_attempt=1, pr=3, head_sha="h", aiwf_sha="a",
                        verdict="ai-review: merge", started=100.0, now=160.04, usage_dir=tmp_path)
    assert "\n" not in text
    m = json.loads(text)
    assert {k: v for k, v in m.items() if k != "agents"} == {
        "v": 1, "workflow": "review", "repo": "o/r", "run_id": 7, "run_attempt": 1, "pr": 3, "head_sha": "h",
        "aiwf_sha": "a", "verdict": "ai-review: merge", "duration_s": 60.0}
    assert [a["agent"] for a in m["agents"]] == ["correctness", "security", "verify"]


def test_line_with_no_usage_and_no_verdict(tmp_path):
    m = json.loads(metrics.line(repo="o/r", run_id=7, run_attempt=2, pr=3, head_sha="h", aiwf_sha="a", verdict="",
                                started=100.0, now=90.0, usage_dir=tmp_path / "missing"))
    assert m["verdict"] is None and m["agents"] == [] and m["duration_s"] == 0.0


def test_cli_writes_one_line_and_prints_it(tmp_path, monkeypatch, capsys):
    from aiwf import cli
    (tmp_path / "verify.json").write_text(json.dumps([RESULT]))
    monkeypatch.setenv("AIWF_SHA", "a")
    monkeypatch.setenv("VERDICT", "ai-review: human-review")
    out = tmp_path / "metrics.jsonl"
    rc = cli.main(["review-metrics", "--repo", "o/r", "--run-id", "7", "--run-attempt", "1", "--pr", "3", "--sha",
                   "h", "--started", "1", "--usage-dir", str(tmp_path), "--out", str(out)])
    assert rc == 0
    lines = out.read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["verdict"] == "ai-review: human-review"
    assert f"aiwf-metrics {lines[0]}" in capsys.readouterr().out
