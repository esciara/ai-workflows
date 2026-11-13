"""The playground's callers stay consistent with templates/caller.yml (read-only, no runs, no e2e slot).

Compared (aiwf.callers_match): top-level `permissions`, `permissions` of every job present in both files, and
`concurrency` (cancel-in-progress and group, after `ai-workflows-e2e-` -> `ai-workflows-` for caller-e2e.yml).
Jobs absent from the playground's ai-workflows.yml (review, triage) are skipped on purpose; caller-e2e.yml must
contain config, review, review-fork-push and triage. Past bugs this guards: a review job without `actions: read`
(startup_failure) and a missing comment-concurrency group.
"""

from __future__ import annotations

import base64

import pytest

import playground as pg
from aiwf import e2eslot, policy
from aiwf.callers_match import compare, jobs_of

TEMPLATE = (pg.ROOT / "templates" / "caller.yml").read_text()
E2E_REQUIRED = {"config", "review", "review-fork-push", "triage"}
# Known, accepted gap: caller-e2e.yml's triage job has contents/pull-requests write for the unreleased WP6 e2e tests,
# the template has read. Drop this when WP6 lands and the template catches up.
ALLOWED_DRIFT = ("job 'triage' permissions differ: caller {'contents': 'write', 'issues': 'write', "
                 "'pull-requests': 'write'}, template {'contents': 'read', 'issues': 'write', 'pull-requests': 'read'}",)


def playground_file(name: str) -> str:
    f = pg.api(f"repos/{pg.REPO}/contents/.github/workflows/{name}")
    return base64.b64decode(f["content"]).decode()


def test_normal_caller_matches_template():
    problems = compare(TEMPLATE, playground_file("ai-workflows.yml"))
    assert not problems, "\n".join(problems)


def _gate(text: str, job: str = "config") -> str:
    """The job's `if:` with `${{ }}` stripped and whitespace collapsed."""
    raw = str(policy.load_workflow(text)["jobs"][job].get("if", "")).strip()
    raw = raw.removeprefix("${{").removesuffix("}}") if raw.startswith("${{") else raw
    return " ".join(raw.split())


@pytest.mark.parametrize("n", [1, 2, 3])
def test_slot_caller_matches_template(n):
    text = playground_file(e2eslot.caller_file(n))
    missing = E2E_REQUIRED - jobs_of(text)
    assert not missing, f"{e2eslot.caller_file(n)} lacks jobs {sorted(missing)}"
    problems = [p for p in compare(TEMPLATE, text, (e2eslot.group_prefix(n), "ai-workflows-")) if p not in ALLOWED_DRIFT]
    assert not problems, "\n".join(problems)
    assert _gate(text) == e2eslot.gate(n)


def test_slot_callers_are_identical_after_slot_substitution():
    for name in (e2eslot.caller_file, e2eslot.notify_file):
        texts = {n: e2eslot.unslot(playground_file(name(n)), n) for n in e2eslot.SLOTS}
        assert texts[1] == texts[2] == texts[3], f"{name(1)}, {name(2)}, {name(3)} differ beyond the slot number"


def test_normal_caller_gate_is_the_negation_of_the_slot_gates():
    assert _gate(playground_file("ai-workflows.yml")) == e2eslot.normal_gate()


def test_slot_labels_exist_and_the_single_slot_is_gone():
    names = {lb["name"] for lb in pg.api(f"repos/{pg.REPO}/labels?per_page=100")}
    assert {e2eslot.label(n) for n in e2eslot.SLOTS} <= names
    files = {f["name"] for f in pg.api(f"repos/{pg.REPO}/contents/.github/workflows")}
    assert not {"caller-e2e.yml", "notify-e2e.yml"} & files
