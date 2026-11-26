"""`doctor`: check the factory host without starting a run. One `ok` or `FAIL` line per check, exit 1 on any FAIL.

Never prints a secret: the decrypt check discards the value. M1.2 adds the App token mint, M1.4 the sbx egress policy.
"""

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from aiwf.factory import m0, secrets

TOOLS = ("sops", "sbx", "uv", "git")
Result = tuple[bool, str]


def check_tools() -> Result:
    missing = [t for t in TOOLS if not shutil.which(t)]
    return (not missing, "all on PATH" if not missing else f"not on PATH: {', '.join(missing)} (launchd PATH is minimal)")


def check_key_file() -> Result:
    problems = secrets.check_key_file(secrets.default_paths())
    return (not problems, "key file 0600 and directory 0700, owned by the running user" if not problems else "; ".join(problems))


def check_decrypt() -> Result:
    for name in (secrets.CLAUDE_OAUTH, secrets.FACTORY_APP_PEM):
        try:
            secrets.read_secret(name)  # value discarded
        except secrets.SecretsError as e:
            return False, str(e)
    return True, "claude_oauth and factory_app_pem decrypt"


def check_sbx() -> Result:
    try:
        r = subprocess.run(["sbx", "ls", "--quiet"], capture_output=True, text=True, timeout=60, check=False,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"sbx did not run ({type(e).__name__})"
    return (r.returncode == 0, "sbx ls works" if r.returncode == 0 else f"sbx ls failed rc={r.returncode}")


def check_stop_file() -> Result:
    stop = m0.stop_file()
    if stop.exists():
        return False, f"{stop} exists (kill switch is on)"
    return True, "no STOP file"


def check_failures() -> Result:
    n = m0.read_failures()
    limit = int(os.environ.get("AIWF_FACTORY_MAX_FAILURES") or m0.DEFAULT_MAX_FAILURES)
    if n >= limit:
        return False, f"{n} consecutive failures: the runner will not start; delete {m0.failures_file()} to re-arm"
    return True, f"{n} consecutive failures (limit {limit})"


CHECKS: list[tuple[str, Callable[[], Result]]] = [
    ("tools", check_tools),
    ("key-file", check_key_file),
    ("decrypt", check_decrypt),
    ("sbx", check_sbx),
    ("stop-file", check_stop_file),
    ("failures", check_failures),
]


def main() -> int:
    failed = 0
    for name, check in CHECKS:
        try:
            ok, msg = check()
        except Exception as e:  # a crashing check is a FAIL; the type only, never the text
            ok, msg = False, type(e).__name__
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {name}: {msg}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
