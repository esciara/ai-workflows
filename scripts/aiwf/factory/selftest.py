"""M0 acceptance self-test, run once by the maintainer as macOS user `factory`.

Prints one PASS/FAIL line per check and a summary. It never reads, prints, accepts or stores the token or a password:
the Keychain probe runs without `-w` and its output is discarded.
"""

import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

PREFIX = "aiwf-"
KEYCHAIN_SERVICE = "aiwf-claude-oauth"
KEYCHAIN_FILE = "~/Library/Keychains/login.keychain-db"
KILL_AFTER = 5.0
M0_CMD = ["uv", "run", "python", "-m", "aiwf.factory.m0"]
TOKEN_PREFIX = "sk-ant-oat"
HELLO_RE = re.compile(r"hello,?\s+world", re.IGNORECASE)  # the prompt is "say hello world": punctuation varies

Result = tuple[bool, str]
# run(args, timeout) -> (returncode, stdout, stderr); injected in tests
Runner = Callable[[list[str], float], tuple[int, str, str]]


def default_run(args: list[str], timeout: float) -> tuple[int, str, str]:
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False, stdin=subprocess.DEVNULL)
    return r.returncode, r.stdout, r.stderr


def aiwf_sandboxes(ls_out: str) -> list[str]:
    """Names of aiwf-* sandboxes in `sbx ls` output (quiet or table form: first column)."""
    names = []
    for line in ls_out.splitlines():
        parts = line.split()
        if parts and parts[0].startswith(PREFIX):
            names.append(parts[0])
    return names


def count_hello_results(out: str) -> int:
    """Number of printed result lines (JSON with a `sandbox` key) whose output says Hello, world!"""
    n = 0
    for line in out.splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and "sandbox" in obj and HELLO_RE.search(json.dumps(obj.get("output"))):
            n += 1
    return n


def count_results(out: str) -> int:
    """Number of printed result lines of any content."""
    n = 0
    for line in out.splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and "sandbox" in obj:
            n += 1
    return n


def keychain_verdict(rc: int, stderr: str, user: str) -> Result:
    """Decide from the exit code and stderr of `security find-generic-password` (no -w). Never receives the secret."""
    if rc == 0:
        return True, "Keychain token readable"
    err = stderr.lower()
    unlock = f"run `security unlock-keychain {KEYCHAIN_FILE}` and type the password at its prompt, then rerun"
    if "user interaction is not allowed" in err or rc == 36:
        return False, f"Keychain is locked: {unlock}"
    if "could not be found" in err or rc == 44:
        return False, (
            f"Keychain item missing: run `security add-generic-password -a {user} -s {KEYCHAIN_SERVICE} -w` "
            "and paste the token at its prompt, then rerun"
        )
    return False, f"Keychain probe failed (rc={rc}): {unlock}, or check the item exists"


def unfinished_hello_two(db: str) -> int:
    """Count hello_two workflows in the DBOS SQLite that are not finished (read-only)."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return con.execute(
            "SELECT count(*) FROM workflow_status WHERE name = 'hello_two' AND status IN ('PENDING', 'ENQUEUED')"
        ).fetchone()[0]
    finally:
        con.close()


class SelfTest:
    def __init__(self, run: Runner = default_run, spawn=None, sleep=time.sleep, home: Path | None = None,
                 user: str = "factory", unfinished=None, kill=None):
        self.run, self.sleep, self.user = run, sleep, user
        # new session so that SIGKILL reaches the whole group: `uv run` would otherwise die and orphan python
        self.spawn = spawn or (lambda: subprocess.Popen(
            M0_CMD, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True))
        self.kill = kill or (lambda proc: os.killpg(proc.pid, signal.SIGKILL))
        db = os.environ.get("AIWF_FACTORY_DB") or str((home or Path.home()) / "factory" / "dbos.sqlite")
        self.db = db
        self.unfinished = unfinished or (lambda: unfinished_hello_two(db))

    def leftover(self) -> list[str]:
        rc, out, _ = self.run(["sbx", "ls"], 120)
        if rc != 0:
            raise RuntimeError(f"sbx ls failed rc={rc}")
        return aiwf_sandboxes(out)

    def check_keychain(self) -> Result:
        rc, _out, err = self.run(["security", "find-generic-password", "-a", self.user, "-s", KEYCHAIN_SERVICE], 60)
        return keychain_verdict(rc, err, self.user)

    def check_normal_run(self) -> Result:
        rc, out, _ = self.run(M0_CMD, 900)
        hello, total = count_hello_results(out), count_results(out)
        if rc != 0:
            return False, f"m0 exited rc={rc}"
        if hello != 2 or total != 2:
            return False, f"expected 2 Hello, world! results, got {hello} of {total} printed"
        left = self.leftover()
        if left:
            return False, f"sandboxes left after run: {', '.join(left)}"
        return True, "2 Hello, world! results, no aiwf-* sandbox left"

    def check_no_token_in_db(self) -> Result:
        rc, out, _ = self.run(["grep", "-a", "-c", TOKEN_PREFIX, self.db], 120)
        if rc not in (0, 1):
            return False, f"grep failed rc={rc} on {self.db}"
        count = out.strip()
        if count != "0":
            return False, f"token prefix found {count or '?'} time(s) in {self.db}"
        return True, "no token in dbos.sqlite"

    def check_kill_resume(self) -> Result:
        proc = self.spawn()
        self.sleep(KILL_AFTER)
        if proc.poll() is not None:
            return False, f"m0 ended on its own (rc={proc.returncode}) before the kill; nothing was tested"
        self.kill(proc)
        proc.wait()
        pending = self.unfinished()
        if pending != 1:
            return False, f"after the kill expected 1 unfinished hello_two in the DB, found {pending}; nothing to resume"
        rc, out, _ = self.run(M0_CMD, 900)
        if rc != 0:
            return False, f"rerun exited rc={rc}"
        total = count_results(out)
        if total != 2:
            return False, f"rerun printed {total} results, expected exactly 2"
        if self.unfinished() != 0:
            return False, "a hello_two is still unfinished after the rerun"
        left = self.leftover()
        if left:
            return False, f"sandboxes left after resume: {', '.join(left)}"
        return True, "resumed, 2 results, no aiwf-* sandbox left"


def report(name: str, check: Callable[[], Result]) -> bool:
    try:
        ok, msg = check()
    except Exception as e:  # a crashing check is a FAIL, not a crash
        ok, msg = False, f"{type(e).__name__}: {e}"
    print(f"{'PASS' if ok else 'FAIL'} {name}: {msg}", flush=True)
    return ok


def main(st: SelfTest | None = None) -> int:
    st = st or SelfTest(user=os.environ.get("USER", "factory"))
    if not report("keychain", st.check_keychain):
        print("SUMMARY: FAIL (stopped at keychain)")
        return 1
    results = [
        report("normal-run", st.check_normal_run),
        report("kill-resume", st.check_kill_resume),
        report("no-token-in-db", st.check_no_token_in_db),  # last: covers everything the runs wrote
    ]
    passed = sum(results) + 1  # the keychain check passed to get here
    print(f"SUMMARY: {'PASS' if all(results) else 'FAIL'} ({passed}/{len(results) + 1} checks passed)")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
