import json
import urllib.error

import pytest

from aiwf import notify as n

HOOK = "https://hooks.slack.com/services/T000/B000/SECRETHOOK"
TOKEN = "123456:SECRET-TOKEN"
CHAT = "-100777"
ENV = {"SLACK_WEBHOOK_URL": HOOK, "TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": CHAT}
LINK = "https://github.com/o/r/actions/runs/42"


def tg_ok(text: str, message_id: int = 7) -> str:
    url_at = text.encode("utf-16-le").find(LINK.encode("utf-16-le")) // 2
    return json.dumps({"ok": True, "result": {"message_id": message_id, "chat": {"id": CHAT}, "text": text,
                                              "entities": [{"type": "url", "offset": url_at, "length": len(LINK)}]}})


class Fake:
    def __init__(self, answers=None, raise_for=None):
        self.calls = []
        self.answers = answers or {}
        self.raise_for = raise_for

    def __call__(self, url, payload):
        self.calls.append((url, payload))
        if self.raise_for and self.raise_for in url:
            raise urllib.error.URLError(f"cannot reach {url}")
        if "slack" in url:
            return self.answers.get("slack", (200, "ok"))
        return self.answers.get("telegram", (200, tg_ok(payload["text"])))


@pytest.mark.parametrize("value, want", [
    ("slack", ["slack"]), ("telegram", ["telegram"]), ("slack,telegram", ["slack", "telegram"]),
    (" Telegram, slack slack ", ["telegram", "slack"]), ("none", []), ("", []),
])
def test_parse_channels(value, want):
    assert n.parse_channels(value) == want


def test_parse_channels_rejects_unknown():
    with pytest.raises(n.NotifyError, match="email"):
        n.parse_channels("slack,email")


@pytest.mark.parametrize("url", ["http://github.com/x", "javascript:alert(1)", "https://a b", "https://x|y", ""])
def test_link_must_be_one_https_url(url):
    with pytest.raises(n.NotifyError):
        n.check_link(url)


def test_one_message_per_channel_with_the_link():
    post = Fake()
    results, errors = n.notify(["slack", "telegram"], "Hello", LINK, ENV, post)
    assert errors == []
    assert [c[0] for c in post.calls] == [HOOK, f"https://api.telegram.org/bot{TOKEN}/sendMessage"]
    slack, telegram = post.calls[0][1], post.calls[1][1]
    assert slack["text"] == f"Hello <{LINK}|Open on GitHub>"
    assert telegram["chat_id"] == CHAT and telegram["text"] == f"Hello\n{LINK}" and "parse_mode" not in telegram
    assert results == [
        {"channel": "slack", "status": 200, "body": "ok", "links": [LINK]},
        {"channel": "telegram", "ok": True, "message_id": 7, "links": [LINK]},
    ]


def test_untrusted_text_is_escaped_for_slack_and_flattened():
    post = Fake()
    n.notify(["slack"], "a <!channel> & b\nsecond line", LINK, ENV, post)
    assert post.calls[0][1]["text"].startswith("a &lt;!channel&gt; &amp; b second line <")


def test_telegram_links_count_utf16_offsets():
    text = f"🚀 émoji\n{LINK}"
    assert n.telegram_links(json.loads(tg_ok(text))["result"]) == [LINK]


def test_missing_secrets_fail_that_channel_only():
    results, errors = n.notify(["slack", "telegram"], "x", LINK, {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": CHAT},
                               Fake())
    assert [r["channel"] for r in results] == ["telegram"]
    assert errors == ["slack: SLACK_WEBHOOK_URL is not set"]


@pytest.mark.parametrize("answers", [
    {"slack": (404, f"no_service {HOOK}")},
    {"telegram": (401, json.dumps({"ok": False, "description": f"Unauthorized {TOKEN} {CHAT}"}))},
])
def test_provider_errors_are_redacted(answers):
    results, errors = n.notify(["slack", "telegram"], "x", LINK, ENV, Fake(answers))
    assert len(results) == 1 and len(errors) == 1
    for secret in (HOOK, TOKEN, CHAT, "SECRET"):
        assert secret not in errors[0]


@pytest.mark.parametrize("where", ["slack", "telegram"])
def test_network_errors_never_print_the_request_url(where):
    _, errors = n.notify(["slack", "telegram"], "x", LINK, ENV, Fake(raise_for=where))
    assert len(errors) == 1 and errors[0].startswith(f"{where}: URLError")
    assert "SECRET" not in errors[0] and TOKEN not in errors[0]


def test_cli_prints_result_lines_and_fails_on_any_error(monkeypatch, capsys):
    monkeypatch.setattr(n, "http_post", Fake({"slack": (500, "oops")}))
    for k, v in {**ENV, "NOTIFY_TEXT": "hi", "NOTIFY_URL": LINK, "AIWF_SHA": "abc"}.items():
        monkeypatch.setenv(k, v)
    assert n.cmd_notify(type("A", (), {"channels": "slack,telegram"})()) == 1
    out, err = capsys.readouterr()
    lines = [json.loads(line[len(n.RESULT_PREFIX):]) for line in out.splitlines() if line.startswith(n.RESULT_PREFIX)]
    assert lines == [{"channel": "telegram", "ok": True, "message_id": 7, "links": [LINK], "aiwf_sha": "abc"}]
    assert "::error title=notify::slack: Slack answered HTTP 500" in err
    assert "SECRET" not in out + err


def test_cli_with_no_channel_sends_nothing(capsys):
    assert n.cmd_notify(type("A", (), {"channels": "none"})()) == 0
    assert "nothing sent" in capsys.readouterr().out
