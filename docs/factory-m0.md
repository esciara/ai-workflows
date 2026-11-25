# Factory M0

M0 is the smallest slice of the local AI software factory: a DBOS workflow `hello_two()` in `scripts/aiwf/factory/m0.py` that runs two `claude -p "say hello world"` calls in parallel, each in its own `sbx` sandbox (`aiwf-<workflow_id first 8>-<i>`), through a DBOS queue `sbx` with concurrency 2. State is in SQLite (`~/factory/dbos.sqlite`, override with `AIWF_FACTORY_DB`); the application version is the git SHA (override with `AIWF_FACTORY_VERSION`). Startup first removes every stale `aiwf-*` sandbox. Credentials are never read here: the sbx proxy injects them.

The sbx flags (`create --name N claude .`, `exec N -- claude ...`, `ls --quiet`) are assumed, not confirmed; they live in one marked block in `m0.py` and must be checked against the maintainer's S1 output.

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
