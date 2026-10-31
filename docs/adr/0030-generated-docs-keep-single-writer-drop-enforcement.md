# ADR-0030 · Generated docs: single writer kept, enforcement dropped

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D30`
- Amends: [ADR-0015](0015-parallel-operating-model.md)

## Context

ADR-0015 committed four generated files (`docs/progress.md`, `docs/board.jsonl`, the ADR index in `docs/adr/README.md`, `docs/diagrams.md`), made the orchestrator their single writer in sync PRs, and enforced that with tests. Each guard was added to fix the previous one:

- `docs/progress.md` was hand-edited and conflicted between parallel branches, so it moved to beads.
- beads live on one Mac, so a scanned export `docs/board.jsonl` was committed and progress rendered from it.
- every PR that re-rendered the files conflicted with the others, so a single writer was added: only the orchestrator's `sync-*` branch may change them, enforced by `tests/test_single_writer.py`.
- freshness checks (`--check`, `generated.stale`) ran on every branch and on main.
- incident: PR #19 added ADR files; CI run 41157699361 failed because the ADR index was out of date, while the single-writer rule forbade that branch from regenerating it. A deadlock between two guards.
- the fix limited freshness to `sync-*` branches (`is_sync_branch`, `current_branch`) and added a SessionStart stale-sync warning.

The maintainer's rule (2026-10-31): risks whose worst outcome is a stall get documented, no mechanism; mechanisms only for security breach, wrong output or lost work. A stale or hand-edited render is cosmetic: the sources (beads, ADR files, `.mmd` files) are the truth. The maintainer reads the rendered files on GitHub to follow progress, so they must stay committed.

## Options considered

- Stop committing the renders (keep only `docs/board.jsonl`), renderers print on demand: no conflicts, no sync PR; the maintainer can no longer read progress, the ADR index and the diagrams on GitHub.
- Keep the renders and the single writer as a convention, drop their enforcement: the maintainer keeps reading them on GitHub; a stale or hand-edited render shows up as a rebase conflict or a batch out of date.
- Keep everything: no change; about 200 lines of guards and tests that only protect a cosmetic risk and already deadlocked once.

The first was rejected because the maintainer reads the renders on GitHub; the third keeps a mechanism for a stall-only risk. Moving the board to GitHub Issues was not reconsidered; ADR-0015 rejected it.

## Decision

- Unchanged: the four generated files stay committed; the orchestrator renders them with `scripts/dev/render-progress`, `scripts/dev/render-adr-index` and `scripts/dev/render-diagrams` and commits them in its sync PRs; track PRs change only sources. This is a convention.
- Removed, the enforcement: `scripts/aiwf/generated.py` (single-writer check, freshness check, `is_sync_branch`, `current_branch`), `tests/test_single_writer.py`, the freshness tests in `tests/test_adrindex.py`, `tests/test_progress.py` and `tests/test_diagrams.py`, `--check` on the three renderers, and the SessionStart stale-sync warning.
- Kept: the renderers' unit tests, and the gitleaks scan of the board export (it guards against a secret leak).

Why: the guards protected only against a stall or a cosmetic drift; the files themselves are needed on GitHub.

## Consequences

- Risk accepted: a stale or hand-edited render shows up as a rebase conflict or a batch out of date, fixed by the orchestrator's next sync PR. Stall only.
- No CI failure can come from a generated file being out of date; nothing reminds the orchestrator that a sync PR is due beyond its own routine.
- ADR-0015's step-6 CI follow-ups for these files (`render-* --check`, single-writer and staleness checks) no longer apply; gitleaks on PRs still stands.
