import base64
import json
from pathlib import Path

import pytest

from aiwf import cli, config

FIX = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parents[1]


def load_text(text):
    return config.load(text, "test.yml")


def errors_of(text):
    with pytest.raises(config.ConfigError) as exc:
        load_text(text)
    return exc.value.errors


# --- valid configs and defaults ---------------------------------------------


def test_minimal_config_gets_all_defaults():
    cfg = load_text((FIX / "minimal.yml").read_text())
    assert cfg == {
        "enabled": True,
        "maintainers": ["esciara"],
        "default_branch": "main",
        "risk_paths": {"high": [], "medium": []},
        "limits": {"human_review_lines": 400, "fix_rounds": 3, "info_requests": 2},
        "reporter_silence_days": {"ping": 4, "stale": 14, "close": 21},
        "notify": "none",
        "fork_prs": "on-command",
        "workflows": {"review": True, "triage": False},
    }


def test_full_config_keeps_explicit_values():
    cfg = load_text((FIX / "full.yml").read_text())
    assert cfg["limits"] == {"human_review_lines": 300, "fix_rounds": 2, "info_requests": 1}
    assert cfg["risk_paths"]["medium"] == ["src/api/**"]
    assert cfg["model"] == "claude-sonnet-4-5"
    assert cfg["required_checks"] == ["test", "lint"]
    assert cfg["workflows"]["triage"] is True


def test_partial_nested_object_is_filled():
    cfg = load_text("maintainers: [a]\nlimits: {fix_rounds: 5}\n")
    assert cfg["limits"] == {"human_review_lines": 400, "fix_rounds": 5, "info_requests": 2}


def test_example_template_is_valid():
    cfg = load_text((ROOT / "templates" / "ai-workflows.example.yml").read_text().replace("<OWNER>", "esciara"))
    assert cfg["maintainers"] == ["esciara"]


def test_defaults_do_not_mutate_input():
    data = {"maintainers": ["a"]}
    config.apply_defaults(data)
    assert data == {"maintainers": ["a"]}


# --- invalid configs ---------------------------------------------------------


def test_missing_maintainers_and_unknown_key_both_reported():
    errs = errors_of((FIX / "invalid.yml").read_text())
    assert any("'maintainers' is a required property" in e for e in errs)
    assert any("'reviewers' was unexpected" in e for e in errs)


def test_empty_maintainers_rejected():
    assert any(e.startswith("$.maintainers:") for e in errors_of("maintainers: []\n"))


def test_unknown_nested_key_rejected_with_path():
    errs = errors_of("maintainers: [a]\nlimits: {fix_round: 3}\n")
    assert errs == ["$.limits: Additional properties are not allowed ('fix_round' was unexpected)"]


def test_wrong_type_reports_path():
    errs = errors_of("maintainers: [a]\nlimits: {fix_rounds: three}\n")
    assert errs[0].startswith("$.limits.fix_rounds:")


def test_bad_enum_rejected():
    assert errors_of("maintainers: [a]\nnotify: email\n")[0].startswith("$.notify:")


def test_bad_maintainer_login_reports_index():
    assert errors_of("maintainers: [ok, 'not a login']\n")[0].startswith("$.maintainers[1]:")


def test_silence_days_order_enforced():
    errs = errors_of("maintainers: [a]\nreporter_silence_days: {ping: 10, stale: 5}\n")
    assert "ping < stale < close" in errs[0]


def test_invalid_yaml_reports_line():
    errs = errors_of("maintainers: [a\nfoo: bar\n")
    assert "invalid YAML" in errs[0] and errs[0].startswith("line ")


@pytest.mark.parametrize("text,msg", [("", "file is empty"), ("- a\n- b\n", "top level must be a mapping")])
def test_empty_or_non_mapping(text, msg):
    assert errors_of(text) == [msg]


# --- fetching from GitHub (gh mocked) ----------------------------------------


class FakeGh:
    def __init__(self, files, default_branch="main"):
        self.files, self.default_branch, self.calls = files, default_branch, []

    def __call__(self, args):
        self.calls.append(args)
        endpoint = args[1]
        if "/contents/" in endpoint:
            path, ref = endpoint.split("/contents/", 1)[1].split("?ref=")
            if (path, ref) not in self.files:
                raise RuntimeError("gh: Not Found (HTTP 404)")
            content = base64.b64encode(self.files[(path, ref)].encode()).decode()
            return json.dumps({"type": "file", "content": content})
        return self.default_branch + "\n"


def test_fetch_uses_default_branch_not_head():
    gh = FakeGh({(".github/ai-workflows.yml", "trunk"): "maintainers: [a]\n"}, default_branch="trunk")
    text, source = config.fetch_from_repo("o/r", ".github/ai-workflows.yml", gh=gh)
    assert text == "maintainers: [a]\n"
    assert source == "o/r:.github/ai-workflows.yml@trunk"
    assert gh.calls[0] == ["api", "repos/o/r", "--jq", ".default_branch"]


def test_fetch_explicit_ref_skips_default_branch_lookup():
    gh = FakeGh({("c.yml", "feature"): "maintainers: [a]\n"})
    config.fetch_from_repo("o/r", "c.yml", ref="feature", gh=gh)
    assert len(gh.calls) == 1


def test_fetch_missing_file():
    with pytest.raises(config.ConfigError) as exc:
        config.fetch_from_repo("o/r", "nope.yml", gh=FakeGh({}))
    assert exc.value.errors == ["file not found"]


def test_fetch_directory_rejected():
    gh = lambda args: json.dumps([{"type": "file"}]) if "contents" in args[1] else "main"
    with pytest.raises(config.ConfigError) as exc:
        config.fetch_from_repo("o/r", ".github", gh=gh)
    assert exc.value.errors == ["path is not a file"]


# --- CLI ---------------------------------------------------------------------


def test_cli_valid_writes_outputs(tmp_path, capsys):
    out = tmp_path / "out"
    rc = cli.main(["config", "--file", str(FIX / "full.yml"), "--github-output", str(out)])
    assert rc == 0
    assert "Config OK" in capsys.readouterr().out
    lines = dict(line.split("=", 1) for line in out.read_text().splitlines())
    assert json.loads(lines["config"])["maintainers"] == ["esciara", "other-dev"]
    assert lines["review"] == "true" and lines["triage"] == "true"


def test_cli_disabled_turns_workflows_off(tmp_path):
    f = tmp_path / "c.yml"
    f.write_text("enabled: false\nmaintainers: [a]\n")
    out = tmp_path / "out"
    assert cli.main(["config", "--file", str(f), "--github-output", str(out)]) == 0
    assert "review=false" in out.read_text().splitlines()


def test_cli_invalid_exits_nonzero(tmp_path, capsys):
    out = tmp_path / "out"
    rc = cli.main(["config", "--file", str(FIX / "invalid.yml"), "--github-output", str(out)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "::error title=Invalid ai-workflows config::" in err
    assert "'reviewers' was unexpected" in err
    assert not out.exists()


def test_cli_missing_file(capsys):
    assert cli.main(["config", "--file", "/nonexistent/x.yml"]) == 1
    assert "Cannot read config" in capsys.readouterr().err


def test_cli_repo_mode(monkeypatch, tmp_path):
    gh = FakeGh({(".github/ai-workflows.yml", "main"): "maintainers: [a]\n"})
    monkeypatch.setattr(config, "run_gh", gh)
    out = tmp_path / "out"
    assert cli.main(["config", "--repo", "o/r", "--github-output", str(out)]) == 0
    assert '"maintainers":["a"]' in out.read_text()
