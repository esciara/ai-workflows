"""Slash-command parsing and the command-author check (ADR-0005)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

# command -> whether it takes text after it: None = ignored, "optional", "required"
COMMANDS: dict[str, str | None] = {
    "ping": None,
    "review": None,
    "retriage": None,
    "fix": "optional",
    "no-fix": "required",
}
ALLOWED_PERMISSIONS = {"admin", "write"}
# Up to 3 leading spaces; 4+ spaces or a tab is a Markdown code block.
COMMAND_RE = re.compile(r"^ {0,3}/([a-z][a-z-]*)(?:[ \t]+(.*?))?[ \t]*$")

GhRunner = Callable[[list[str]], str]


@dataclass(frozen=True)
class Command:
    name: str
    args: str = ""


def parse(body: str | None) -> Command | None:
    """The command on the first non-blank line of a comment, or None.

    Only the first non-blank line counts, so a command quoted (`>`), fenced (```) or
    buried later in the text is never taken as one.
    """
    if not body:
        return None
    first = next((line for line in body.replace("\r\n", "\n").split("\n") if line.strip()), "")
    m = COMMAND_RE.match(first)
    if not m or m.group(1) not in COMMANDS:
        return None
    name, args = m.group(1), (m.group(2) or "").strip()
    takes = COMMANDS[name]
    if takes is None:
        args = ""
    elif takes == "required" and not args:
        return None
    return Command(name, args)


def repo_permission(repo: str, login: str, gh: GhRunner) -> str:
    """The user's permission on the repo (admin, write, read or none); none when unknown."""
    try:
        out = gh(["api", f"repos/{repo}/collaborators/{login}/permission", "--jq", ".permission"])
    except RuntimeError:
        return "none"  # 404 for non-collaborators and bots
    return out.strip() or "none"


def authorize(login: str, maintainers: list[str], permission: str) -> bool:
    """ADR-0005: in `maintainers` (case-insensitive) AND write or admin on the repo."""
    in_config = login.lower() in {m.lower() for m in maintainers}
    return in_config and permission in ALLOWED_PERMISSIONS


def accept(body: str | None, login: str, maintainers: list[str], repo: str, gh: GhRunner) -> Command | None:
    """The command to run, or None (not a command, or an author who may not issue one)."""
    cmd = parse(body)
    if cmd is None or not login:
        return None
    if login.lower() not in {m.lower() for m in maintainers}:
        return None  # skip the API call for anyone outside the config
    return cmd if authorize(login, maintainers, repo_permission(repo, login, gh)) else None
