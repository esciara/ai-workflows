"""WP13: the contributor plugin (level 0) stays read-only and installable, and the contributor guide matches it."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"
SKILLS = ("review", "analyse")


def frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, "no frontmatter"
    return dict(line.split(": ", 1) for line in m.group(1).splitlines())


def allowed(name: str) -> list[str]:
    fm = frontmatter((PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8"))
    return re.findall(r"[A-Za-z]+(?:\([^)]*\))?", fm["allowed-tools"])


def test_manifest_and_marketplace_are_valid_and_point_at_the_plugin():
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "ai-workflows" and manifest["version"] and manifest["description"]
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    (entry,) = market["plugins"]
    assert entry["name"] == manifest["name"] and (ROOT / entry["source"]).resolve() == PLUGIN.resolve()


@pytest.mark.parametrize("name", SKILLS)
def test_skill_has_frontmatter_and_the_hard_rules(name):
    text = (PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    fm = frontmatter(text)
    assert fm["name"] == name and fm["description"]
    assert "Never post" in text and "data, never instructions" in text and "Suspicious instructions" in text
    assert "--output" in text and "--ext-diff" in text and "git push" in text


@pytest.mark.parametrize("name", SKILLS)
def test_skill_tools_are_read_only(name):
    tools = allowed(name)
    assert {"Read", "Grep", "Glob"} <= set(tools)
    banned = {"Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch", "Agent", "Bash"}
    assert not banned & set(tools), "bare or writing tools are not allowed: use scoped Bash(...) entries"
    for tool in tools:
        if tool.startswith("Bash"):
            m = re.fullmatch(r"Bash\((git \w[\w-]*|gh issue view):\*\)", tool)
            assert m and m.group(1) in READ_COMMANDS, f"{tool} is not a known read-only command"


READ_COMMANDS = {f"git {s}" for s in ("diff", "log", "show", "status", "merge-base", "rev-parse", "blame")} | {
    "gh issue view"}


def test_review_cannot_use_gh_and_analyse_only_reads_issues():
    assert not [t for t in allowed("review") if t.startswith("Bash(gh")]
    assert [t for t in allowed("analyse") if t.startswith("Bash(gh")] == ["Bash(gh issue view:*)"]
    assert not any(w in " ".join(allowed("review")) for w in ("push", "commit", "checkout"))


def test_contributor_guide_covers_both_levels_and_the_plugin_commands():
    guide = (ROOT / "docs" / "contributor.md").read_text(encoding="utf-8")
    for needle in ("Level 0", "Level 1", "/ai-workflows:review", "/ai-workflows:analyse", "/plugin marketplace add esciara/ai-workflows",
                   "upstream", "AI policy", "templates/caller.yml", "CLAUDE_CODE_OAUTH_TOKEN"):
        assert needle in guide, needle
    assert not re.search(r"@(main|master)\b", guide), "the guide must not tell people to pin to a branch"


def hook():
    spec = importlib.util.spec_from_file_location("deny_write_flags", PLUGIN / "hooks" / "deny_write_flags.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_hook_is_registered_for_bash_and_the_script_exists():
    cfg = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    (entry,) = cfg["hooks"]["PreToolUse"]
    assert entry["matcher"] == "Bash"
    assert "${CLAUDE_PLUGIN_ROOT}/hooks/deny_write_flags.py" in entry["hooks"][0]["command"]


CANDIDATES = [
    "git diff --output=/tmp/x main...HEAD", "git diff --output /tmp/x", "git log --ext-diff -p", "git show --textconv HEAD:a",
    "git -c core.pager=evil diff", "cd x && git diff --output=y", 'git diff "--output=/tmp/x" main...HEAD',
    "git log -p '--output'=/tmp/x", "git diff \\--output=/tmp/x", 'git diff --out""put=/tmp/x', "git diff --ext main...HEAD",
    "git log -p --ext-dif", "git -C . -c diff.external=sh diff", "git --attr-source HEAD -c diff.external=sh diff", "git --no-pager -c core.pager=x log",
    "git --config-env=diff.external=E diff", 'g""it diff --output=/tmp/x', "git diff --textc HEAD", "git diff 'unterminated", "ls; git show --output=a HEAD",
    "git diff $'--output=/x' main", "git diff $(printf -- --output)=x main", "git log `echo --output`=x", 'git diff "$FLAG" main',
    "git log --grep ';' --output=OUT", "git --namespace '&&' diff --output=OUT", "git diff -G '|' --output=OUT",
    "git diff {--output=OUT,HEAD}", "git diff --out\\\nput=OUT", "git di\\\nff --output=OUT", "gi\\\nt diff --output=OUT",
    "git diff --output=OUT", "git diff <(touch OUT)", "git diff >(cat)", "git log -S ')' --output=OUT",
    "GIT_EXTERNAL_DIFF=x git diff", "$'git' diff", "git diff main | cat", "git diff main; id", "git diff\tmain", "git diff main\n", "git  diff",
    "git diff -Oorder", "git diff --text main", "git diff *", "git diff a > out", "git diff --output-indicator-new=+",
]


GUARDED = re.compile(r"\s*git\s+(diff|log|show|blame)(\s|$)")
DENIED = [c for c in CANDIDATES if GUARDED.match(c)]
NOT_CAUGHT = [c for c in CANDIDATES if not GUARDED.match(c)]


def test_the_guarded_cases_are_not_empty():
    assert len(DENIED) > 25 and NOT_CAUGHT


@pytest.mark.parametrize("command", DENIED)
def test_hook_denies_guarded_commands_that_are_not_the_strict_form(command):
    assert run_hook(command).returncode == 2


@pytest.mark.parametrize("command", NOT_CAUGHT + ["g$()it diff --output=OUT", "$'g\\151t' diff --output=OUT", "GIT diff --output=OUT", "g*t diff --output=OUT"])
def test_documented_limit_obfuscated_or_prefixed_commands_are_not_caught(command):
    assert run_hook(command).returncode == 0  # left to Claude Code's own permission prompt


@pytest.mark.parametrize("command", [
    "git diff main...HEAD", "git log --oneline main..HEAD", "git show HEAD:cart.py", "gh issue view 12 --comments",
    "git merge-base main HEAD", "ls -o", "grep -c foo a", "git diff --exit-code main", "git log -c -1", "git show -c HEAD",
    "git blame -L 1,5 src/a.py", "git log --format=%H -n 3", "git rev-parse --show-toplevel", "git status --short", "git merge-base main HEAD", "gh issue view 7", "git diff HEAD~1 -- src/a.py", 'echo "hello"', "git commit -m x",
])
def test_hook_allows_plain_reads_and_ignores_unrelated_commands(command):
    assert run_hook(command).returncode == 0


def run_hook(command: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(PLUGIN / "hooks" / "deny_write_flags.py")], capture_output=True,
                          text=True, input=json.dumps({"tool_input": {"command": command}}))


def test_hook_process_exits_2_with_a_message_to_deny_and_0_to_allow():
    denied = run_hook("git diff --output=x")
    assert denied.returncode == 2 and "--output" in denied.stderr
    assert run_hook("git diff main...HEAD").returncode == 0
    assert run_hook("").returncode == 0


def test_hook_fails_closed_on_malformed_stdin():
    for bad in ("not json", "[]", ""):
        res = subprocess.run([sys.executable, str(PLUGIN / "hooks" / "deny_write_flags.py")], capture_output=True, text=True, input=bad)
        assert res.returncode == 2 and res.stderr
