# ADR-0047 · Docs consistency tests: source against source only

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D47`

## Context

Several hand-written docs restate the same facts: ADR headers point at each other (`Supersedes` / `Superseded by`, `Amends` / `Amended by`), the WP table of `docs/plan.md` and `docs/diagrams/overview.mmd` both hold the WPs and their dependencies, and `docs/known-issues.md` cites ADRs. Nothing checked that they agree. A read-only review found two ADR pairs out of step on `main` (ADR-0012 and ADR-0026 listed amendments that ADR-0018 and ADR-0029 did not declare).

ADR-0030 dropped the freshness checks on generated files: they compared a render with its source, so a track PR that changed a source failed CI until the orchestrator's sync PR re-rendered, while the single-writer rule forbade the track from rendering (PR #19, CI run 41157699361). Any new check must not recreate that deadlock.

## Options considered

- No checks: nothing to maintain; drift between sources stays invisible until a reader trips on it, and agents read ADR headers as live rules.
- Checks between a render and its source (e.g. `docs/progress.md` against `docs/board.jsonl`): catches stale renders; is the freshness enforcement ADR-0030 dropped, and recreates the PR #19 deadlock.
- Structural checks between sources only, in the unit suite: a PR that changes one source must change the other in the same PR, which a track can always do; no generated file is read.

The second option was rejected by ADR-0030 already.

## Decision

`tests/test_docs_consistency.py` runs with the unit suite and compares only hand-written sources:

- ADR headers: Status is `Proposed`, `Accepted` or `Superseded by ADR-NNNN`; every referenced ADR has a file; `Supersedes` and the old ADR's `Superseded by` Status agree both ways; `Amends` and `Amended by` agree both ways; an optional `Superseded by:` header line matches the Status.
- `docs/plan.md` against `docs/diagrams/overview.mmd`: each WP row without a letter has a node and each node a row; a row's Depends on equals the node's incoming edges. Split rows (`WP2a`, ADR-0046) exist only in the plan: their WP needs a row and what they depend on needs a row.
- `docs/known-issues.md`: every `ADR-NNNN` mention and `adr/…md` link resolves to an ADR file.

Never checked: generated blocks, `docs/progress.md`, `docs/diagrams.md`, `docs/board.jsonl`. Bead ids in `docs/known-issues.md` are not checked: the only bead list in git is `docs/board.jsonl`, an export refreshed in the sync PR, so a track PR citing a new bead would fail until the next sync, the PR #19 deadlock again.

Why: a mismatch between two sources is wrong output an agent may act on, and the PR that causes it can always fix it.

## Consequences

- Adding a WP or a dependency means editing `docs/plan.md` and `overview.mmd` in the same PR; adding an amendment means editing both ADR headers.
- A bead id cited in `docs/known-issues.md` can still dangle; found by reading, not by CI.
- Fixed with this ADR: ADR-0018 now declares `Amends: ADR-0012` and ADR-0029 `Amends: ADR-0026`, matching the `Amended by` lines those ADRs already carried (header metadata only; both pairs are superseded).
