# ADR-0015 · Parallel operating model: beads board, single writer, agent-lifetime claims, merge rules

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D15`
- Amended by: [ADR-0030](0030-generated-docs-keep-single-writer-drop-enforcement.md)
- Amended by: [ADR-0033](0033-stall-only-risks-get-no-mechanism-claims-retired.md)

## Context

After WP1, Workflow A (WP2–WP4) and Workflow B (WP5–WP8) can be built in parallel, plus WP11 and WP12 off WP1. Several agents working at once, each in its own git worktree, hit failure modes a single session never sees: two branches editing `docs/progress.md`, the ADR index or `docs/diagrams.md`; two tracks taking the same ADR number; stacked branches going stale when a lower PR merges; two tracks changing the same orchestrator module; and a claimed work package that stays "in progress" after its agent died.

Spike on beads `bd` 1.3.2 (embedded Dolt, the default):

- All worktrees of one repo share one database, found through the git common directory; it lives in `.beads/` of the main checkout and is not in git. A write from one worktree is seen at once from the others; no sync step.
- 10 concurrent `bd create` from two worktrees all succeeded (writes serialised by a lock, ~1 s each). `bd update --claim` is atomic: of two concurrent claims, one wins.
- `bd merge-slot acquire/release` gives one exclusive holder across worktrees.
- `bd init` by default writes agent files and hooks, sets `core.hooksPath`, commits them, and adds the GitHub repo as a Dolt remote (`bd dolt push` would publish issue data). It was run with `--skip-agents --skip-hooks`, and the Dolt remote was removed.
- A claim (`--claim`, or `-a` with `-s in_progress`) takes a 5 min lease in a node-local table. `bd heartbeat <id> --actor <holder>` refreshes it (only the holder may); `bd reclaim --older-than <d>` reverts in_progress beads whose lease expired more than `<d>` ago; `bd unclaim <id> --if-assignee <actor>` releases atomically, whoever runs it.
- `bd export` includes the merge-slot bead, lease and heartbeat timestamps, `updated_at`, and `owner` (an email address).

Claude Code 2.1.314 hook behaviour, verified:

- `SubagentStop` fires only when a subagent finishes normally (foreground and background); not on `TaskStop`, SIGINT/SIGTERM, or a subagent error.
- `PostToolUse` on `TaskStop` fires with `tool_input.task_id` = the agent id.
- A subagent error fires `StopFailure` with `agent_id`, `agent_type` and `error`.
- `SessionEnd` fires on SIGINT/SIGTERM (reason `other`); its default timeout is 1.5 s.
- Tool hooks of a subagent carry `agent_id` and `agent_type`; the main session's carry neither. `session_id` is shared with the parent, and `cwd` is always the main project directory, even for a subagent working in a worktree. `SubagentStart` carries only `agent_id` and `agent_type`, not the prompt.
- A background `Agent` call (`run_in_background: true`) returns at once: its `PostToolUse` carries the verbatim `tool_input` (description, prompt) and `tool_response.agentId` with `status: async_launched`, the same id as the subagent's `agent_id` in its hooks. `SubagentStart` fires a few ms before that `PostToolUse`; the subagent's first tool hook comes about a second after. A foreground call fires `PostToolUse(Agent)` only when the agent has finished (`status: completed`). In `claude -p`, an `Agent` call without `run_in_background` also launched in the background.
- `SendMessage` to a finished agent resumes it under the same `agent_id`: `PostToolUse(SendMessage)` carries `tool_input.to` = the agent id and `tool_response.resumedAgentId`; `SubagentStart`, its tool hooks and `SubagentStop` fire again with that id.
- `kill -9` of the Claude process: no hook fires (verified on a scratch repo: the heartbeat loop then released the bead in ~5 s).
- Untested: an API error mid-run, `PostToolUseFailure`, and the reaper's skip after sleep.

## Options considered

- Board storage:
  - Local embedded bd database, no Dolt remote, plus a committed export `docs/board.jsonl` from which `docs/progress.md` is rendered: atomic claims, merge slot, dependencies; a reviewable record in git that CI can re-render from; only one machine holds the live board.
  - bd with a Dolt remote on the GitHub repo (`refs/dolt/*`): board shared across machines; issue data and emails published, plus a sync step and conflict handling.
  - Raw `.beads/issues.jsonl` committed by every branch: board in git; every track branch that touches it conflicts.
  - Hand-edited `docs/progress.md`: no tool; conflicts and lost updates on every merge.
  - GitHub issues/projects: shared and durable; network for every status change, no claim or merge-slot primitive.
- Who claims:
  - Push: only the orchestrator assigns (claims on the agent's behalf when it spawns it); track agents never claim: one writer for assignment, no race between agents.
  - Pull: agents claim the next ready bead themselves: less orchestration; two agents can pick overlapping work, or a bead meant for another track.
- Claim lifetime:
  - Tied to the agent's lifetime by hooks (heartbeat while alive, release on every observed end), with the lease and a reaper as backstop for ends no hook sees: a dead agent's bead returns to the board within minutes.
  - Lease only, reaper on a timer: no hooks; every end, even a normal one, waits for lease expiry plus grace.
  - No expiry (first draft): simple; a crashed agent's bead stays in progress until someone notices.
- Generated files (`docs/progress.md`, `docs/board.jsonl`, ADR index, `docs/diagrams.md`):
  - Single writer: the orchestrator regenerates them in a serial sync PR after each merge batch; track PRs change only sources: no conflicts on generated files.
  - Every PR regenerates them: always fresh on main; every pair of parallel PRs conflicts on them.
  - A bot regenerates them on main after each merge: no sync PR; needs a workflow with write access to main.
- Branch updates after a merge:
  - `git rebase --update-refs origin/main`, push with `--force-with-lease`: stacked branches move together; the lease refuses to overwrite a push nobody fetched.
  - Merge `main` into the branch: no force-push; breaks the linear, rebase-merged history.
- Merge order:
  - Fixed by the orchestrator (dependency order, then assignment order): predictable; a ready PR may wait behind a slower one.
  - First ready, first merged: faster; rebases land unpredictably.
- ADR numbers:
  - Allocated by the orchestrator: no collisions.
  - Next free number at write time: collides as soon as two tracks write an ADR.

Rejected: the Dolt remote and raw JSONL trade the conflict-free board for durability the scanned export already gives; pull claims race exactly in the parallel case; lease-only and no-expiry leave a dead agent's bead stuck for long or forever; regenerating in every PR recreates the hot-file conflicts; a bot on main needs write access the factory does not have yet (see Scalability limits); hand-edited progress, merging main into branches and first-ready merging fail in the parallel case.

## Decision

- **Board.** bd in embedded mode, in `.beads/` of the main checkout, no Dolt remote; `.beads/` is never committed. One bead per WP, id `aiwf-wp<N>`, label `wp`, `blocks` dependencies as in `docs/plan.md`, metadata `wp`, `pr`, `notes`, `log`, `metrics`. Statuses `open`, `in_progress`, `in_review` (custom), `blocked`, `closed`. Follow-ups are beads too (child beads of their WP, or labelled `step6` / `ops`). Fresh checkout: `bd init --non-interactive --skip-agents --skip-hooks -p aiwf`, `bd config set status.custom "in_review:wip"`, then `bd import docs/board.jsonl`.
- **Export.** `scripts/dev/render-progress` runs `bd export`, drops the volatile fields (`updated_at`, `lease_expires_at`, `heartbeat_at`) and `owner`, drops the merge-slot bead (label `gt:slot`), sorts by id with sorted keys, scans the result with gitleaks and refuses to write on a finding (or when gitleaks is missing), writes `docs/board.jsonl`, then renders `docs/progress.md` from the export. `--check` renders from the committed export only, so CI can check it from git.
- **Single writer.** `docs/progress.md`, `docs/board.jsonl`, the ADR index (generated in `docs/adr/README.md` by `scripts/dev/render-adr-index`) and `docs/diagrams.md` (`scripts/dev/render-diagrams`, from `docs/diagrams/*.mmd`) are written only by the orchestrator, in a serial sync PR on a `sync-*` branch after each merge batch. Track PRs change only sources: ADR files, `docs/diagrams/*.mmd`. `tests/test_single_writer.py` fails when a non-`sync-*` branch changes a generated file against `origin/main` (the rule applies to a file once its generator is on main); it is written to run in CI as is.
- **Roles.**
  - Orchestrator (one session, main checkout): assigns WPs, allocates ADR numbers, fixes the merge order, and is the only writer of the board (beyond a track moving its own bead to `in_review`) and of the generated files.
  - Track agent (one per WP, a subagent of the orchestrator): works one WP in its own worktree, never claims or reassigns, never touches other tracks' files.
- **Claims tied to agent lifetime** (`scripts/aiwf/claims.py`, hooks in the committed `.claude/settings.json`):
  - Scope: track agents are background subagents of the orchestrator session. Peer Claude sessions (several terminals) are out of scope: nothing binds their claims.
  - Assignment and binding, parent side: the orchestrator spawns a track agent with the `Agent` tool, `run_in_background: true`, and a description that starts with the bead id and a colon (`aiwf-wp2: build Workflow A labels`). `PreToolUse(Agent)` denies such a spawn unless `run_in_background` is `true` and the caller is the main session, then claims the bead for actor `track-aiwf-wp<N>` (already held by that actor: allowed) or denies the spawn when the claim fails. `PostToolUse(Agent)` binds the bead to `tool_response.agentId` in `.beads/aiwf-claims.json` (gitignored with `.beads/`). Calls whose description does not start with a bead id are ignored. Hooks for an `agent_id` not yet bound are no-ops; the subagent's first tool call comes about a second after the binding.
  - Resume: `PostToolUse(SendMessage)` to a known, released agent re-binds it when its bead is still in_progress for its actor, or `in_review`.
  - Guard: a `PreToolUse(Bash)` hook denies, for subagents only, `bd` commands with `--claim`, `--assignee`/`-a` on update/create, `--force`, and `bd reclaim`/`unclaim`/`assign`. Best effort: it matches command text, and agents are not adversarial.
  - Heartbeat: `SessionStart` launches one background loop per session that runs `bd heartbeat --actor <holder>` every 2 min for the session's in_progress beads (at most once a minute per bead) Lease TTL is bd's 5 min. The loop checks every 5 s that the parent Claude process is alive; when it has died (crash, `kill -9`, so no `SessionEnd`), the loop releases the session's beads and exits.
  - Release, with up to 3 tries: `SubagentStop`, `PostToolUse(TaskStop)` (`tool_input.task_id`) and `StopFailure` with `agent_id` release that agent's bead; `SessionEnd` releases every bead of the session (timeout raised to 20 s). Release is `bd unclaim --if-assignee <holder>`, skipped when the bead is no longer in_progress (e.g. `in_review`), plus `bd merge-slot release` if the holder has the slot.
  - Backstop: the loop and the hooks run `bd reclaim --older-than 10m` at most every 2 min; a run is skipped when the reaper's previous run is older than 10 min (the machine slept, so heartbeats could not run).
  - Every hook exits 0 on internal error (except the guard's deliberate deny), has a short timeout, and does nothing when `bd` or `.beads/` is missing (cloud sessions, CI).
- **Stale-sync warning.** `SessionStart` of the main session compares a fresh export with `docs/board.jsonl` and each generated file with its sources (`aiwf.generated.stale`) and prints a warning when a sync PR is due.
- **Merge rules.**
  - The orchestrator fixes the merge order; the maintainer merges in that order.
  - Before rebasing a branch onto a newly merged `main`, take `bd merge-slot acquire`; release it after the push. One rebase at a time.
  - Rebase with `git rebase --update-refs origin/main` and push with `git push --force-with-lease`. Never a plain `--force`, never a merge commit.
  - Check that the PR is still open before pushing to it.
- **Shared-code boundary.** These paths are shared; a track changes them only after the orchestrator's go, and the orchestrator serialises such changes (one open PR per shared path):
  - `.github/workflows/*`, `templates/`, `.claude/settings.json`
  - `scripts/aiwf/cli.py`, `publish.py`, `commands.py`, `config.py`, `labels.py`, `policy.py`, and the board tooling `gendoc.py`, `board.py`, `progress.py`, `adrindex.py`, `diagrams.py`, `generated.py`, `claims.py`; `scripts/dev/*`
  - `schema/ai-workflows.schema.json`, `schema/labels.yml`
  - `tests/test_workflow_policy.py`, `tests/test_single_writer.py`, `tests/e2e/conftest.py`, `tests/e2e/playground.py`
  - `pyproject.toml`, `uv.lock`
  - `CLAUDE.md`, `docs/spec.md`, `docs/plan.md`, `docs/diagrams/overview.mmd`, and the generated files above (orchestrator only)
- Track-owned paths: a new module per role (e.g. `scripts/aiwf/review.py`), its prompts and schemas, `tests/test_<module>.py`, `tests/e2e/test_wp<N>.py`, `docs/diagrams/wp<N>.mmd`, and an ADR with an allocated number.

Why: bd gives atomic claims and a merge slot across worktrees without a server, and the scanned export keeps a reviewable, CI-checkable record in git; push assignment and the single writer remove the races between tracks; hooks free a bead as soon as its agent ends, and the lease plus reaper cover the ends no hook sees; fixed order, update-refs and the lease keep stacked branches linear and safe.

## Scalability limits / revisit when

- The orchestrator is the single writer, and the board lives on one Mac. That is fine for up to ~3 parallel tracks on this machine.
- Revisit (shared Dolt server; post-merge regeneration of the generated files by a bot on main) when more than ~3 tracks run, or agents run off this Mac. Tracked as bead `aiwf-ldn`.

## Consequences

- Known gaps, accepted:
  - Crash or `kill -9` of the Claude process: no hook fires; the heartbeat loop releases the session's beads within ~5 s. If the loop dies too (machine crash, reboot), the bead is freed only after lease expiry plus the reaper's grace, ~15 min.
  - A spawn whose `PreToolUse(Agent)` claimed the bead but which then fails (another hook or the user refuses the call, the tool errors): the claim has no agent; it lapses with the lease and the reaper (~15 min), or the orchestrator re-spawns under the same bead id.
  - Peer sessions and foreground track agents are not supported (the guard refuses foreground track spawns).
  - A release hook that fails all tries: the bead stalls until the session ends (`SessionEnd`), or until the lease backstop if the heartbeat loop has stopped too.
  - The `PreToolUse` guard is best effort (command-text match).
  - The untested hook cases above rely on the lease backstop until tested (bead `aiwf-2en`).
- Losing the main checkout's `.beads/` loses live claims and anything not yet exported; `bd import docs/board.jsonl` restores the rest.
- Generated files on main lag behind merges until the next sync PR; the stale-sync warning says when one is due.
- A new WP diagram needs a `generated:wp<N>` block in `docs/diagrams.md`: the track adds the `.mmd`, the orchestrator adds the block in the sync PR.
- Step 6 follow-ups in `ci.yml` (beads `aiwf-8wt`, `aiwf-xg3`): `render-progress --check`, `render-adr-index --check`, `render-diagrams --check` and the single-writer check on PRs, a staleness check on main, and gitleaks on every PR.
