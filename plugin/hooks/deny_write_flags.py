#!/usr/bin/env python3
"""PreToolUse hook: deny git flags that write files or run external programs (--output, --ext-diff, --textconv, -c).

The skills pre-approve `git diff|log|show|blame` by prefix, which also matches these flags. Reads the hook JSON on
stdin; exit 2 with a message on stderr denies the call, any other exit allows it. Only commands that run git are checked.
"""

from __future__ import annotations

import json
import re
import sys

GIT = re.compile(r"(^|[;&|(`\s])git\s")
FLAG = re.compile(r"(^|\s)(--output(=|\s|$)|--ext-diff\b|--textconv\b|-o\s|-c\s|--exec-path\b|--open-files-in-pager\b)")


def denied(command: str) -> str | None:
    if GIT.search(command) and (m := FLAG.search(command)):
        return f"ai-workflows plugin: `{m.group(2).strip()}` is not allowed in git commands (read-only, local-only skills)"
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
