"""WP16 acceptance test (ADR-0056). Done when: e2e runs execute in parallel on separate slots, each routed only to its
own slot caller, which runs this repo at its own ref `e2e-target-<n>`; the drift test covers the three callers
(tests/e2e/test_callers_match.py).

Gating: needs the playground PR (caller-e2e-<n>.yml, notify-e2e-<n>.yml, labels `e2e-target-<n>`, normal caller gate
= negation of the three slot gates) merged by the maintainer first, then the build PR (aiwf.e2eslot, playground.py).

Run WITHOUT `AIWF_E2E_SLOT` (`AIWF_E2E=1 pytest tests/e2e/test_wp16.py -v`): the test itself holds slots 1 and 2 at the
same time, points each slot's ref at HEAD, and opens one draft PR per slot from an `e2e/<n>/` branch. Draft PRs start
no review, so the only work is each caller's routing gate (`config`): cheap, and enough to prove routing. For each
PR's head commit: exactly one caller ran `config` (its slot's), at `e2e-target-<n>` = the commit pushed; the normal
caller and the other slot callers skipped it.
"""

from __future__ import annotations

import contextlib
import os
import time

import pytest

import playground as pg
from aiwf import e2eslot

SLOTS = (1, 2)


def callers() -> set[str]:
    """The normal caller and the three slot callers (a function: names come from the build PR's aiwf.e2eslot)."""
    return {pg.WORKFLOW, *(e2eslot.workflow_name(n) for n in e2eslot.SLOTS)}


def config_job(jobs: dict[str, str]) -> str | None:
    """Conclusion of the caller's `config` job: `config / load` when it ran, `config` when its `if:` skipped it."""
    return jobs.get("config / load", jobs.get("config"))


def runs_for(sha: str, after: str) -> dict[str, dict]:
    """Caller name -> its completed pull_request run for head `sha`; waits until every caller (normal + 3 slots) ran."""

    def find() -> dict[str, int] | None:
        runs = pg.api(f"repos/{pg.REPO}/actions/runs?event=pull_request&head_sha={sha}&per_page=50")["workflow_runs"]
        hits = {r["name"]: r["id"] for r in runs if r["name"] in callers() and r["created_at"] >= after}
        return hits if set(hits) == callers() else None

    return {name: pg.completed(run_id) for name, run_id in pg.poll(find, f"the caller runs for {sha[:7]}").items()}


def test_two_slots_run_in_parallel_each_routed_to_its_own_caller_and_ref():
    if os.environ.get("AIWF_E2E_SLOT"):
        pytest.fail("run test_wp16 without AIWF_E2E_SLOT: it holds slots 1 and 2 itself (not a pass)", pytrace=False)
    with contextlib.ExitStack() as stack:
        target = {}
        for n in SLOTS:
            print(f"waiting for e2e slot {n} ...")
            assert stack.enter_context(e2eslot.hold(n)) == n
            target[n] = e2eslot.push_target(n)
            print(f"slot {n} held; e2e-target-{n} -> {target[n]}")
        after = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 5))
        prs = {n: stack.enter_context(pg.throwaway_pr(f"[e2e] WP16 slot {n}", e2e=True, wp="wp16", slug=f"slot{n}",
                                                      slot=n, draft=True)) for n in SLOTS}
        for n, pr in prs.items():
            assert pr["branch"].startswith(e2eslot.branch_prefix(n)), pr
            labels = {lb["name"] for lb in pg.api(f"repos/{pg.REPO}/issues/{pr['number']}/labels")}
            assert labels & {e2eslot.label(m) for m in e2eslot.SLOTS} == {e2eslot.label(n)}, labels

        for n, pr in prs.items():
            sha = pg.api(f"repos/{pg.REPO}/pulls/{pr['number']}")["head"]["sha"]
            runs = runs_for(sha, after)
            mine = e2eslot.workflow_name(n)
            for name, run in runs.items():
                jobs = pg.jobs(run["id"])
                print(f"slot {n} PR #{pr['number']}: {name} run {run['id']} {run['html_url']} -> {jobs}")
                want = "success" if name == mine else "skipped"
                assert config_job(jobs) == want, f"{name}: config {config_job(jobs)!r}, expected {want!r}"
            refs = [w for w in runs[mine]["referenced_workflows"] if "/config.yml@" in w["path"]]
            assert [(w["ref"], w["sha"]) for w in refs] == [(e2eslot.target_ref(n), target[n])], refs
