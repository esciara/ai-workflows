# Factory M1.1: unattended start

M1.1 makes the factory start at boot with nobody logged in. The agent-buildable part is in the repo: `scripts/aiwf/factory/secrets.py` (SOPS + age reader), `doctor.py`, `__main__.py` (`python -m aiwf.factory [run|doctor]`), `templates/factory/com.esciara.aiwf-factory.plist` and the spike files. The rest needs the maintainer, below. Design: [ADR-0064](adr/0064-mac-factory-runner-own-github-app-and-secrets-at-rest.md) decisions 5 and 6.

## What the code does

- Secrets live in `~factory/.config/aiwf/secrets.enc.yaml` (entries `claude_oauth` and `factory_app_pem`), encrypted by SOPS to the age key `~factory/.config/aiwf/age.key`.
- The runner and `doctor` refuse to start unless the key file is a regular file owned by the running user with mode 0600 and its directory is owned by that user with mode 0700 (a 0644 key file means no start; under launchd a refusal exits non-zero and counts as a failed start: it retries every 60 s and fills `hello_two.err.log` until 3 consecutive failures, then the runner stops itself (see Kill switches below)).
- Each value is decrypted with `sops decrypt --extract` and read from stdout into memory; it never appears in argv, logs or DBOS records. The env override `CLAUDE_CODE_OAUTH_TOKEN` is honoured only with `AIWF_FACTORY_TEST=1` (tests); production always does the key-file mode check.
- `uv run python -m aiwf.factory doctor` prints one `ok` or `FAIL` line per check (tools on PATH, key file, decrypt, `sbx ls`, no STOP file) and exits 1 on any FAIL.
- The LaunchDaemon runs `python -m aiwf.factory run` (M0's `hello_two`) as `factory`, `Umask 077`, minimal PATH, logs in `~factory/factory/runs/`. It restarts only after a failure, because M1.1's run exits after one `hello_two`.

## Runbook (maintainer)

Rules: never put a token or key in a command line, a file in the repo or the chat; every secret is typed or pasted at a prompt of the tool, or written by `sops edit`. Steps 1 to 6 run as user `factory` (log in over `ssh factory@localhost` or `su - factory` from an admin shell); steps marked admin run as your admin user with `sudo`.

1. As `factory`: `brew install sops age` (skip if present), then `mkdir -p ~/factory/runs ~/factory/src`.
2. As `factory`: `chmod 700 ~` (ADR-0065 stopgap: home not readable by others).
3. As `factory`: create the key (FileVault must be on; then exclude the key from Time Machine with `tmutil addexclusion ~/.config/aiwf/age.key` after creating it): `mkdir -m 700 -p ~/.config/aiwf`, then `(umask 077; age-keygen -o ~/.config/aiwf/age.key)`. It prints the public key (starts with `age1`); copy that line only, never the file.
4. As `factory`: write `~/.config/aiwf/.sops.yaml` with `creation_rules: [{path_regex: secrets\.enc\.yaml$, age: <the age1 public key>}]`, then `cd ~/.config/aiwf && sops edit secrets.enc.yaml` and add `claude_oauth: <factory-only token from claude setup-token>` and `factory_app_pem: |` followed by the PEM lines (the App comes later in M1.2: a placeholder value is fine now). Then delete any downloaded `.pem`. The token never goes through argv or chat.
5. As `factory`: `cd ~/factory/src && git clone <repo> . && git checkout <this branch or the tag>` then `uv sync --extra factory`, then `uv run python -m aiwf.factory doctor`. Expect all `ok`. Then prove the refusal: `chmod 644 ~/.config/aiwf/age.key`, rerun doctor (expect `FAIL key-file ... mode 0644`) and `uv run python -m aiwf.factory run` (expect the refusal, no sandbox), then `chmod 600 ~/.config/aiwf/age.key`.
6. As `factory`: set the sbx network policy once (`sbx policy`, allow `api.anthropic.com` only) and remove sbx secrets as in `docs/factory-m0.md`.
7. Spike (admin, no GUI needed for the result): `sudo cp ~factory/factory/src/templates/factory/com.esciara.aiwf-factory-spike.plist /Library/LaunchDaemons/ && sudo chown root:wheel /Library/LaunchDaemons/com.esciara.aiwf-factory-spike.plist && sudo chmod 644 /Library/LaunchDaemons/com.esciara.aiwf-factory-spike.plist && sudo launchctl bootstrap system /Library/LaunchDaemons/com.esciara.aiwf-factory-spike.plist`. Log the `factory` GUI session out first (or reboot and do not log in).
8. Read the result as `factory` (or admin with `sudo cat`): `cat ~factory/factory/runs/spike.out.log` (PASS/FAIL lines, no secret). Expected: `sbx-no-gui`, `sbx-create`, `claude-stdin-bare-e-egress`, `no-leftover` all PASS, `SUMMARY: PASS`. Then `sudo launchctl bootout system/com.esciara.aiwf-factory-spike && sudo rm /Library/LaunchDaemons/com.esciara.aiwf-factory-spike.plist`.
9. Any spike FAIL stops M1: do not continue, send the FAIL lines back as an ask. Fallbacks to try only with a go: `--env-file` on a 0600 temp file for bare `-e`, a different sbx login context for no-GUI.
10. Install the daemon (admin): same commands as step 7 with `com.esciara.aiwf-factory.plist`, then `sudo launchctl bootstrap system /Library/LaunchDaemons/com.esciara.aiwf-factory.plist`. Check `cat ~factory/factory/runs/hello_two.out.log` shows two JSON lines.
11. Reboot check: reboot the Mac, do not log in as `factory` (an admin or nobody logged in), wait about 5 minutes, then over ssh: `cat ~factory/factory/runs/hello_two.out.log` (two fresh JSON lines), `sbx ls` (no `aiwf-*`), `grep -a -c sk-ant-oat ~/factory/dbos.sqlite ~/factory/runs/*.log` (every count 0).
12. Report PASS or the exact FAIL line back; update the M1.1 Status row only after steps 8 and 11 pass.

## Kill switches and parallel runs

- The runner exits 0 at start when `~factory/factory/STOP` exists, and after 3 consecutive failed starts (counter file `~factory/factory/failures`, limit `AIWF_FACTORY_MAX_FAILURES`), so `KeepAlive` stops restarting it. Delete the file to re-arm; a successful run resets the counter.
- There is no runner lock: parallel runs are allowed. Sandboxes are named `aiwf-p<owner pid>-<workflow id>-<n>`, and the startup reaper removes only `aiwf-*` sandboxes whose owner process is dead (or that carry no owner tag), never a live run's.
- Concurrent failing runs can lose a failure-counter increment (no lock); the cap is approximate. `doctor` reports a STOP file or a reached cap as FAIL.
