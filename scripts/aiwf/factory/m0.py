"""Factory milestone M0: two parallel Claude hello-worlds in sbx sandboxes, durable via DBOS.

The subscription OAuth token is read once from the Keychain (or env, for tests) and passed to `sbx exec` through the
subprocess environment only: never in argv, never as a step argument, never logged. Never print the environment.
"""

import json
import os
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

QUEUE_NAME = "sbx"
PREFIX = "aiwf-"
TIMEOUT = 600
KEYCHAIN_SERVICE = "aiwf-claude-oauth"
TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"
_token: str | None = None  # module-level on purpose: DBOS stores step args in SQLite, so steps read it from here


def load_token() -> None:
    """Read the token once at startup. Override from env for tests. Messages never include the value."""
    global _token
    tok = os.environ.get(TOKEN_ENV, "").strip()
    if not tok:
        user = os.environ.get("USER", "")
        r = subprocess.run(
            ["security", "find-generic-password", "-a", user, "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, check=False,
        )
        tok = r.stdout.strip() if r.returncode == 0 else ""
    if not tok:
        raise SystemExit(
            f"No Claude token: run `security add-generic-password -a \"$USER\" -s {KEYCHAIN_SERVICE} -w` first"
        )
    _token = tok


def get_token() -> str:
    if not _token:
        raise RuntimeError("token not loaded")
    return _token


# --- sbx CLI flags: ONE place. Unconfirmed, check against the maintainer's S1 output. ---
# Confirmed by a real run: `sbx create claude --name N --cpus 2 -m 4g` (no workspace), `sbx exec N claude -p ...`
# (stdin must be /dev/null). Sbx's default sandbox size is huge, so always pass cpus and memory.
# UNVERIFIED: bare `-e KEY` on `exec` taking the value from the environment (create documents it).
# If exec rejects it, fall back to `--env-file` on a 0600 temp file (os.open mode 0o600) deleted in finally.
# `ls --quiet` is also an assumption.
def sbx_create_args(name: str) -> list[str]:
    cpus = os.environ.get("AIWF_SBX_CPUS", "2")
    mem = os.environ.get("AIWF_SBX_MEMORY", "4g")
    return ["sbx", "create", "claude", "--name", name, "--cpus", cpus, "-m", mem]


def sbx_exec_args(name: str) -> list[str]:
    return ["sbx", "exec", "-e", TOKEN_ENV, name, "claude", "-p", "say hello world", "--output-format", "json"]


def sbx_rm_args(name: str) -> list[str]:
    return ["sbx", "rm", name]


SBX_LS_ARGS = ["sbx", "ls", "--quiet"]  # expected: one sandbox name per line
# --- end of unconfirmed flags ---


def run_sbx(args: list[str], check: bool = True, with_token: bool = False) -> str:
    """Single choke point for every sbx/claude call (faked in unit tests)."""
    env = {**os.environ, TOKEN_ENV: get_token()} if with_token else None
    r = subprocess.run(
        args, capture_output=True, text=True, timeout=TIMEOUT, check=False, env=env, stdin=subprocess.DEVNULL
    )
    if check and r.returncode != 0:
        # stderr deliberately omitted: DBOS stores the error text, and it could echo a credential
        raise RuntimeError(f"{args[:2]} failed rc={r.returncode}")
    return r.stdout


def sandbox_name(workflow_id: str, i: int) -> str:
    return f"{PREFIX}{workflow_id[:8]}-{i}"


def now() -> str:
    return datetime.now(UTC).isoformat()


def reap() -> list[str]:
    """M0: remove every stale aiwf-* sandbox (no PENDING-workflow check yet)."""
    removed = []
    for line in run_sbx(SBX_LS_ARGS).splitlines():
        name = line.split()[0] if line.split() else ""
        if name.startswith(PREFIX):
            try:
                run_sbx(sbx_rm_args(name), check=False)
            except (subprocess.SubprocessError, OSError):
                continue  # one hung rm must not abort startup
            removed.append(name)
    return removed


def hello_body(workflow_id: str, i: int) -> dict:
    name = sandbox_name(workflow_id, i)
    started = now()
    try:
        run_sbx(sbx_rm_args(name), check=False)  # idempotent: drop a stale one
        run_sbx(sbx_create_args(name))
        out = run_sbx(sbx_exec_args(name), with_token=True)
        try:
            result = json.loads(out)
        except ValueError:
            result = out
        return {"sandbox": name, "start": started, "end": now(), "output": result}
    finally:
        try:
            run_sbx(sbx_rm_args(name), check=False)
        except (subprocess.SubprocessError, OSError):
            pass  # the startup reaper removes it next run; do not mask the original error


def _dbos_config() -> dict:
    version = os.environ.get("AIWF_FACTORY_VERSION") or subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    db = os.environ.get("AIWF_FACTORY_DB") or str(Path.home() / "factory" / "dbos.sqlite")
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    return {
        "name": "aiwf-factory",
        "system_database_url": f"sqlite:///{db}",
        "application_version": version,
    }


def resumed_run(dbos, version: str):
    """A run of this app version that launch() is resuming (PENDING, or ENQUEUED once re-enqueued)."""
    found = dbos.list_workflows(name="hello_two", status=["PENDING", "ENQUEUED"], app_version=version)
    return found[0].workflow_id if found else None


def main() -> int:
    from dbos import DBOS

    holder: dict = {}
    queue_ready = threading.Event()  # launch() recovers PENDING runs on a thread before the queue exists

    @DBOS.step(name="hello_step")
    def hello_step(wf_id: str, i: int) -> dict:
        return hello_body(wf_id, i)

    @DBOS.workflow(name="hello")
    def hello(i: int) -> dict:  # queues take workflows; the step holds the side effects
        return hello_step(DBOS.workflow_id, i)

    @DBOS.workflow(name="hello_two")
    def hello_two() -> list[dict]:
        queue_ready.wait()
        handles = [holder["queue"].enqueue(hello, i) for i in (1, 2)]
        return [h.get_result() for h in handles]

    load_token()
    config = _dbos_config()
    DBOS(config=config)
    reap()  # before launch: launch recovers PENDING workflows, which recreate their sandboxes
    DBOS.launch()
    holder["queue"] = DBOS.register_queue(QUEUE_NAME, concurrency=2)
    queue_ready.set()
    resumed = resumed_run(DBOS, config["application_version"])
    if resumed:  # launch() is recovering a killed run: wait for it, do not start a second
        results = DBOS.retrieve_workflow(resumed).get_result()
    else:
        results = hello_two()
    for r in results:
        print(json.dumps(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
