"""CODEOWNERS keeps the guard, policy and trust-boundary files owned by the maintainer (ADR-0060)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "/.github/CODEOWNERS",
    "/scripts/dev/guard-bash",
    "/scripts/dev/as-*",
    "/scripts/aiwf/devguard.py",
    "/.claude/settings.json",
    "/.claude/skills/",
    "/prompts/dev-reviewer.md",
    "/scripts/aiwf/policy.py",
    "/scripts/aiwf/commands.py",
    "/scripts/aiwf/review_gate.py",
    "/tests/test_devguard.py",
    "/tests/test_as_agent.py",
    "/tests/test_workflow_policy.py",
    "/tests/test_codeowners.py",
]


def owners() -> dict[str, list[str]]:
    rules = {}
    for line in (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            path, *who = line.split()
            rules[path] = who
    return rules


def test_exception_paths_owned_by_maintainer():
    rules = owners()
    for dropped in ("/.github/", "/docs/spec.md", "/tests/e2e/test_wp*.py"):
        assert dropped not in rules, f"ADR-0060: {dropped} no longer needs per-PR approval"
    assert {p: rules.get(p) for p in REQUIRED} == {p: ["@esciara"] for p in REQUIRED}


def test_owned_paths_exist():
    for pattern in owners():
        rel = pattern.lstrip("/").rstrip("/")
        assert list(ROOT.glob(rel)), f"CODEOWNERS pattern matches nothing: {pattern}"
