"""Validate an agent's JSON answer against its schema, then write to GitHub (orchestrator only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schema"
ERROR_LABEL = "ai: error"
MAX_INPUT = 64_000

GhRunner = Callable[[list[str]], str]


class InvalidOutput(Exception):
    pass


def validate(kind: str, raw: str | None) -> dict[str, Any]:
    """Parsed agent output for `kind`, or InvalidOutput. Never trusts the agent's text."""
    if not raw or not raw.strip():
        raise InvalidOutput("empty agent output")
    if len(raw) > MAX_INPUT:
        raise InvalidOutput("agent output too large")
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, RecursionError):
        raise InvalidOutput("agent output is not JSON") from None
    schema = json.loads((SCHEMA_DIR / f"{kind}.json").read_text())
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(map(str, e.absolute_path)))
    if errors:
        raise InvalidOutput("; ".join(f"{'/'.join(map(str, e.absolute_path)) or '$'}: {e.message[:200]}" for e in errors))
    return data


def ping_body(data: dict[str, Any], run_url: str) -> str:
    lines = ["<!-- ai-workflows:ping -->", f"🏓 pong: {data['reply']}"]
    if run_url:
        lines += ["", f"[Run]({run_url})"]
    return "\n".join(lines)


def publish(kind: str, raw: str | None, repo: str, issue: int, run_url: str, gh: GhRunner) -> bool:
    """Post the reply when the output is valid; otherwise add `ai: error` and post nothing."""
    try:
        data = validate(kind, raw)
    except InvalidOutput as exc:
        print(f"::error title=Invalid agent output::{exc}")
        gh(["api", "-X", "POST", f"repos/{repo}/issues/{issue}/labels", "-f", f"labels[]={ERROR_LABEL}"])
        return False
    if kind != "ping":
        raise ValueError(f"no publisher for {kind}")
    gh(["api", "-X", "POST", f"repos/{repo}/issues/{issue}/comments", "-f", f"body={ping_body(data, run_url)}"])
    print(f"replied on {repo}#{issue}")
    return True
