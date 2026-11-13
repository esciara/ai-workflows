import os

import pytest

import playground as pg  # noqa: F401  (puts the e2e helpers on the path for every e2e module)
from aiwf import e2eslot


def pytest_collection_modifyitems(config, items):
    if os.environ.get("AIWF_E2E") == "1":
        return
    skip = pytest.mark.skip(reason="end-to-end test: set AIWF_E2E=1 to run against the playground")
    for item in items:
        if "/e2e/" in str(item.fspath):
            item.add_marker(skip)


def pytest_configure(config):
    """With AIWF_E2E_SLOT=1|2|3|any, the controller process takes that e2e slot (ADR-0056) for the whole run and points
    `e2e-target-<n>` at HEAD. xdist workers inherit AIWF_E2E_SLOT_HELD and AIWF_E2E_TARGET_SHA; the `e2e_target`
    fixture and the playground helpers read them."""
    if os.environ.get("AIWF_E2E") != "1" or hasattr(config, "workerinput"):
        return
    try:
        slot = e2eslot.parse_slot(os.environ.get("AIWF_E2E_SLOT"))
    except ValueError as e:
        raise pytest.UsageError(str(e)) from None
    if slot is None:
        return
    held = e2eslot.hold(slot)
    print(f"waiting for e2e slot {slot} ...")
    n = held.__enter__()
    config.add_cleanup(lambda: held.__exit__(None, None, None))
    sha = e2eslot.push_target(n, remote=os.environ.get("AIWF_E2E_REMOTE", "origin"))
    os.environ.update({e2eslot.HELD_ENV: str(n), e2eslot.SHA_ENV: sha})
    print(f"e2e slot {n} held; e2e-target-{n} -> {sha}")


@pytest.fixture
def e2e_target() -> str:
    """The commit `e2e-target-<n>` points at for this run; fails the test unless the run holds a slot."""
    try:
        return e2eslot.held()[1]
    except e2eslot.NoSlot as e:
        pytest.fail(str(e), pytrace=False)
