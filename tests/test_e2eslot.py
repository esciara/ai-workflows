"""WP16 unit tests: three fixed e2e slots (ADR-0056), written before the build against the proposed interface of
`aiwf.e2eslot`. Expected red until the build PR: every test is a strict xfail, so main stays green and the build PR
must drop the marker (a strict xfail that passes fails the run).

Proposed interface (aiwf.e2eslot):
- `SLOTS = (1, 2, 3)`; `parse_slot(value)` reads `AIWF_E2E_SLOT`: '1'|'2'|'3' -> int, 'any' -> 'any', unset -> None.
- `lock_path(n)`: `aiwf-e2e-<n>.lock` in `$AIWF_E2E_LOCK_DIR`, else in the git common dir.
- `hold(slot, timeout, poll)`: context manager yielding the slot number held; `'any'` takes the first free slot and
  waits while all three are busy; `SlotBusy` after `timeout`.
- `push_target(n, ref, remote, cwd)`: points `e2e-target-<n>` at `ref` with a lease; needs slot `n` held.
- Names derived from `n`: `label`, `branch_prefix`, `workflow_name`, `notify_workflow_name`, `caller_file`,
  `notify_file`, `group_prefix`, `target_ref`; `gate(n)` and `normal_gate()` (routing `if:` bodies); `unslot`.
- `held(env)`: (slot, sha) the controller exported to xdist workers (`AIWF_E2E_SLOT_HELD`, `AIWF_E2E_TARGET_SHA`);
  raises `NoSlot` otherwise. The `e2e_target` fixture calls it and fails the test on `NoSlot`.
"""

import os
import signal
import subprocess
import sys

import pytest

from aiwf import e2eslot

pytestmark = pytest.mark.xfail(strict=True, reason="WP16: three e2e slots, built in the build PR (ADR-0056)")

HOLDER = "import sys, time; from aiwf import e2eslot\n" \
         "with e2eslot.hold(sys.argv[1] if sys.argv[1] == 'any' else int(sys.argv[1])) as n:\n" \
         "    print(f'held {n}', flush=True); time.sleep(60)\n"


@pytest.fixture
def lock_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AIWF_E2E_LOCK_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def holders(lock_dir):
    """Start holder processes on a slot ('1'..'3' or 'any'); returns (start, the slot each one got). Killed at exit."""
    procs = []
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}

    def start(slot: str) -> tuple[subprocess.Popen, int]:
        p = subprocess.Popen([sys.executable, "-c", HOLDER, slot], stdout=subprocess.PIPE, text=True, env=env)
        procs.append(p)
        line = p.stdout.readline().strip()
        assert line.startswith("held "), line
        return p, int(line.split()[1])

    yield start
    for p in procs:
        p.kill()
        p.wait()


@pytest.mark.parametrize("value,want", [("1", 1), ("2", 2), ("3", 3), ("any", "any"), (None, None), ("", None)])
def test_parse_slot(value, want):
    assert e2eslot.parse_slot(value) == want


@pytest.mark.parametrize("value", ["0", "4", "one", "ANY ", "1,2"])
def test_parse_slot_rejects_anything_else(value):
    with pytest.raises(ValueError, match="AIWF_E2E_SLOT"):
        e2eslot.parse_slot(value)


def test_one_lock_file_per_slot_with_env_override(lock_dir):
    assert e2eslot.SLOTS == (1, 2, 3)
    assert [e2eslot.lock_path(n) for n in e2eslot.SLOTS] == [lock_dir / f"aiwf-e2e-{n}.lock" for n in (1, 2, 3)]


def test_lock_files_default_to_the_git_common_dir(monkeypatch):
    monkeypatch.delenv("AIWF_E2E_LOCK_DIR", raising=False)
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=e2eslot.ROOT,
                            capture_output=True, text=True, check=True).stdout.strip()
    assert e2eslot.lock_path(2) == (e2eslot.ROOT / common).resolve() / "aiwf-e2e-2.lock"


def test_a_busy_slot_blocks_only_itself(holders):
    holders("2")
    with pytest.raises(e2eslot.SlotBusy, match="pid"):
        with e2eslot.hold(2, timeout=0):
            pass
    for n in (1, 3):
        with e2eslot.hold(n, timeout=0) as got:
            assert got == n


