# ADR-0036 · Parallel operating model (consolidated)

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D36`
- Supersedes: [ADR-0015](0015-parallel-operating-model.md), [ADR-0027](0027-plan-stop-bead-is-blocked-awaiting-go.md)

## Context

The parallel operating model was decided in ADR-0015, then partly removed by ADR-0030 (enforcement of the generated files) and ADR-0033 (agent-lifetime claims, merge slot), with the agents' GitHub identity and the protection of `main` added by ADR-0031. A reader of ADR-0015 alone meets a heartbeat, a reaper, a merge slot and CI checks that no longer exist, and agents read leftover text as instructions. The README rule now says: when part of a decision is removed or reversed, a new ADR states the full current decision and supersedes the old one.

## Options considered

- (a) Keep ADR-0015 plus its amendments: no new file; the reader has to merge three or four ADRs in their head and still reads retired mechanisms as current.
- (b) A note at the top of ADR-0015 pointing at the amendments: cheap; edits an accepted decision, and the body still describes retired mechanisms.
- (c) A consolidated ADR that states only what is in force and supersedes ADR-0015: one place to read; one more ADR, and the history moves to the superseded ones.

(a) and (b) leave retired mechanisms in the text agents read as current.

## Decision

Replaces: ADR-0015 (its agent-lifetime claims, heartbeat, lease, reaper, spawn guard and merge slot were dropped by ADR-0033; its single-writer test, `--check` freshness checks, stale-sync warning and step-6 CI follow-ups for generated files were dropped by ADR-0030).

- **Board.** bd in embedded mode, in `.beads/` of the main checkout (shared by all worktrees through the git common directory), no Dolt remote; `.beads/` is never committed. One bead per WP, id `aiwf-wp<N>`, label `wp`, `blocks` dependencies as in `docs/plan.md`, metadata `wp`, `pr`, `notes`, `log`, `metrics`. Statuses `open`, `in_progress`, `in_review` (custom), `blocked`, `closed`; a plan-stop bead is `blocked` with label `awaiting-go` (ADR-0027). Follow-ups are beads too (child beads of their WP, or labelled `step6` / `ops`). Fresh checkout: `bd init --non-interactive --skip-agents --skip-hooks -p aiwf`, `bd config set status.custom "in_review:wip"`, then `bd import docs/board.jsonl`.
- **Export.** `scripts/dev/render-progress` runs `bd export`, drops volatile fields (`updated_at`, `lease_expires_at`, `heartbeat_at`), `owner` and the merge-slot bead (label `gt:slot`) since bd may still hold them, sorts by id with sorted keys, scans the result with gitleaks and refuses to write on a finding (or when gitleaks is missing), writes `docs/board.jsonl`, then renders `docs/progress.md` from it.
- **Generated files.** `docs/progress.md`, `docs/board.jsonl`, the ADR index block in `docs/adr/README.md` (`scripts/dev/render-adr-index`) and `docs/diagrams.md` (`scripts/dev/render-diagrams`, from `docs/diagrams/*.mmd`) stay committed so the maintainer reads them on GitHub. The orchestrator renders and commits them in a serial sync PR on a `sync-*` branch after each merge batch; track PRs change only sources (ADR files, `docs/diagrams/*.mmd`). This is a convention: nothing checks freshness or the single writer; a stale or hand-edited render is fixed by the next sync PR.
- **Roles.**
  - Orchestrator (one session, main checkout): assigns WPs to tracks (push model), allocates ADR numbers, fixes the merge order, rebases one branch at a time, and is the only writer of the board and the generated files. To start a track it assigns the bead (`bd update <id> -a <actor> -s in_progress`), then spawns the track agent with the Agent tool, `run_in_background: true`, and a description starting with `aiwf-wp<N>: `; it resumes a finished track agent with `SendMessage`, never by spawning a new one.
  - Track agent (one per WP): works one WP in its own worktree (`git worktree add ../ai-workflows-<slug> -b wp<N>-<slug> origin/main`). Never assigns beads or changes their assignee, never uses `bd --claim` or `bd --force`; may move only its own bead to `in_review`. Changes only sources and never touches other tracks' files; shared paths only with the orchestrator's go.
- **Orphaned beads.** A SessionStart hook in `.claude/settings.json` prints the `in_progress` beads (`bd list --status in_progress`), and does nothing when `bd` or `.beads/` is missing. At session start the orchestrator treats one with no live track agent as orphaned (crashed agent) and resumes or reassigns it. There is no heartbeat, lease, reaper, agent binding, spawn guard or merge slot: risks whose worst outcome is a stall get documented, no mechanism; mechanisms are only for security breach, wrong output or lost work.
- **Agent identity on GitHub (ADR-0031).** All development agents act as the GitHub App `esciara-ai-workflows-agent` (no administration permission): every GitHub write goes through `scripts/dev/as-agent gh …` / `scripts/dev/as-agent git push …`; bare `gh` may only read. Maintainer actions needed in e2e (commands such as `/fix`, `/review`, playground PR approvals, the labels-sync dispatch) go through `scripts/dev/as-maintainer`, limited to the playground. The `PreToolUse` Bash hook `scripts/dev/guard-bash` blocks bare `gh` writes, bare `git push`, merges, agent approvals, `gh auth token`, pushes to `main`, force pushes without `--force-with-lease` and remote branch deletion; it is a guardrail matching command text, not a boundary.
- **`main` protection (ADR-0031).** A repository ruleset on `main` with an empty bypass list: pull request required, 1 approval, stale approvals dismissed, approval of the most recent push required, status check `test` from GitHub Actions required, force pushes blocked, deletions restricted, merge method rebase. The maintainer approves and merges every PR, in the orchestrator's order.
- **Branch updates.** Rebase with `git rebase --update-refs origin/main` and push with `--force-with-lease`; never a plain `--force`, never a merge commit. Check that the PR is still open before pushing to it. A rebase pushed after the maintainer's approval needs a fresh approval.
- **Shared paths.** A track changes these only after the orchestrator's go, and the orchestrator serialises such changes (one open PR per shared path):
  - `.github/workflows/*`, `templates/`, `.claude/settings.json`
  - `scripts/aiwf/cli.py`, `publish.py`, `commands.py`, `config.py`, `labels.py`, `policy.py`, and the board tooling `gendoc.py`, `board.py`, `progress.py`, `adrindex.py`, `diagrams.py`; the dev guard `devguard.py` and the e2e slot `e2eslot.py`; `scripts/dev/*`
  - `schema/ai-workflows.schema.json`, `schema/labels.yml`
  - `tests/test_workflow_policy.py`, `tests/e2e/conftest.py`, `tests/e2e/playground.py`
  - `pyproject.toml`, `uv.lock`
  - `CLAUDE.md`, `docs/spec.md`, `docs/plan.md`, `docs/diagrams/overview.mmd`, and the generated files above (orchestrator only)
- **Track-owned paths.** A new module per role (e.g. `scripts/aiwf/review.py`), its prompts and schemas, `tests/test_<module>.py`, `tests/e2e/test_wp<N>.py`, `docs/diagrams/wp<N>.mmd`, and an ADR with an allocated number.

Why: bd gives a local board shared by all worktrees without a server, and the scanned export keeps a reviewable record in git; push assignment and a single orchestrator remove the races between tracks without claims; the ruleset and the App's missing administration permission make "agents never merge or push to `main`" enforced by GitHub rather than by instructions.

## Consequences

- A crashed or killed track agent leaves its bead `in_progress` until the orchestrator's next session start. Stall only.
- Nothing technically stops a track agent from running `bd update --claim` or `--force`; CLAUDE.md forbids it, and the worst outcome is a wrong assignee, fixed by the orchestrator.
- Generated files on `main` lag behind merges until the next sync PR; nothing reminds the orchestrator that one is due beyond its routine. No CI failure comes from a stale generated file.
- Losing the main checkout's `.beads/` loses anything not yet exported; `bd import docs/board.jsonl` restores the rest.
- A new WP diagram needs a `generated:wp<N>` block in `docs/diagrams.md`: the track adds the `.mmd`, the orchestrator adds the block in the sync PR.
- The board lives on one Mac and the orchestrator is the single writer: fine for up to ~3 parallel tracks. Revisit (shared Dolt server, or post-merge regeneration by a bot on `main`) when more tracks run or agents run off this Mac; bead `aiwf-ldn`.
- Agents keep a narrow path to the maintainer's credentials through `scripts/dev/as-maintainer`; the ruleset, not the hook, is the boundary.
