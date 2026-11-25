"""WP13: the contributor plugin (level 0) stays read-only and installable, and the contributor guide matches it."""

from __future__ import annotations

import json
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


READ_COMMANDS = {f"git {s}" for s in ("diff", "log", "show", "status", "merge-base", "rev-parse", "branch", "blame")} | {
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
