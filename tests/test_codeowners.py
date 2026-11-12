"""CODEOWNERS keeps the ADR-0051 exception paths owned by the maintainer."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "/.github/",
    "/docs/spec.md",
    "/tests/e2e/test_wp*.py",
    "/scripts/dev/guard-bash",
    "/scripts/dev/as-*",
    "/scripts/aiwf/devguard.py",
    "/.claude/settings.json",
    "/scripts/aiwf/policy.py",
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
    assert {p: rules.get(p) for p in REQUIRED} == {p: ["@esciara"] for p in REQUIRED}


def test_owned_paths_exist():
    for pattern in owners():
        rel = pattern.lstrip("/").rstrip("/")
        assert list(ROOT.glob(rel)), f"CODEOWNERS pattern matches nothing: {pattern}"
