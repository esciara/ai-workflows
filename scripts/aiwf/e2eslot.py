"""The single e2e slot (ADR-0026, ADR-0028): a `flock` on this Mac, held while a test points `e2e-target` at its branch.

The kernel drops the lock when the holding process dies, so a crashed run never needs a cleanup step.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import subprocess
import time
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[2]
TARGET = "refs/heads/e2e-target"
_held: set[str] = set()


class SlotBusy(Exception):
    pass


def _git(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def lock_path() -> Path:
    """$AIWF_E2E_LOCK, else a file in the git common dir, which every worktree of this repo shares."""
    if os.environ.get("AIWF_E2E_LOCK"):
        return Path(os.environ["AIWF_E2E_LOCK"])
    return (ROOT / _git("rev-parse", "--git-common-dir")).resolve() / "aiwf-e2e.lock"


@contextlib.contextmanager
def hold(path: Path | None = None, timeout: float = 3600, poll: float = 5) -> Iterator[Path]:
    """Hold the e2e slot; wait up to `timeout` seconds for it, then raise SlotBusy."""
    path = path or lock_path()
    fh = open(path, "a+")
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    fh.seek(0)
                    raise SlotBusy(f"e2e slot {path} busy: {fh.read().strip() or 'unknown holder'}") from None
                time.sleep(poll)
        fh.seek(0)
        fh.truncate()
        fh.write(f"pid {os.getpid()} since {time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
        fh.flush()
        _held.add(str(path))
        yield path
    finally:
        _held.discard(str(path))
        fh.close()  # closing the file releases the flock


def push_target(ref: str = "HEAD", remote: str = "origin", cwd: Path = ROOT, path: Path | None = None) -> str:
    """Point `e2e-target` on `remote` at `ref`; needs the slot. The lease is the remote's current value (or absence),
    read just before the push, so a pointer that moved under us fails instead of being overwritten."""
    if str(path or lock_path()) not in _held:
        raise RuntimeError("push_target needs the e2e slot: run it inside e2eslot.hold()")
    sha = _git("rev-parse", f"{ref}^{{commit}}", cwd=cwd)
    current = _git("ls-remote", remote, TARGET, cwd=cwd).split("\t")[0]
    push = ["push", "--quiet", f"--force-with-lease={TARGET}:{current}", remote, f"{sha}:{TARGET}"]
    if Path(cwd, remote).exists():  # a local remote (unit tests)
        _git(*push, cwd=cwd)
    else:  # GitHub: push as the agent App (ADR-0031), never with the maintainer's git credentials
        subprocess.run([str(ROOT / "scripts" / "dev" / "as-agent"), "git", *push], cwd=cwd, capture_output=True,
                       text=True, check=True)
    return sha
