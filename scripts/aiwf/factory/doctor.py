"""`doctor`: check the factory host without starting a run. One `ok` or `FAIL` line per check, exit 1 on any FAIL.

Never prints a secret: the decrypt check discards the value and the token check prints only a PR count. M1.4 the sbx egress policy.
"""

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable

from aiwf.factory import apptoken, m0, secrets

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


PLAYGROUND = "esciara/ai-workflows-playground"


def check_app_token() -> Result:
    """Mint a read-only token for the playground and list its PRs (the token goes to one request header, then is dropped)."""
    repo = os.environ.get("AIWF_FACTORY_REPO", PLAYGROUND)
    if not os.environ.get(apptoken.APP_ID_ENV):  # M1.1 hosts have a placeholder PEM and no App yet
        return True, f"skipped: {apptoken.APP_ID_ENV} is not set (the App is created in M1.2, docs/factory-m1.md)"
    try:
        tok = apptoken.mint(repo, apptoken.READ)
        status, raw = apptoken._urllib_http("GET", f"{apptoken.API}/repos/{repo}/pulls?state=open&per_page=100",
                                            {"Authorization": f"Bearer {tok.reveal()}", "Accept": "application/vnd.github+json",
                                             "User-Agent": "aiwf-factory"}, None)
    except apptoken.TokenError as e:
        return False, str(e)
    if status != 200:
        return False, f"listing PRs of {repo} failed with HTTP {status}"
    try:
        prs = json.loads(raw)
    except ValueError:
        prs = None
    if not isinstance(prs, list):
        return False, f"listing PRs of {repo} returned an unexpected body"
    return True, f"minted a read token and listed {len(prs)} open PR(s) of {repo}"


def check_keychain() -> Result:
    """Unlock factory's login keychain (empty password, ADR-0067), then confirm it is unlocked."""
    ok, msg = m0.unlock_keychain()
    if not ok:
        return False, msg
    if msg.startswith("skipped"):
        return True, msg
    try:
        r = subprocess.run(["security", "show-keychain-info", str(m0.keychain_path())], capture_output=True, text=True,
                           timeout=30, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"security did not run ({type(e).__name__})"
    if r.returncode != 0:
        return False, f"keychain still locked or unreadable rc={r.returncode}: {r.stderr.strip()[:200]} (docs/factory-m1.md, step sbx keychain)"
    return True, "login keychain unlocked"


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
    limit = m0.max_failures()
    if n >= limit:
        return False, f"{n} consecutive failures: the runner will not start; delete {m0.failures_file()} and kickstart the daemon to re-arm"
    return True, f"{n} consecutive failures (limit {limit})"


CHECKS: list[tuple[str, Callable[[], Result]]] = [
    ("tools", check_tools),
    ("key-file", check_key_file),
    ("decrypt", check_decrypt),
    ("app-token", check_app_token),
    ("keychain", check_keychain),
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
