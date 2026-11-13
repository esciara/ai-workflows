"""config.fetch_from_repo error paths: every failure becomes a ConfigError that names the repo, path and ref."""

import base64
import json

import pytest

from aiwf import config


def contents(payload):
    """A gh stub: default branch `main`, then `payload` (str: raw body; Exception: raised) for the contents call."""
    def gh(args):
        if "/contents/" not in args[1]:
            return "main\n"
        if isinstance(payload, Exception):
            raise payload
        return payload if isinstance(payload, str) else json.dumps(payload)
    return gh


def errors_of(gh):
    with pytest.raises(config.ConfigError) as exc:
        config.fetch_from_repo("o/r", "c.yml", gh=gh)
    return exc.value


def test_repo_metadata_failure_is_a_config_error():
    def gh(args):
        raise RuntimeError("HTTP 403: Resource not accessible")
    err = errors_of(gh)
    assert err.errors == ["cannot read repo metadata: HTTP 403: Resource not accessible"]
    assert err.source == "o/r"


@pytest.mark.parametrize("message,reason", [
    ("gh: Not Found (HTTP 404)", "file not found"),
    ("HTTP 404", "file not found"),
    ("HTTP 403: rate limit exceeded", "HTTP 403: rate limit exceeded"),  # not a missing file: the real cause shows
])
def test_contents_failure_names_the_source_and_reason(message, reason):
    err = errors_of(contents(RuntimeError(message)))
    assert err.errors == [reason]
    assert err.source == "o/r:c.yml@main"


def test_non_json_response():
    assert errors_of(contents("<html>bad gateway</html>")).errors == ["unexpected response from GitHub contents API"]


@pytest.mark.parametrize("payload", [{"type": "dir"}, {"type": "symlink"}, {}, [], "null"])
def test_anything_but_a_file_is_rejected(payload):
    assert errors_of(contents(payload)).errors == ["path is not a file"]


@pytest.mark.parametrize("content", ["!!!not base64!!!", base64.b64encode(b"\xff\xfe\x00bad").decode()])
def test_undecodable_content(content):
    assert errors_of(contents({"type": "file", "content": content})).errors == ["content is not valid base64/UTF-8"]


def test_content_with_github_line_breaks_decodes():
    body = base64.encodebytes(b"maintainers: [a]\n" * 10).decode()  # the API wraps base64 at 60 columns
    text, _ = config.fetch_from_repo("o/r", "c.yml", gh=contents({"type": "file", "content": body}))
    assert text == "maintainers: [a]\n" * 10
