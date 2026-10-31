"""Validate an agent's JSON answer against its schema, then write to GitHub (orchestrator only).

Per-workflow publishers (ADR-0025): each `aiwf.publish_<workflow>` module (commands, review = Workflow A,
triage = Workflow B) exports `PUBLISHERS = {kind: fn(data, repo, issue, run_url, gh)}`; this module validates, then
dispatches by kind. A new workflow adds a module, never a line here. Shared low-level gh helpers live here.
"""

from __future__ import annotations

import importlib
import json
import pkgutil
from functools import cache
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


def comment(gh: GhRunner, repo: str, issue: int, body: str) -> None:
    gh(["api", "-X", "POST", f"repos/{repo}/issues/{issue}/comments", "-f", f"body={body}"])


def add_labels(gh: GhRunner, repo: str, issue: int, *labels: str) -> None:
    gh(["api", "-X", "POST", f"repos/{repo}/issues/{issue}/labels", *[a for lb in labels for a in ("-f", f"labels[]={lb}")]])


Publisher = Callable[[dict[str, Any], str, int, str, GhRunner], None]


@cache
def publishers() -> dict[str, Publisher]:
    """kind -> publisher, collected from every `aiwf.publish_*` module. Two modules claiming one kind is an error."""
    import aiwf

    found: dict[str, Publisher] = {}
    for info in sorted(pkgutil.iter_modules(aiwf.__path__), key=lambda m: m.name):
        if not info.name.startswith("publish_"):
            continue
        for kind, fn in importlib.import_module(f"aiwf.{info.name}").PUBLISHERS.items():
            if kind in found:
                raise RuntimeError(f"publish kind {kind!r} registered twice (aiwf.{info.name})")
            found[kind] = fn
    return found


def publish(kind: str, raw: str | None, repo: str, issue: int, run_url: str, gh: GhRunner) -> bool:
    """Publish when the output is valid; otherwise add `ai: error` and post nothing."""
    publisher = publishers().get(kind)
    if publisher is None:
        raise ValueError(f"no publisher for {kind}")
    try:
        data = validate(kind, raw)
    except InvalidOutput as exc:
        print(f"::error title=Invalid agent output::{exc}")
        add_labels(gh, repo, issue, ERROR_LABEL)
        return False
    publisher(data, repo, issue, run_url, gh)
    return True
