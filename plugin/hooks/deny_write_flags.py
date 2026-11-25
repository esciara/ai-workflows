#!/usr/bin/env python3
"""PreToolUse hook: deny git flags that write files or run external programs (--output, --ext-diff, --textconv, -c).

The skills pre-approve `git diff|log|show|blame` by prefix, which also matches these flags. Reads the hook JSON on
stdin; exit 2 with a message on stderr denies the call, any other exit allows it. Only commands that run git are checked.
The command is tokenised like a shell would (quotes and backslashes resolved), a command that cannot be parsed is denied,
and long options are matched by prefix, since git accepts unique abbreviations (`--ext` for `--ext-diff`).
Limit: shell expansion (variables, command substitution) is not resolved.
"""

from __future__ import annotations

import json
import shlex
import sys

LONG = ("--output", "--ext-diff", "--textconv", "--exec-path", "--open-files-in-pager")
MIN_ABBREV = 5  # "--ext", "--outp": git's shortest unique abbreviations are at least this long


def tokens(command: str) -> list[str] | None:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return None


SAFE = {"--text"}  # a real, read-only git option that is also a prefix of --textconv
VALUE_OPTS = {"-C", "--git-dir", "--work-tree", "--namespace", "--super-prefix"}  # global options with a separate value


def denied(command: str) -> str | None:
    toks = tokens(command)
    if toks is None:
        return "ai-workflows plugin: the command could not be parsed, denied" if "git" in command else None
    for i, tok in enumerate(toks):
        if tok != "git" and not tok.endswith("/git"):
            continue
        rest = toks[i + 1:]
        end = next((j for j, t in enumerate(rest) if t and set(t) <= set(";&|()")), len(rest))
        args = rest[:end]
        skip = False
        for arg in args:  # global options come before the subcommand, in any order
            if skip:
                skip = False
            elif arg in VALUE_OPTS:
                skip = True
            elif not arg.startswith("-"):
                break  # the subcommand
            elif arg == "-c" or arg.startswith("--config-env"):
                return f"ai-workflows plugin: `git {arg.split('=')[0]}` is not allowed (read-only, local-only skills)"
        for arg in args:
            name = arg.split("=", 1)[0]
            if (arg.startswith("--") and name not in SAFE and len(name) >= MIN_ABBREV
                    and any(opt.startswith(name) for opt in LONG)):
                return f"ai-workflows plugin: `{name}` is not allowed in git commands (read-only, local-only skills)"
    return None


def main() -> int:
    try:
        command = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    except (ValueError, AttributeError):
        return 0
    reason = denied(command if isinstance(command, str) else "")
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
