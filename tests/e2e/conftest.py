import os

import pytest

import playground as pg
from aiwf import e2eslot


def pytest_collection_modifyitems(config, items):
    if os.environ.get("AIWF_E2E") == "1":
        return
    skip = pytest.mark.skip(reason="end-to-end test: set AIWF_E2E=1 to run against the playground")
    for item in items:
        if "/e2e/" in str(item.fspath):
            item.add_marker(skip)


FIXTURE_TITLE = "[e2e] WP1 /ping fixture"


@pytest.fixture
def fixture_issue(request) -> dict:
    """A reusable test-fixture issue per test (found by title, created once). Never deleted.

    One issue per test because the caller serialises runs per issue (its `concurrency` group): tests sharing an issue
    would queue behind each other when run in parallel (`-n auto`, pytest-xdist).
    """
    title = f"{FIXTURE_TITLE} ({request.node.originalname})"
    return pg.reusable_issue(title, "Reusable fixture for tests/e2e/test_wp1.py in esciara/ai-workflows.", e2e=False)


@pytest.fixture
def throwaway_pr():
    """A test-fixture PR on its own branch; branch deleted (and PR closed) in teardown."""
    with pg.throwaway_pr("[e2e] WP1 /ping on a PR", e2e=False) as pr:
        yield pr


def pytest_configure(config):
    """With AIWF_E2E_SLOT=1, the controller process takes the e2e slot for the whole run and points `e2e-target` at
    HEAD (ADR-0026, ADR-0028). xdist workers inherit AIWF_E2E_TARGET_SHA; the `e2e_target` fixture checks it."""
    if os.environ.get("AIWF_E2E") != "1" or os.environ.get("AIWF_E2E_SLOT") != "1" or hasattr(config, "workerinput"):
        return
    slot = e2eslot.hold()
    print(f"waiting for the e2e slot {e2eslot.lock_path()} ...")
    slot.__enter__()
    config.add_cleanup(lambda: slot.__exit__(None, None, None))
    os.environ["AIWF_E2E_TARGET_SHA"] = e2eslot.push_target(remote=os.environ.get("AIWF_E2E_REMOTE", "origin"))
    print(f"e2e slot held; e2e-target -> {os.environ['AIWF_E2E_TARGET_SHA']}")


@pytest.fixture
def e2e_target() -> str:
    """The commit `e2e-target` points at for this run; fails the test unless the run holds the slot."""
    sha = os.environ.get("AIWF_E2E_TARGET_SHA")
    if not sha:
        pytest.fail("this test needs the e2e slot: run with AIWF_E2E_SLOT=1 (not a pass)", pytrace=False)
    return sha
