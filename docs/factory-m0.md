# Factory M0

M0 is the smallest slice of the local AI software factory: a DBOS workflow `hello_two()` in `scripts/aiwf/factory/m0.py` that runs two `claude -p "say hello world"` calls in parallel, each in its own `sbx` sandbox (`aiwf-<workflow_id first 8>-<i>`), through a DBOS queue `sbx` with concurrency 2. State is in SQLite (`~/factory/dbos.sqlite`, override with `AIWF_FACTORY_DB`); the application version is the git SHA (override with `AIWF_FACTORY_VERSION`). Startup first removes every stale `aiwf-*` sandbox. The subscription token is read once at startup from the macOS Keychain of the running user (service `aiwf-claude-oauth`, override with env `CLAUDE_CODE_OAUTH_TOKEN` for tests) and handed to `sbx exec` through the subprocess environment (bare `-e CLAUDE_CODE_OAUTH_TOKEN`), never in argv, DBOS records or logs. Sandboxes are created with `--cpus 2 -m 4g` (override with `AIWF_SBX_CPUS`, `AIWF_SBX_MEMORY`).

The sbx create and exec forms were confirmed by a real run; bare `-e KEY` on `exec` and `ls --quiet` are still unverified. They live in one marked block in `m0.py`, with the `--env-file` fallback described there.

## Set-up (once, as user `factory`)

- Set the sbx network policy once beforehand with `sbx policy` (the first run otherwise asks an interactive question).
- Store the token in the Keychain: `security add-generic-password -a factory -s aiwf-claude-oauth -w` (it prompts; paste the token).
- Have no sbx secret for anthropic: remove any existing one with `sbx secret rm anthropic`, and custom ones by their placeholder.

## Run (as user `factory`)

- `git clone <repo> ~/factory/src`
- `cd ~/factory/src && uv sync --extra factory`
- `uv run python -m aiwf.factory.m0`
- Over ssh: `ssh factory@localhost 'cd ~/factory/src && uv run python -m aiwf.factory.m0'`

Output: two JSON lines, each with `sandbox`, `start`, `end` (taken inside the step) and `output`.

## Done checks

- The two outputs overlap in time (start/end timestamps).
- `kill -9` mid-run, then restart: the run resumes without rerunning a completed step.
- `sbx ls` shows no `aiwf-*` afterwards.
- Works over ssh.
- The token string is not in the logs or in `dbos.sqlite`.

## Known limits

- The token is inside the VM (accepted risk).
- The sbx secret proxy route does not work for subscription tokens: the built-in `anthropic` secret sends it as an API key (401), and a custom secret for api.anthropic.com breaks even a directly passed token.
- The sandbox default size is huge (half of host RAM), so always pass `--cpus` and `-m`.

## Verified (maintainer, as macOS user `factory`)

- `sbx ls` shows no `aiwf-*` after a run.
- `grep -a -c sk-ant-oat ~/factory/dbos.sqlite` returns 0.
- `kill -9` mid-run then rerun resumes, with no duplicate and no leftover sandbox (after the `sbx rm --force` fix).
- A run over `ssh factory@localhost` works with factory's GUI session both open and logged out, but only after `security unlock-keychain ~/Library/Keychains/login.keychain-db`.

## Open for M1 / ADR

- The login keychain is locked in ssh sessions ("User interaction is not allowed"), so m0 prints "No Claude token" until it is unlocked. Unattended or launchd runs need a solution for this.
