"""Chat notifications (WP11a, ADR-0024): one message per channel, Slack (incoming webhook) and Telegram (Bot API
`sendMessage`), each a short text plus a link back to GitHub.

Secrets (SLACK_WEBHOOK_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID) and the message (NOTIFY_TEXT, NOTIFY_URL) come from
env vars, never the command line. Nothing printed carries a secret: errors are reduced to a status or an exception
type and redacted, and the result lines hold only what the provider answered (Slack: status and body; Telegram: `ok`,
`message_id` and the links it parsed out of the stored message), not the chat ID or the request URL.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping

CHANNELS = ("slack", "telegram")
RESULT_PREFIX = "AIWF_NOTIFY_RESULT "
TELEGRAM_API = "https://api.telegram.org"
MAX_TEXT = 3000  # well under Telegram's 4096-character limit, link included
SECRET_ENV = ("SLACK_WEBHOOK_URL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
URL_RE = re.compile(r"https://[^\s<>|\"']+")

Post = Callable[[str, dict[str, Any]], tuple[int, str]]


class NotifyError(Exception):
    pass


def parse_channels(value: str) -> list[str]:
    """`slack`, `telegram`, `slack,telegram`, `none` or empty -> ordered, de-duplicated channel list."""
    out: list[str] = []
    for name in re.split(r"[,\s]+", value.strip().lower()):
        if name in ("", "none"):
            continue
        if name not in CHANNELS:
            raise NotifyError(f"unknown channel {name!r} (expected {', '.join(CHANNELS)} or none)")
        if name not in out:
            out.append(name)
    return out


def check_link(url: str) -> str:
    if not URL_RE.fullmatch(url):
        raise NotifyError("the link must be a single https:// URL")
    return url


def one_line(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…"


def slack_escape(text: str) -> str:
    """Slack mrkdwn control characters; also defuses `<!channel>`-style mentions in untrusted text."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def slack_payload(text: str, url: str) -> dict[str, Any]:
    return {"text": f"{slack_escape(text)} <{url}|Open on GitHub>", "unfurl_links": False}


def telegram_payload(chat_id: str, text: str, url: str) -> dict[str, Any]:
    # Plain text (no parse_mode), so nothing in `text` is read as markup; Telegram turns the URL into a link entity.
    return {"chat_id": chat_id, "text": f"{text}\n{url}", "link_preview_options": {"is_disabled": True}}


def telegram_links(message: Mapping[str, Any]) -> list[str]:
    """URLs Telegram found in the stored message (entity offsets count UTF-16 code units)."""
    raw = str(message.get("text", "")).encode("utf-16-le")
    links = []
    for ent in message.get("entities") or []:
        if ent.get("type") == "url":
            start, length = int(ent["offset"]) * 2, int(ent["length"]) * 2
            links.append(raw[start : start + length].decode("utf-16-le"))
        elif ent.get("type") == "text_link":
            links.append(str(ent.get("url", "")))
    return links


def http_post(url: str, payload: dict[str, Any]) -> tuple[int, str]:
    """POST JSON; returns (status, body) for any HTTP answer. Network errors raise (callers redact them)."""
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "ai-workflows-notify"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def redact(text: str, secrets: list[str]) -> str:
    for s in sorted((s for s in secrets if s), key=len, reverse=True):
        text = text.replace(s, "***")
    return text


def send_slack(webhook: str, text: str, url: str, post: Post) -> dict[str, Any]:
    status, body = post(webhook, slack_payload(text, url))
    if status != 200 or body.strip() != "ok":
        raise NotifyError(f"Slack answered HTTP {status}: {body.strip()[:200]}")
    return {"channel": "slack", "status": status, "body": body.strip(), "links": [url]}


def send_telegram(token: str, chat_id: str, text: str, url: str, post: Post) -> dict[str, Any]:
    status, body = post(f"{TELEGRAM_API}/bot{token}/sendMessage", telegram_payload(chat_id, text, url))
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        data = {}
    if status != 200 or data.get("ok") is not True:
        raise NotifyError(f"Telegram answered HTTP {status}: {str(data.get('description', ''))[:200]}")
    message = data.get("result") or {}
    return {"channel": "telegram", "ok": True, "message_id": message.get("message_id"), "links": telegram_links(message)}


def notify(channels: list[str], text: str, url: str, env: Mapping[str, str], post: Post | None = None
           ) -> tuple[list[dict[str, Any]], list[str]]:
    """Send one message per channel. Returns (results, errors); errors are redacted and never stop other channels."""
    post = post or http_post
    text, url = one_line(text), check_link(url)
    secrets = [env.get(k, "") for k in SECRET_ENV]
    results, errors = [], []
    for channel in channels:
        try:
            if channel == "slack":
                if not env.get("SLACK_WEBHOOK_URL"):
                    raise NotifyError("SLACK_WEBHOOK_URL is not set")
                results.append(send_slack(env["SLACK_WEBHOOK_URL"], text, url, post))
            else:
                if not env.get("TELEGRAM_BOT_TOKEN") or not env.get("TELEGRAM_CHAT_ID"):
                    raise NotifyError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must both be set")
                results.append(send_telegram(env["TELEGRAM_BOT_TOKEN"], env["TELEGRAM_CHAT_ID"], text, url, post))
        except NotifyError as exc:
            errors.append(f"{channel}: {redact(str(exc), secrets)}")
        except Exception as exc:  # network errors: the message may hold a URL, so keep only the type and redact
            errors.append(f"{channel}: {type(exc).__name__}: {redact(str(exc), secrets)[:200]}")
    return results, errors


def cmd_notify(args: argparse.Namespace) -> int:
    env = os.environ
    try:
        channels = parse_channels(args.channels)
        if not channels:
            print("notify: no channel configured, nothing sent")
            return 0
        results, errors = notify(channels, env.get("NOTIFY_TEXT", ""), env.get("NOTIFY_URL", ""), env)
    except NotifyError as exc:
        print(f"::error title=notify::{exc}", file=sys.stderr)
        return 1
    for r in results:
        print(RESULT_PREFIX + json.dumps({**r, "aiwf_sha": env.get("AIWF_SHA", "")}, sort_keys=True))
    for e in errors:
        print(f"::error title=notify::{e}", file=sys.stderr)
    return 1 if errors else 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("notify", help="send one chat message per channel (env NOTIFY_TEXT, NOTIFY_URL and secrets)")
    p.add_argument("--channels", required=True, help="slack, telegram, slack,telegram or none")
    p.set_defaults(func=cmd_notify)
