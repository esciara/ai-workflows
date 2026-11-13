"""Three fixed e2e slots (ADR-0056): slot `n` (1, 2, 3) is a `flock` on `aiwf-e2e-<n>.lock` on this Mac, held while a
run points `e2e-target-<n>` at its commit. The playground's `caller-e2e-<n>.yml` runs this repo at that ref for items
routed to slot `n` (label `e2e-target-<n>`, or a same-repo PR from an `e2e/<n>/` branch).

The kernel drops a lock when the holding process dies, so a crashed run never needs a cleanup step.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import re
import subprocess
import time
from pathlib import Path
from typing import IO, Iterator, Mapping

ROOT = Path(__file__).resolve().parents[2]
SLOTS = (1, 2, 3)
USAGE = "AIWF_E2E_SLOT=1|2|3|any"
HELD_ENV, SHA_ENV = "AIWF_E2E_SLOT_HELD", "AIWF_E2E_TARGET_SHA"  # exported by the controller to xdist workers
_held: set[int] = set()


class SlotBusy(Exception):
    pass


class NoSlot(Exception):
    pass


def parse_slot(value: str | None) -> int | str | None:
    """`AIWF_E2E_SLOT`: '1'|'2'|'3' -> that slot, 'any' -> 'any', unset or empty -> None."""
    if not value:
        return None
    if value == "any":
        return "any"
    if value in {str(n) for n in SLOTS}:
        return int(value)
    raise ValueError(f"{USAGE} expected, got AIWF_E2E_SLOT={value!r}")


def _slot(n: object) -> int:
    if isinstance(n, bool) or n not in SLOTS:
        raise ValueError(f"not an e2e slot: {n!r} (slots are {SLOTS})")
    return n  # type: ignore[return-value]


def target_ref(n: int) -> str:
    return f"refs/heads/e2e-target-{_slot(n)}"


def label(n: int) -> str:
    return f"e2e-target-{_slot(n)}"


def branch_prefix(n: int) -> str:
    return f"e2e/{_slot(n)}/"


def workflow_name(n: int) -> str:
    return f"AI workflows (e2e {_slot(n)})"


def notify_workflow_name(n: int) -> str:
    return f"AI workflows notify (e2e {_slot(n)})"


def caller_file(n: int) -> str:
    return f"caller-e2e-{_slot(n)}.yml"


def notify_file(n: int) -> str:
    return f"notify-e2e-{_slot(n)}.yml"


def group_prefix(n: int) -> str:
    return f"ai-workflows-e2e-{_slot(n)}-"


def gate(n: int) -> str:
    """Body of slot `n`'s routing `if:` (its caller's `config` job): a same-repo PR from an `e2e/<n>/` branch, or an
    item labelled `e2e-target-<n>` (comment payloads have no head ref, so a PR's comments route by label)."""
    return (f"(startsWith(github.head_ref, '{branch_prefix(n)}') && github.event.pull_request.head.repo.full_name == "
            f"github.repository) || contains(github.event.pull_request.labels.*.name, '{label(n)}') || "
            f"contains(github.event.issue.labels.*.name, '{label(n)}')")


def normal_gate() -> str:
    """Body of the normal caller's routing `if:`: the exact negation of the union of the slot gates."""
    return "!(" + " || ".join(f"({gate(n)})" for n in SLOTS) + ")"


def unslot(text: str, n: int) -> str:
    """`text` with every slot-`n` name (`(e2e n)`, `e2e-target-n`, `e2e/n/`, `-e2e-n-`, `-e2e-n.`) numbered `N`."""
    s = re.escape(str(_slot(n)))
    for pattern in (rf"(?<=\(e2e ){s}(?=\))", rf"(?<=e2e-target-){s}(?!\d)", rf"(?<=e2e/){s}(?=/)",
                    rf"(?<=-e2e-){s}(?=[-.])"):
        text = re.sub(pattern, "N", text)
    return text


def _git(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def lock_path(n: int) -> Path:
    """`aiwf-e2e-<n>.lock` in $AIWF_E2E_LOCK_DIR, else in the git common dir, which every worktree of this repo shares."""
    folder = os.environ.get("AIWF_E2E_LOCK_DIR") or _git("rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(folder).resolve() / f"aiwf-e2e-{_slot(n)}.lock"


def _try(fh: IO[str]) -> bool:
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False


def _holder(fh: IO[str]) -> str:
    fh.seek(0)
    return fh.read().strip() or "unknown holder"


@contextlib.contextmanager
def hold(slot: int | str, timeout: float = 3600, poll: float = 5) -> Iterator[int]:
    """Hold slot `slot` (1, 2 or 3), or with 'any' the first free one; wait up to `timeout` seconds, then SlotBusy.
    Yields the slot number held."""
    wanted = list(SLOTS) if slot == "any" else [_slot(slot)]
    files = {n: open(lock_path(n), "a+") for n in wanted}
    got = None
    deadline = time.monotonic() + timeout
    try:
        while got is None:
            got = next((n for n in wanted if _try(files[n])), None)
            if got is None:
                if time.monotonic() >= deadline:
                    busy = "; ".join(f"slot {n}: {_holder(files[n])}" for n in wanted)
                    raise SlotBusy(f"e2e slot{'s' if len(wanted) > 1 else ''} busy: {busy}")
                time.sleep(poll)
        for n in wanted:  # keep only the held slot's file open
            if n != got:
                files.pop(n).close()
        fh = files[got]
        fh.seek(0)
        fh.truncate()
        fh.write(f"pid {os.getpid()} since {time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
        fh.flush()
        _held.add(got)
        yield got
    finally:
        if got is not None:
            _held.discard(got)
        for fh in files.values():
            fh.close()  # closing the file releases the flock


def push_target(n: int, ref: str = "HEAD", remote: str = "origin", cwd: Path = ROOT) -> str:
    """Point `e2e-target-<n>` on `remote` at `ref`; needs slot `n` held by this process. The lease is the remote's
    current value (or absence), read just before the push, so a ref that moved under us fails instead of being
    overwritten."""
    if _slot(n) not in _held:
        raise RuntimeError(f"push_target needs e2e slot {n}: run it inside e2eslot.hold({n})")
    target = target_ref(n)
    sha = _git("rev-parse", f"{ref}^{{commit}}", cwd=cwd)
    current = _git("ls-remote", remote, target, cwd=cwd).split("\t")[0]
    push = ["push", "--quiet", f"--force-with-lease={target}:{current}", remote, f"{sha}:{target}"]
    if Path(cwd, remote).exists():  # a local remote (unit tests)
        _git(*push, cwd=cwd)
    else:  # GitHub: push as the agent App (ADR-0031), never with the maintainer's git credentials
        subprocess.run([str(ROOT / "scripts" / "dev" / "as-agent"), "git", *push], cwd=cwd, capture_output=True,
                       text=True, check=True)
    return sha


def held(env: Mapping[str, str] = os.environ) -> tuple[int, str]:
    """(slot, sha) the pytest controller holds for this run and exported to its workers; NoSlot otherwise."""
    slot, sha = env.get(HELD_ENV), env.get(SHA_ENV)
    if not slot or not sha:
        raise NoSlot(f"this test needs an e2e slot: run with {USAGE} (not a pass)")
    return _slot(int(slot)), sha
