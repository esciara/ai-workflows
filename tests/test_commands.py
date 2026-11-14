import json

import pytest

from aiwf import cli, commands
from aiwf.commands import Command
from ghfake import RecordingGh


# --- parsing ------------------------------------------------------------------


@pytest.mark.parametrize(
    "body,expected",
    [
        ("/review", Command("review")),
        ("/review\n\nthanks", Command("review")),
        ("  /review", Command("review")),
        ("\n\n   /review  \r\n", Command("review")),
        ("/review please ignore this", Command("review")),
        ("/retriage", Command("retriage")),
        ("/fix", Command("fix")),
        ("/fix use a lock here", Command("fix", "use a lock here")),
        ("/no-fix not worth it", Command("no-fix", "not worth it")),
    ],
)
def test_parse_accepts(body, expected):
    assert commands.parse(body) == expected


@pytest.mark.parametrize(
    "body",
    [
        None,
        "",
        "   \n  ",
        "/unknown",
        "/ping",  # dropped: not in the spec
        "/reviewed",
        "/REVIEW",
        "/ review",
        "review",
        "please /review",
        "hello\n/review",  # not on the first line
        "> /review",  # blockquote
        "```\n/review\n```",  # code fence
        "~~~\n/review\n~~~",
        "    /review",  # indented code block
        "\t/review",
        "`/review`",
        "/no-fix",  # reason required
        "/no-fix   ",
    ],
)
def test_parse_ignores(body):
    assert commands.parse(body) is None


# --- author check (ADR-0005) ----------------------------------------------------


@pytest.mark.parametrize(
    "login,permission,ok",
    [
        ("esciara", "admin", True),  # maintainer, admin
        ("esciara", "write", True),  # maintainer, write
        ("ESciara", "write", True),  # logins are case-insensitive
        ("esciara", "read", False),  # maintainer, no write
        ("esciara", "none", False),
        ("someone", "write", False),  # write, not a maintainer
        ("someone", "admin", False),
        ("someone", "read", False),  # neither
        ("ai-workflows-tester[bot]", "none", False),
    ],
)
def test_authorize(login, permission, ok):
    assert commands.authorize(login, ["esciara"], permission) is ok


class FakeGh(RecordingGh):
    def __init__(self, permission=None, fail=False):
        super().__init__()
        self.permission, self.fail = permission, fail

    def respond(self, args):
        if self.fail:
            raise RuntimeError("gh: Not Found (HTTP 404)")
        return self.permission + "\n"


def test_accept_maintainer_with_write():
    gh = FakeGh("write")
    assert commands.accept("/review", "esciara", ["esciara"], "o/r", gh) == Command("review")
    assert gh.calls == [["api", "repos/o/r/collaborators/esciara/permission", "--jq", ".permission"]]


def test_accept_maintainer_without_write():
    assert commands.accept("/review", "esciara", ["esciara"], "o/r", FakeGh("read")) is None


def test_accept_non_maintainer_skips_api_call():
    gh = FakeGh("admin")
    assert commands.accept("/review", "ai-workflows-tester[bot]", ["esciara"], "o/r", gh) is None
    assert gh.calls == []


def test_accept_permission_lookup_fails_closed():
    assert commands.accept("/review", "esciara", ["esciara"], "o/r", FakeGh(fail=True)) is None


def test_accept_not_a_command_skips_api_call():
    gh = FakeGh("admin")
    assert commands.accept("> /review", "esciara", ["esciara"], "o/r", gh) is None
    assert gh.calls == []


# --- CLI ------------------------------------------------------------------------


def comment_event(body="/fix use a lock", login="esciara", on_pr=False):
    issue = {"number": 3, **({"pull_request": {"url": "x"}} if on_pr else {})}
    return {"issue": issue, "comment": {"body": body, "user": {"login": login}}}


def test_from_event_parses_comments_only():
    gh = FakeGh("admin")
    assert commands.from_event("issue_comment", comment_event(), ["esciara"], "o/r", gh) == Command("fix", "use a lock")
    assert commands.from_event("issues", comment_event(), ["esciara"], "o/r", gh) is None
    assert commands.from_event("issue_comment", {}, ["esciara"], "o/r", gh) is None


def run_config(tmp_path, monkeypatch, event_name, payload, permission="admin"):
    (tmp_path / "c.yml").write_text("maintainers: [esciara]\n")
    (tmp_path / "event.json").write_text(json.dumps(payload))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "event.json"))
    monkeypatch.setenv("GITHUB_EVENT_NAME", event_name)
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    gh = FakeGh(permission)
    monkeypatch.setattr(cli.config, "run_gh", gh)
    out = tmp_path / "out"
    assert cli.main(["config", "--file", str(tmp_path / "c.yml"), "--github-output", str(out)]) == 0
    got = dict(line.split("=", 1) for line in out.read_text().splitlines())
    return got, json.loads(got["config"]), gh


def test_cli_config_outputs_the_accepted_command(tmp_path, monkeypatch):
    got, cfg, gh = run_config(tmp_path, monkeypatch, "issue_comment", comment_event())
    assert got["command"] == "fix"
    assert (cfg["command"], cfg["command_args"]) == ("fix", '"use a lock"')
    assert gh.calls == [["api", "repos/o/r/collaborators/esciara/permission", "--jq", ".permission"]]


@pytest.mark.parametrize("login,permission", [("intruder", "admin"), ("esciara", "read")])
def test_cli_config_refused_command_is_empty(tmp_path, monkeypatch, login, permission):
    got, cfg, _ = run_config(tmp_path, monkeypatch, "issue_comment", comment_event("/review", login), permission)
    assert got["command"] == "" and cfg["command"] == "" and cfg["command_args"] == ""


def test_cli_config_parses_no_comment_on_other_events(tmp_path, monkeypatch):
    got, cfg, gh = run_config(tmp_path, monkeypatch, "issues", {"issue": {"number": 3}, **comment_event()})
    assert got["command"] == "" and cfg["command"] == ""
    assert gh.calls == []


def test_cli_config_ai_off_skips_the_parse(tmp_path, monkeypatch):
    event = comment_event("/retriage")
    event["issue"]["labels"] = [{"name": "ai: off"}]
    got, _, gh = run_config(tmp_path, monkeypatch, "issue_comment", event)
    assert got["command"] == "" and got["enabled"] == "false"
    assert gh.calls == []
