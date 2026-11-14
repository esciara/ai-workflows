"""Pinning rules checked without the network: the docker image rule, and the WP14 static checks of the caller template
and the install guide (the offline half of tests/e2e/test_wp14.py)."""

import re
from pathlib import Path

import pytest

from aiwf import policy

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64


def pin_errors(uses: str) -> list[str]:
    text = f"on: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    permissions: {{contents: read}}\n    steps:\n      - uses: {uses}\n"
    return policy.pin_errors(text)


@pytest.mark.parametrize("ref", [f"docker://alpine@{DIGEST}", f"docker://ghcr.io/o/img:1.2@{DIGEST} # v1.2"])
def test_docker_image_with_digest_passes(ref):
    assert pin_errors(ref) == []


@pytest.mark.parametrize("ref", ["docker://alpine:3.20", "docker://alpine", "docker://ghcr.io/o/img:latest",
                                 f"docker://alpine@sha1:{'c' * 40}"])
def test_docker_image_without_sha256_digest_is_unpinned(ref):
    [err] = pin_errors(ref)
    assert err.startswith("unpinned: line 7: ") and "needs @sha256 digest" in err


@pytest.mark.parametrize("uses,problem", [
    (f"o/a@{SHA}", "needs a '# vX' version comment"),
    ("o/a@v4 # v4", "needs a 40-hex commit SHA"),
    ("o/a@main", "needs a 40-hex commit SHA"),
])
def test_action_refs_need_a_sha_and_a_version_comment(uses, problem):
    [err] = pin_errors(uses)
    assert problem in err


def test_action_pinned_with_sha_and_version_passes_and_local_refs_are_exempt():
    assert pin_errors(f"o/a@{SHA} # v4.1.0") == []
    assert pin_errors("./local-action") == []


# --- WP14 static checks (offline twin of tests/e2e/test_wp14.py) ---------------------------------------------------

OWN_USES_RE = re.compile(r"^\s*uses:\s*esciara/ai-workflows/(\.github/workflows/[\w.-]+\.yml)@(\S+)[ \t]*(#.*)?$", re.M)
TAG_RE = re.compile(r"#\s*(v\d+\.\d+\.\d+)\s*$")
TEMPLATE = (ROOT / "templates" / "caller.yml").read_text()


def test_caller_template_pins_every_own_workflow_to_one_release_sha():
    assert "@main" not in TEMPLATE
    uses = OWN_USES_RE.findall(TEMPLATE)
    assert uses, "no `uses: esciara/ai-workflows/...` line in the template"
    pins = set()
    for path, ref, comment in uses:
        assert re.fullmatch(r"[0-9a-f]{40}", ref), f"{path} is pinned to {ref!r}, not a full commit SHA"
        tag = TAG_RE.search(comment or "")
        assert tag, f"{path} has no `# vX.Y.Z` version comment"
        pins.add((ref, tag.group(1)))
    assert len(pins) == 1, f"the template mixes releases: {sorted(pins)}"
    assert policy.pin_errors(TEMPLATE) == []  # the policy agrees: own refs are checked like any action


GUIDE_MUST_NAME = {
    "the model token secret": "CLAUDE_CODE_OAUTH_TOKEN",
    "how to get the model token": "claude setup-token",
    "the caller template": "templates/caller.yml",
    "where the caller goes": ".github/workflows/ai-workflows.yml",
    "the config template": "templates/ai-workflows.example.yml",
    "where the config goes": ".github/ai-workflows.yml",
    "the setting that stays off": "Allow GitHub Actions to create and approve pull requests",
}


def test_install_guide_covers_the_rights_checklist_and_pins_releases():
    guide = (ROOT / "docs" / "install.md").read_text()
    assert [what for what, text in GUIDE_MUST_NAME.items() if text not in guide] == []
    setting = [line for line in guide.splitlines() if GUIDE_MUST_NAME["the setting that stays off"] in line]
    assert any(re.search(r"\b(off|unticked|unchecked|disabled)\b", line, re.I) for line in setting)
    assert "@main" not in guide
    assert re.search(r"\b(tag|release)\b", guide, re.I) and re.search(r"\bSHA\b", guide)
