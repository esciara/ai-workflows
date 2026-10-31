"""Guardrails for development agents' GitHub access (ADR-0031). Stdlib only: run by the system python3.

- `decide(command)`: the Claude Code `PreToolUse` Bash hook (`scripts/dev/guard-bash`). GitHub writes go through
  `scripts/dev/as-agent` (the agent App); bare `gh` may only read; bare `git push` is blocked; merges, approvals by
  agents, `gh auth token`, pushes to main, force pushes without a lease and remote branch deletion are always blocked.
  A pattern match, not a boundary (the ruleset is): it matches command text, so `echo "gh pr merge"` is blocked too.
- `maintainer_allowed(args)`: the allow-list of `scripts/dev/as-maintainer` (maintainer comments, reviews and the
  labels-sync dispatch, on the playground only).
"""

from __future__ import annotations

import os
import re
import shlex

PLAYGROUND = "esciara/ai-workflows-playground"
FORK = "opinionated-digital-center/ai-workflows-playground"  # fork pushes stay on the maintainer's git (ADR-0031)
WRAPPERS = {"as-agent", "as-tester", "as-maintainer"}
SHELLS = {"bash", "sh", "zsh"}
PREFIXES = {"command", "exec", "env", "sudo", "time", "nohup", "xargs", "builtin"}

# Blocked anywhere in the command text, wrapped or not.
ALWAYS = [
    (re.compile(r"\bgh\b.*\bpr\s+merge\b"), "agents never merge (the maintainer does)"),
    (re.compile(r"\bgh\b.*\bapi\b.*/(pulls/[^/\s]+/merge|merges)\b"), "agents never merge (the maintainer does)"),
    (re.compile(r"\bgh\b.*\bauth\s+token\b|--show-token\b"), "never print a token"),
    (re.compile(r"\bgh\b.*\bapi\b.*\bDELETE\b.*(esciara/ai-workflows|\{owner\}/\{repo\})/"), "no remote deletes on this repo"),
]
APPROVE = re.compile(r"\bgh\b.*(\bpr\s+review\b.*(--approve|\s-a\b)|event=APPROVE)")

GH_READS = {
    "pr": {"view", "list", "diff", "checks", "status"},
    "issue": {"view", "list", "status"},
    "run": {"view", "list", "watch", "download"},
    "repo": {"view", "list"},
    "release": {"view", "list", "download"},
    "label": {"list"},
    "workflow": {"view", "list"},
    "auth": {"status"},
}
GH_READ_GROUPS = {"search", "status", "browse", "help", "version", "--version", "--help"}
API_WRITE_FLAGS = {"-f", "-F", "--field", "--raw-field", "--input"}


def segments(command: str) -> list[list[str]]:
    """Simple commands of `command`, split on shell operators; `bash -c '…'` and `eval …` are expanded."""
    lex = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    try:
        tokens = list(lex)
    except ValueError:  # unbalanced quotes: fall back to a naive split
        tokens = command.split()
    out: list[list[str]] = [[]]
    for t in tokens:
        if t and all(c in "();<>|&" for c in t):
            out.append([])
        else:
            out[-1].append(t.lstrip("$`").rstrip("`"))
    result = []
    for seg in filter(None, out):
        words = strip_prefixes(seg)
        if words and os.path.basename(words[0]) in SHELLS and "-c" in words[1:-1]:
            result += segments(words[words.index("-c") + 1])
        elif words and words[0] == "eval":
            result += segments(" ".join(words[1:]))
        elif words:
            result.append(words)
    return result


def strip_prefixes(words: list[str]) -> list[str]:
    """Drop `VAR=x`, `command`, `env -i`, … in front of the real command."""
    i = 0
    while i < len(words):
        w = words[i]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", w) or w in PREFIXES or (i and w.startswith("-") and words[i - 1] in PREFIXES):
            i += 1
        else:
            break
    return words[i:]


def git_sub(args: list[str]) -> int:
    """Index of the git subcommand in `args` (the words after `git`), skipping `-C dir`, `-c k=v`, …"""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in {"-C", "-c"} else 1
    return i


def git_push_problem(args: list[str]) -> str | None:
    """Why this `git` invocation is a forbidden push, or None. `args` follow `git`, global options included."""
    i = git_sub(args)
    if i >= len(args) or args[i] != "push":
        return None
    rest = args[i + 1:]
    lease = any(a.startswith("--force-with-lease") for a in rest)
    for a in rest:
        if a in {"--force", "--mirror"} or re.fullmatch(r"-[a-zA-Z]*f[a-zA-Z]*", a) and not a.startswith("--"):
            if a == "--mirror" or not lease:
                return "force push without --force-with-lease"
        if a in {"--delete", "-d", "--prune", "--all", "--mirror"} or (a.startswith(":") and len(a) > 1):
            return "remote branch deletion or bulk push"
        if not a.startswith("-") and a.startswith("+") and not lease:
            return "force push without --force-with-lease"
        if not a.startswith("-") and re.search(r"(^|:)(\+?)(refs/heads/)?main$", a):
            return "push to main (open a PR)"
    return None


