"""M1.1 spike, run by the maintainer as user `factory`, from a LaunchDaemon with no GUI session (docs/factory-m1.md).

Four checks, one PASS/FAIL line each: sbx works without a GUI; `claude -p` reads its prompt from stdin inside `sbx exec`;
bare `-e KEY` takes the value from the environment; the egress policy still lets `claude` start. The token is read from
the SOPS file into memory and passed through the environment only; no output line contains it.
"""

import os
import subprocess
import sys

from aiwf.factory import m0, secrets

NAME = "aiwf-spike-1"
PROMPT = "say hello world"


def sh(args: list[str], env: dict | None = None, stdin: str | None = None, timeout: int = 300) -> tuple[int, str]:
    r = subprocess.run(args, capture_output=True, text=True, env=env, input=stdin, timeout=timeout, check=False)
    return r.returncode, r.stdout


def main() -> int:
    ok, msg = m0.unlock_keychain()
    print(f"{'PASS' if ok else 'FAIL'} keychain: {msg}", flush=True)
    if not ok:
        print("SUMMARY: FAIL; M1 stops and comes back as an ask")
        return 1
    try:
        token = secrets.read_secret(secrets.CLAUDE_OAUTH)
    except secrets.SecretsError as e:
        print(f"FAIL secrets: {e}\nSUMMARY: FAIL; M1 stops and comes back as an ask")
        return 1
    env = {**os.environ, m0.TOKEN_ENV: token}
    results: list[bool] = []

    def report(name: str, ok: bool, msg: str) -> None:
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'} {name}: {msg}", flush=True)

    rc, out = sh(["sbx", "ls", "--quiet"])
    report("sbx-no-gui", rc == 0, "sbx ls works" if rc == 0 else f"sbx ls rc={rc}: no GUI session or sbx login missing?")
    if rc != 0:
        print("SUMMARY: FAIL; M1 stops and comes back as an ask")
        return 1
    sh(m0.sbx_rm_args(NAME))
    try:
        rc, _ = sh(m0.sbx_create_args(NAME))
        report("sbx-create", rc == 0, f"rc={rc}")
        if rc != 0:
            print("SUMMARY: FAIL; M1 stops and comes back as an ask")
            return 1
        # prompt on stdin, token only through the environment (bare -e KEY); no prompt argument
        args = ["sbx", "exec", "-i", "-e", m0.TOKEN_ENV, NAME, "claude", "-p", "--output-format", "json"]
        rc, out = sh(args, env=env, stdin=PROMPT)
        report("claude-stdin-bare-e-egress", rc == 0 and "hello" in out.lower(),
               "claude answered from stdin with the token passed bare, behind the egress policy" if rc == 0
               else f"rc={rc}: see which of stdin, bare -e or egress fails (try --env-file, sbx policy ls)")
    finally:
        sh(m0.sbx_rm_args(NAME))
    rc, out = sh(["sbx", "ls", "--quiet"])
    report("no-leftover", rc == 0 and NAME not in out.split(), "sandbox removed")
    print(f"SUMMARY: {'PASS' if all(results) else 'FAIL'}; on FAIL, M1 stops and comes back as an ask")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
