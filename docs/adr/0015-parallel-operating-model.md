# ADR-0015 · Parallel operating model: beads board, merge rules, shared-code boundary

- Status: Proposed
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D15`

## Context

After WP1, Workflow A (WP2–WP4) and Workflow B (WP5–WP8) can be built in parallel, plus WP11 and WP12 off WP1. Several Claude Code sessions working at once, each in its own git worktree, hit failure modes a single session never sees: two sessions editing `docs/progress.md` or the ADR index, two sessions taking the same next ADR number, stacked branches going stale when a lower PR merges, and two sessions changing the same orchestrator module. A status board that every session can update safely, plus explicit merge rules, is needed before the tracks start.

Spike on beads `bd` 1.3.2 (embedded Dolt, the default):

- All worktrees of one repo share one database, found through the git common directory; it lives in `.beads/` of the main checkout and is not in git. A write from one worktree is seen at once from the others; no sync step.
- 10 concurrent `bd create` from two worktrees all succeeded (writes are serialised by a lock, ~1 s each). `bd update --claim` is atomic: of two concurrent claims, one wins and the other fails with "already claimed".
- `bd merge-slot acquire/release` gives one exclusive holder across worktrees.
- `bd init` by default writes `AGENTS.md`, a beads section into `CLAUDE.md`, a `SessionStart` hook in `.claude/settings.json`, Cursor/Codex files, sets `core.hooksPath`, commits them, and adds the GitHub repo as a Dolt remote (`bd dolt push` would push issue data into the public repo). It was run with `--skip-agents --skip-hooks`, and the Dolt remote was removed.
- Claims carry a short lease (5 min); an expired lease is only reverted by an explicit `bd reclaim`, which nobody runs here.

## Options considered

- Status board:
  - beads, local embedded database shared by worktrees, `docs/progress.md` rendered from it: atomic claims, merge slot, dependencies, no merge conflicts on the board; the data is local to this machine and not in git, so the committed record is the rendered `docs/progress.md`.
  - beads with a Dolt remote on the GitHub repo (`refs/dolt/*`): board backed up and shared across machines; issue data and actor emails published in a public repo, plus a sync step and conflict handling.
  - beads with `.beads/issues.jsonl` committed: board in git history; every track branch that touches it conflicts, which is what the board is meant to avoid.
  - Hand-edited `docs/progress.md` (status quo): no tool; every track edits one file, so conflicts and lost updates on every merge.
  - GitHub issues/projects on this repo: shared and durable; network for every status change, and no claim or merge-slot primitive.
- Branch updates after a merge:
  - `git rebase --update-refs` onto `origin/main`, push with `--force-with-lease`: stacked branches move together; the lease refuses to overwrite a push nobody fetched.
  - Merge `main` into the track branch: no force-push; breaks the repo's rebase-merge, linear history.
- Merge order:
  - Fixed order set by the orchestrator (dependency order, then the order the WPs were assigned): predictable; a ready PR may wait behind a slower one.
  - First ready, first merged: faster; rebases land on whichever track is behind, unpredictably.
- ADR numbers:
  - Allocated by the orchestrator when a track asks: no collisions.
  - Next free number at write time: collides as soon as two tracks write an ADR.

Rejected: the Dolt remote and committed JSONL trade the conflict-free board for durability that the rendered `docs/progress.md` already gives; hand-edited progress and first-ready merging fail exactly in the parallel case; GitHub issues add network calls and lack the claim and merge-slot primitives.

## Decision

- **Board.** Beads (`bd`) in embedded mode is the status board. One bead per WP, id `aiwf-wp<N>`, label `wp`, `blocks` dependencies as in `docs/plan.md`, and metadata `wp`, `pr`, `notes`, `log` and `metrics`. Statuses: `open`, `in_progress`, `in_review` (custom), `blocked`, `closed`. Follow-up items are child beads of their WP. `.beads/` is never committed and has no Dolt remote. Set up a fresh checkout with `bd init --non-interactive --skip-agents --skip-hooks -p aiwf` and `bd config set status.custom "in_review:wip"`, then re-create the beads from `docs/progress.md` and `docs/plan.md`.
- **Rendered files.** `docs/progress.md` (`scripts/dev/render-progress`) and `docs/diagrams.md` (`scripts/dev/render-diagrams`, from `docs/diagrams/*.mmd`) have generated blocks; nobody hand-edits them.
- **Roles.** The orchestrator assigns WPs to tracks, allocates ADR numbers, sets the merge order, and is the only writer of the board (beyond a track's own claim and `in_review`) and of the rendered files. A track agent works one WP in its own worktree, claims its bead, and never touches other tracks' files.
- **Merge rules.**
  - The orchestrator fixes the merge order; the maintainer merges in that order.
  - Before rebasing a branch onto a newly merged `main`, take `bd merge-slot acquire` and release it after the push. One rebase at a time.
  - Rebase with `git rebase --update-refs origin/main` (stacked branches move together) and push with `git push --force-with-lease`. Never a plain `--force`, never a merge commit.
  - Check that the PR is still open before pushing to it.
- **Shared-code boundary.** These paths are shared by every track; a track changes them only after the orchestrator's go, and the orchestrator serialises such changes (one open PR touching a given shared path at a time):
  - `.github/workflows/*`, `templates/`
  - `scripts/aiwf/cli.py`, `scripts/aiwf/publish.py`, `scripts/aiwf/commands.py`, `scripts/aiwf/config.py`, `scripts/aiwf/labels.py`, `scripts/aiwf/policy.py`, `scripts/aiwf/gendoc.py`
  - `schema/ai-workflows.schema.json`, `schema/labels.yml`
  - `tests/test_workflow_policy.py`, `tests/e2e/conftest.py`, `tests/e2e/playground.py`
  - `pyproject.toml`, `uv.lock`
  - `CLAUDE.md`, `docs/spec.md`, `docs/plan.md`, `docs/adr/README.md` (index), `docs/progress.md`, `docs/diagrams.md`, `docs/diagrams/overview.mmd`
- Track-owned paths: a new module per role (e.g. `scripts/aiwf/review.py`), its prompts, its schemas, `tests/test_<module>.py`, `tests/e2e/test_wp<N>.py`, `docs/diagrams/wp<N>.mmd`, and an ADR with an allocated number.

Why: beads gives atomic claims and a merge slot across worktrees without a server, and the rendered `docs/progress.md` keeps a reviewable record in git; fixed order, update-refs and the lease keep stacked branches linear and safe; the shared-path list turns "never touch another track's files" into something checkable.

## Consequences

- The board lives on the maintainer's machine only; losing the main checkout's `.beads/` loses unrendered state (claims, follow-up beads). `bd backup` can snapshot it; a Dolt remote can be added later by a new ADR.
- A new WP diagram needs a `generated:wp<N>` block in `docs/diagrams.md`, which is shared: the track adds the `.mmd`, the orchestrator adds the block.
- A CI stale-check of `docs/diagrams.md` (`scripts/dev/render-diagrams --check`) comes in a later step; `docs/progress.md` cannot be checked in CI because CI has no board.
- Claims are leases that expire after 5 min; that is harmless while no one runs `bd reclaim`, and must be revisited before any automated reaper is added.