def gh_is_read(args: list[str]) -> bool:
    words = list(args)
    while words[:1] and words[0] in {"-R", "--repo"}:
        words = words[2:]
    if not words:
        return True
    group = words[0]
    if group in GH_READ_GROUPS:
        return True
    if group == "api":
        method = "GET"
        for j, a in enumerate(words):
            if a in {"-X", "--method"} and j + 1 < len(words):
                method = words[j + 1].upper()
            elif a.startswith(("-X", "--method=")) and a not in {"-X", "--method"}:
                method = a.split("=", 1)[-1][2:] if a.startswith("-X") else a.split("=", 1)[1]
                method = method.upper()
        return method == "GET" and not any(w.split("=")[0] in API_WRITE_FLAGS for w in words) and "graphql" not in words
    return words[1:2] != [] and words[1] in GH_READS.get(group, set())


def decide(command: str) -> tuple[bool, str]:
    """(allowed, reason) for a Bash tool command in a Claude Code session of this repo."""
    for pattern, why in ALWAYS:
        if pattern.search(command):
            return False, why
    via_maintainer = False
    for words in segments(command):
        name = os.path.basename(words[0])
        if name in WRAPPERS:
            via_maintainer |= name == "as-maintainer"
            words = words[1:]
            if words and words[0] in {"gh", "git"}:
                name, words = words[0], words[1:]
            else:
                name = "gh"  # as-tester / as-maintainer take gh args directly
            if name == "git" and (why := git_push_problem(words)):
                return False, why
            continue
        if name == "git":
            if why := git_push_problem(words[1:]):
                return False, why
            sub = words[1:][git_sub(words[1:]):][:1]
            if sub == ["push"] and not any(FORK in w for w in words):
                return False, "git push as the maintainer: use scripts/dev/as-agent git push …"
        elif name == "gh" and not gh_is_read(words[1:]):
            return False, "gh write as the maintainer: use scripts/dev/as-agent gh … (bare gh may only read)"
    if APPROVE.search(command) and not via_maintainer:
        return False, "agents never approve PRs"
    if re.search(r"\bgit\b.*\bpush\b[^;&|]*[\s:/]main(?=$|[\s;&|\"'])", command):
        return False, "push to main (open a PR)"
    return True, ""


def _value(args: list[str], *flags: str) -> list[str]:
    return [args[i + 1] for i, a in enumerate(args[:-1]) if a in flags]


def maintainer_allowed(args: list[str]) -> tuple[bool, str]:
    """Allow-list of `as-maintainer <gh args>`: maintainer comments, PR reviews and approvals, and the labels-sync
    `workflow_dispatch`, on the playground only."""
    a = args[1:] if args[:1] == ["gh"] else list(args)
    if a[:2] in (["issue", "comment"], ["pr", "comment"], ["pr", "review"]):
        if not re.fullmatch(r"\d+", a[2] if len(a) > 2 else ""):
            return False, "needs a PR or issue number"
        if _value(a, "-R", "--repo") != [PLAYGROUND]:
            return False, f"only on {PLAYGROUND} (pass -R {PLAYGROUND})"
        ok = {"-R", "--repo", "-b", "--body"} | ({"--approve", "--comment", "--request-changes"} if a[1] == "review" else set())
        rest = a[3:]
        flags = [x for i, x in enumerate(rest) if x.startswith("-") and not (i and rest[i - 1] in {"-b", "--body", "-R", "--repo"})]
        bad = [f for f in flags if f not in ok]
        return (False, f"flag not allowed: {bad[0]}") if bad else (True, "")
    if a[:1] == ["api"]:
        paths = [x for i, x in enumerate(a[1:], 1) if not x.startswith("-") and a[i - 1] not in {"-X", "--method", "-f", "-F", "--raw-field", "-q", "--jq"}]
        base = rf"repos/{re.escape(PLAYGROUND)}/"
        allowed_paths = [
            (rf"{base}issues/\d+/comments", {"body"}),
            (rf"{base}pulls/\d+/reviews", {"body", "event", "commit_id"}),
            (rf"{base}actions/workflows/\d+/dispatches", {"ref"}),
        ]
        if len(paths) != 1:
            return False, "exactly one API path"
        fields_ok = next((f for p, f in allowed_paths if re.fullmatch(p, paths[0])), None)
        if fields_ok is None:
            return False, f"API path not allowed: {paths[0]}"
        i, method = 1, None
        while i < len(a):
            x = a[i]
            if x in {"-X", "--method"}:
                method, i = a[i + 1] if i + 1 < len(a) else "", i + 2
            elif x in {"-f", "--raw-field"} and i + 1 < len(a) and a[i + 1].split("=")[0] in fields_ok:
                i += 2
            elif x == "-F" and i + 1 < len(a) and a[i + 1] == "return_run_details=true" and "ref" in fields_ok:
                i += 2
            elif x in {"-q", "--jq"} and i + 1 < len(a):
                i += 2
            elif x == paths[0]:
                i += 1
            else:
                return False, f"argument not allowed: {x}"
        return (True, "") if method == "POST" else (False, "needs -X POST")
    return False, "as-maintainer only posts comments, PR reviews/approvals and the labels-sync dispatch on " + PLAYGROUND
