import json

import pytest

from aiwf import cli, publish


def test_valid_ping():
    assert publish.validate("ping", '{"reply": "Runtime is up."}') == {"reply": "Runtime is up."}


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "not json",
        '{"reply": "ok"',  # truncated
        "[]",
        '"pong"',
        "null",
        "{}",
        '{"reply": ""}',
        '{"reply": 42}',
        '{"reply": "ok", "labels": ["ai-review: merge"]}',  # extra keys
        '{"reply": "ok @esciara"}',  # mention
        '{"reply": "<!-- ai-review:summary v1 -->"}',  # hidden marker / HTML
        '{"reply": "line one\\nline two"}',
        '{"reply": "run `rm -rf /`"}',
        json.dumps({"reply": "x" * 201}),
        "[" * 5000 + "]" * 5000,  # deep nesting
        json.dumps({"reply": "y" * 70_000}),  # oversized
    ],
)
def test_invalid_ping_rejected(raw):
    with pytest.raises(publish.InvalidOutput):
        publish.validate("ping", raw)


class FakeGh:
    def __init__(self):
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        return "{}"


def test_publish_valid_posts_reply_only():
    gh = FakeGh()
    assert publish.publish("ping", '{"reply": "All good."}', "o/r", 7, "https://run", gh)
    assert len(gh.calls) == 1
    args = gh.calls[0]
    assert args[:4] == ["api", "-X", "POST", "repos/o/r/issues/7/comments"]
    body = args[-1].removeprefix("body=")
    assert body.startswith("<!-- ai-workflows:ping -->\n🏓 pong: All good.")
    assert "[Run](https://run)" in body


def test_publish_invalid_labels_error_and_posts_nothing():
    gh = FakeGh()
    assert not publish.publish("ping", '{"reply": "hi @someone"}', "o/r", 7, "", gh)
    assert gh.calls == [["api", "-X", "POST", "repos/o/r/issues/7/labels", "-f", "labels[]=ai: error"]]


def test_cli_publish_exit_codes(monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(cli.config, "run_gh", gh)
    monkeypatch.setenv("AGENT_JSON", '{"reply": "fine"}')
    assert cli.main(["publish", "--kind", "ping", "--repo", "o/r", "--issue", "3"]) == 0
    monkeypatch.setenv("AGENT_JSON", "")
    assert cli.main(["publish", "--kind", "ping", "--repo", "o/r", "--issue", "3"]) == 1
