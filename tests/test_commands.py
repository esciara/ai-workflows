import pytest

from aiwf import cli, commands
from aiwf.commands import Command


# --- parsing ------------------------------------------------------------------


@pytest.mark.parametrize(
    "body,expected",
    [
        ("/ping", Command("ping")),
        ("/ping\n\nthanks", Command("ping")),
        ("  /ping", Command("ping")),
        ("\n\n   /ping  \r\n", Command("ping")),
        ("/ping please ignore this", Command("ping")),
        ("/review", Command("review")),
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
        "/pinged",
        "/PING",
        "/ ping",
        "ping",
        "please /ping",
        "hello\n/ping",  # not on the first line
        "> /ping",  # blockquote
        "```\n/ping\n```",  # code fence
        "~~~\n/ping\n~~~",
        "    /ping",  # indented code block
        "\t/ping",
        "`/ping`",
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


class FakeGh:
    def __init__(self, permission=None, fail=False):
        self.permission, self.fail, self.calls = permission, fail, []

    def __call__(self, args):
        self.calls.append(args)
        if self.fail:
            raise RuntimeError("gh: Not Found (HTTP 404)")
        return self.permission + "\n"


def test_accept_maintainer_with_write():
    gh = FakeGh("write")
    assert commands.accept("/ping", "esciara", ["esciara"], "o/r", gh) == Command("ping")
    assert gh.calls == [["api", "repos/o/r/collaborators/esciara/permission", "--jq", ".permission"]]


def test_accept_maintainer_without_write():
    assert commands.accept("/ping", "esciara", ["esciara"], "o/r", FakeGh("read")) is None


def test_accept_non_maintainer_skips_api_call():
    gh = FakeGh("admin")
    assert commands.accept("/ping", "ai-workflows-tester[bot]", ["esciara"], "o/r", gh) is None
    assert gh.calls == []


def test_accept_permission_lookup_fails_closed():
    assert commands.accept("/ping", "esciara", ["esciara"], "o/r", FakeGh(fail=True)) is None


def test_accept_not_a_command_skips_api_call():
    gh = FakeGh("admin")
    assert commands.accept("> /ping", "esciara", ["esciara"], "o/r", gh) is None
    assert gh.calls == []


# --- CLI ------------------------------------------------------------------------


def test_cli_parse_command_writes_outputs(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMENT_BODY", "/fix use a lock")
    monkeypatch.setenv("COMMENT_AUTHOR", "esciara")
    monkeypatch.setenv("AIWF_CONFIG", '{"maintainers": ["esciara"]}')
    monkeypatch.setattr(cli.config, "run_gh", FakeGh("admin"))
    out = tmp_path / "out"
    assert cli.main(["parse-command", "--repo", "o/r", "--github-output", str(out)]) == 0
    assert out.read_text() == 'command=fix\nargs="use a lock"\n'


def test_cli_parse_command_rejected_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMENT_BODY", "/ping")
    monkeypatch.setenv("COMMENT_AUTHOR", "intruder")
    monkeypatch.setenv("AIWF_CONFIG", '{"maintainers": ["esciara"]}')
    out = tmp_path / "out"
    assert cli.main(["parse-command", "--repo", "o/r", "--github-output", str(out)]) == 0
    assert not out.exists()