def test_any_takes_the_first_free_slot(holders):
    _, first = holders("any")
    _, second = holders("any")
    assert (first, second) == (1, 2)
    with e2eslot.hold("any", timeout=0) as got:
        assert got == 3


def test_any_waits_when_all_slots_are_busy_and_gets_the_freed_one(holders):
    procs = {n: holders(str(n))[0] for n in e2eslot.SLOTS}
    with pytest.raises(e2eslot.SlotBusy):
        with e2eslot.hold("any", timeout=0):
            pass
    procs[2].send_signal(signal.SIGKILL)  # the kernel releases the flock: no cleanup step
    procs[2].wait()
    with e2eslot.hold("any", timeout=5, poll=0.1) as got:
        assert got == 2


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def test_push_target_moves_only_its_slot_ref_and_needs_that_slot(tmp_path, lock_dir):
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    git("init", "--bare", "-q", str(remote), cwd=tmp_path)
    git("init", "-q", str(work), cwd=tmp_path)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "one", cwd=work)
    with e2eslot.hold(1, timeout=0):
        with pytest.raises(RuntimeError, match="slot 2"):
            e2eslot.push_target(2, remote=str(remote), cwd=work)
        sha = e2eslot.push_target(1, remote=str(remote), cwd=work)
    assert git("rev-parse", "e2e-target-1", cwd=remote) == sha
    assert git("for-each-ref", "--format=%(refname)", cwd=remote) == "refs/heads/e2e-target-1"


@pytest.mark.parametrize("n", [1, 2, 3])
def test_names_derive_from_the_slot_number(n):
    assert e2eslot.target_ref(n) == f"refs/heads/e2e-target-{n}"
    assert e2eslot.label(n) == f"e2e-target-{n}"
    assert e2eslot.branch_prefix(n) == f"e2e/{n}/"
    assert e2eslot.workflow_name(n) == f"AI workflows (e2e {n})"
    assert e2eslot.notify_workflow_name(n) == f"AI workflows notify (e2e {n})"
    assert e2eslot.caller_file(n) == f"caller-e2e-{n}.yml"
    assert e2eslot.notify_file(n) == f"notify-e2e-{n}.yml"
    assert e2eslot.group_prefix(n) == f"ai-workflows-e2e-{n}-"


@pytest.mark.parametrize("n", [0, 4, "any"])
def test_names_reject_a_non_slot(n):
    with pytest.raises(ValueError):
        e2eslot.label(n)


def test_slot_gate_and_normal_gate():
    assert e2eslot.gate(2) == ("(startsWith(github.head_ref, 'e2e/2/') && github.event.pull_request.head.repo.full_name"
                               " == github.repository) || contains(github.event.pull_request.labels.*.name, "
                               "'e2e-target-2') || contains(github.event.issue.labels.*.name, 'e2e-target-2')")
    assert e2eslot.normal_gate() == "!(" + " || ".join(f"({e2eslot.gate(n)})" for n in e2eslot.SLOTS) + ")"
    assert len({e2eslot.unslot(e2eslot.gate(n), n) for n in e2eslot.SLOTS}) == 1


def test_unslot_replaces_every_slot_name_and_nothing_else():
    text = ("name: AI workflows (e2e 3)\ngroup: ai-workflows-e2e-3-x\nuses: o/r/.github/workflows/c.yml@e2e-target-3\n"
            "if: startsWith(github.head_ref, 'e2e/3/') || contains(labels, 'e2e-target-3')\ncron: '3 3 * * *'\n")
    assert e2eslot.unslot(text, 3) == (
        "name: AI workflows (e2e N)\ngroup: ai-workflows-e2e-N-x\nuses: o/r/.github/workflows/c.yml@e2e-target-N\n"
        "if: startsWith(github.head_ref, 'e2e/N/') || contains(labels, 'e2e-target-N')\ncron: '3 3 * * *'\n")


def test_held_needs_a_slot_and_a_sha():
    with pytest.raises(e2eslot.NoSlot, match=r"AIWF_E2E_SLOT=1\|2\|3\|any"):
        e2eslot.held({})
    with pytest.raises(e2eslot.NoSlot):
        e2eslot.held({"AIWF_E2E_SLOT_HELD": "2"})
    assert e2eslot.held({"AIWF_E2E_SLOT_HELD": "2", "AIWF_E2E_TARGET_SHA": "abc123"}) == (2, "abc123")
