# ADR-0033 · Stall-only risks get no mechanism; claims retired

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D33`
- Amends: [ADR-0015](0015-parallel-operating-model.md), [ADR-0027](0027-plan-stop-bead-is-blocked-awaiting-go.md)

## Context

The maintainer's rule (2026-10-31): risks whose worst outcome is a stall get documented, no mechanism; mechanisms are only for security breach, wrong output or lost work.

An architecture review checked ADR-0015's agent-lifetime claims against that rule:

- Size: `scripts/aiwf/claims.py` (361 lines), `tests/test_claims.py` (313 lines), `scripts/dev/claims-hook`, and 9 hook entries in `.claude/settings.json` (SessionStart, SubagentStop, StopFailure, SessionEnd, PreToolUse Bash and Agent, PostToolUse TaskStop, Agent and SendMessage), plus a heartbeat loop, a reaper and the merge slot.
- What they guard: a crashed track agent leaving its bead `in_progress`, two agents taking the same bead, two concurrent rebases. The orchestrator is the only assigner (push model) and the only one rebasing, so the races cannot happen; a stuck bead only delays work.
- Record: no incident was ever caught by them.
- Side effect: ADR-0027 had to pick `blocked` for plan stops only because the release hook and the reaper would otherwise revert the bead.

## Options considered

- Keep the claims machinery: a crashed agent's bead is freed within minutes; ~700 lines and 9 hooks to maintain, with known untested hook cases, for a stall-only risk.
- Keep only the reaper on a timer: less code; still a mechanism for a stall, and frees beads the orchestrator may want kept.
- Retire it: the orchestrator assigns beads directly with `bd update` and checks `in_progress` beads at session start; a one-line SessionStart hook lists them.

The first two keep a mechanism for a risk whose worst outcome is a stall.

## Decision

- Removed: `scripts/aiwf/claims.py`, `scripts/dev/claims-hook`, `tests/test_claims.py`, and every claims hook entry in `.claude/settings.json` (the 9 above). No CLI registration existed.
- No heartbeat, lease, reaper, agent binding, spawn guard or merge slot. The orchestrator rebases one branch at a time; that is a convention.
- The orchestrator assigns a bead before spawning its track agent (`bd update <id> -a <actor> -s in_progress`) and is still the only assigner; a track agent still never assigns and may move only its own bead to `in_review`.
- One SessionStart hook prints the `in_progress` beads (`bd list --status in_progress`); one without a live track agent is orphaned, and the orchestrator resumes or reassigns it. It does nothing when `bd` or `.beads/` is missing.
- Kept: the `permissions.deny` entry `Bash(rm -rf *)` (guards against lost work). No hook guarded pushes to `main` or secrets; branch protection and the gitleaks scan of the board export do that and are unchanged.
- ADR-0027 stays as a status convention: a plan-stop bead is `blocked` with label `awaiting-go`, set by the orchestrator; its rationale ("the only state the claim hooks and the reaper leave alone") no longer applies, the label still says why the WP waits.

Why: every removed part guarded a stall, not a breach, wrong output or lost work.

## Consequences

- A crashed or killed track agent leaves its bead `in_progress`; the orchestrator notices at its next session start and resumes or reassigns it. Worst case: a stall until then.
- Nothing technically stops a track agent from running `bd update --claim` or `--force`; CLAUDE.md forbids it, and the worst outcome is a wrong assignee on the board, fixed by the orchestrator.
- ADR-0015's "Claims tied to agent lifetime" decision, its merge-slot merge rule and its claim-related known gaps no longer apply; bead `aiwf-2en` (untested hook cases) becomes moot.
- `scripts/aiwf/board.py` still drops lease and heartbeat fields and the merge-slot bead from the export, since bd may still hold them.
