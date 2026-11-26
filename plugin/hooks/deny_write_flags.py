#!/usr/bin/env python3
"""PreToolUse hook: best-effort guard for the skills' pre-approved `git diff|log|show|blame` prefixes.

Reads the hook JSON on stdin; exit 2 with a message on stderr denies the call, exit 0 leaves the normal permission flow.
A command that does not mention both `git` and one of diff, log, show, blame (quotes, backslashes and newlines ignored) is not this hook's business (exit 0).
Any other command that mentions them must match, as a whole and on the raw string (no shell parsing), the strict form
`git <diff|log|show|blame>` followed by single-space-separated words made only of [A-Za-z0-9_./:@^~=,+-]. That rules out
quotes, backslashes, `$`, backticks, braces, redirections, process substitution, `;|&()`, newlines, tabs and globs, so no
shell feature can hide a flag. Even in that character set, `--output*`, `--ext-diff`, `--textconv`, `--exec-path`,
`--open-files-in-pager`, `-O*` and abbreviations of them (`--out`, `--ext`, `--text`) are denied.
It is defence in depth, not a sandbox. It fails closed: malformed input or an internal error denies the call.
"""

from __future__ import annotations

import json
import re
import sys

ALLOWED = re.compile(r"git (?:diff|log|show|blame)(?: [A-Za-z0-9_./:@^~=,+-]+)*")
OBFUSCATION = re.compile(r"[\\\\\"'\n]")
MENTIONS = re.compile(r"git")
SUBCOMMANDS = re.compile(r"diff|log|show|blame")
LONG = ("--output", "--ext-diff", "--textconv", "--exec-path", "--open-files-in-pager")
MIN_ABBREV = 3  # "--o" is the shortest prefix of a LONG option that we deny


def denied(command: str) -> str | None:
    plain = OBFUSCATION.sub("", command)  # so that `g""it`, `gi\\<newline>t` or `di\\<newline>ff` still count as mentions
    if not (MENTIONS.search(plain) and SUBCOMMANDS.search(plain)):
        return None
    if not ALLOWED.fullmatch(command):
        return ("ai-workflows plugin: only plain `git diff|log|show|blame <words>` is allowed here (letters, digits and "
                "_./:@^~=,+- only; no quotes, expansion, pipes, redirection or chaining)")
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
    except Exception:  # fail closed: malformed stdin or any bug denies the call
        print("ai-workflows plugin: hook could not check the command, denied", file=sys.stderr)
        return 2
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
