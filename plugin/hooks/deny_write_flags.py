#!/usr/bin/env python3
"""PreToolUse hook: best-effort guard for the skills' pre-approved `git diff|log|show|blame` prefixes.

Reads the hook JSON on stdin; exit 2 with a message on stderr denies the call, exit 0 leaves the normal permission flow.
It guards only commands that start (after leading whitespace) with `git` plus `diff`, `log`, `show` or `blame`; every
other command, including obfuscated spellings of git (`g""it`, `$'g\\151t'`, `g$()it`), is not caught here and relies on
Claude Code's own permission prompt. A guarded command must match, as a whole and on the raw string (no shell parsing),
`git <subcommand>` followed by single-space-separated words made only of [A-Za-z0-9_./:@^~=,+%-]: no quotes, backslashes,
`$`, backticks, braces, redirection, `;|&()`, newlines, tabs or globs. Even then `--output*`, `--ext-diff`, `--textconv`,
`--exec-path`, `--open-files-in-pager`, `-O*` and abbreviations of them are denied.
A non-string command is not gated (exit 0). `-O*` is denied only as a token that starts with `-O`, not inside grouped short flags. It is defence in depth, not a sandbox. If its input is malformed or it hits an error it denies the call (best effort).
"""

from __future__ import annotations

import json
import re
import sys

ALLOWED = re.compile(r"git (?:diff|log|show|blame)(?: [A-Za-z0-9_./:@^~=,+%-]+)*")
GATE = re.compile(r"\s*git\s+(?:diff|log|show|blame)(?![A-Za-z0-9_-])")
LONG = ("--output", "--ext-diff", "--textconv", "--exec-path", "--open-files-in-pager")
MIN_ABBREV = 3  # "--o" is the shortest prefix of a LONG option that we deny


def denied(command: str) -> str | None:
    if not GATE.match(command):
        return None
    command = command.lstrip()
    if not ALLOWED.fullmatch(command):
        return ("ai-workflows plugin: only plain `git diff|log|show|blame <words>` is allowed here (letters, digits and "
                "_./:@^~=,+%- only; no quotes, expansion, pipes, redirection or chaining)")
    for arg in command.split(" ")[2:]:
        name = arg.split("=", 1)[0]
        if arg.startswith("-O") or (name.startswith("--") and len(name) >= MIN_ABBREV
                                    and any(opt.startswith(name) or name.startswith(opt) for opt in LONG)):
            return f"ai-workflows plugin: `{name}` is not allowed in git commands (read-only, local-only skills)"
    return None


def main() -> int:
    try:
        command = json.load(sys.stdin).get("tool_input", {}).get("command", "")
        reason = denied(command if isinstance(command, str) else "")
    except Exception:  # best effort: malformed stdin or any bug denies the call
        print("ai-workflows plugin: hook could not check the command, denied", file=sys.stderr)
        return 2
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
