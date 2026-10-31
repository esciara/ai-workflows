# ADR-0027 · Plan stop: bead is `blocked` with label `awaiting-go`

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D27`
- Amended by: [ADR-0033](0033-stall-only-risks-get-no-mechanism-claims-retired.md)

## Context

Swarm-plan decision D4. At a stop-WP's plan stop, the track agent posts its plan as its handback and ends. The release hook then unclaims the bead and it goes back to `open`, where it could be reassigned. Leaving it `in_progress` does not work either: with no live agent heartbeating it, the reaper reverts it (ADR-0015).

## Options considered

- `blocked` plus label `awaiting-go`, set by the orchestrator: survives the release hook and the reaper; the label says why.
- Leave it `in_progress`: no extra step; the reaper reverts it.
- Let it go back to `open`: no extra step; it looks free and could be reassigned.

## Decision

When a track hands back a plan at a stop, the orchestrator sets the bead to `blocked` with label `awaiting-go`. After the maintainer's "go", the orchestrator removes the label and assigns a fresh agent in the same worktree, with the plan committed there.

Why: it is the only state the claim hooks and the reaper leave alone.

## Consequences

- Stop-WPs waiting for "go" are the `blocked` beads with label `awaiting-go`.
- Track agents still never change claims; only the orchestrator sets this state.
