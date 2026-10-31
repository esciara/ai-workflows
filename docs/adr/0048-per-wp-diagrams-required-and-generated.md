# ADR-0048 · Per-WP diagrams: required by the definition of done, sections generated

- Status: Proposed
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D48`
- Amends: [ADR-0036](0036-parallel-operating-model-consolidated.md), [ADR-0042](0042-factory-loop-consolidated.md)

## Context

Per-WP diagrams (`docs/diagrams/wp<N>.mmd`) were allowed ([ADR-0036](0036-parallel-operating-model-consolidated.md), track-owned paths) but never required: nothing in the factory loop ([ADR-0042](0042-factory-loop-consolidated.md)) asked for one. Only `overview.mmd`, `wp1.mmd` and `wp5.mmd` existed; WP2a, WP2b and WP3 were done with none.

Adding one also broke CI. Each `.mmd` needed a hand-placed `generated:<stem>` marker in `docs/diagrams.md`, which only the orchestrator's sync PR may edit, while `tests/test_diagrams.py` renders the repo's `docs/diagrams.md` since [ADR-0046](0046-status-views-derived-from-beads.md). A track PR that added its `.mmd` therefore failed with "no marker for generated block(s)" until the next sync PR: the deadlock of PR #19 that [ADR-0030](0030-generated-docs-keep-single-writer-drop-enforcement.md) and [ADR-0047](0047-docs-consistency-tests-source-vs-source.md) set out to avoid. The per-WP headings and "Check on the playground" lists in `docs/diagrams.md` were hand-typed outside the markers, so they could drift from `docs/plan.md`.

## Options considered

- A: `scripts/dev/render-diagrams` generates all per-WP sections into one `generated:per-wp` block, plus a source-only consistency check, plus a definition-of-done step: a track adds only its `.mmd` and CI stays green; the check makes the diagram hard to forget; one renderer change and one test.
- B: a definition-of-done line only, the orchestrator adding each marker in the sync PR: no code; still relies on memory, and every track PR that adds a diagram stays red until the sync PR.
- C: the orchestrator draws the diagrams in the sync PR: tracks do nothing; loads the orchestrator's context, and the diagram is drawn by someone who did not build the WP.

B keeps the CI deadlock and the reliance on memory; C puts the drawing on the session least able to do it.

## Decision

Option A, with one diagram per split WP.

- A WP's PR adds `docs/diagrams/wp<N>.mmd`, part of its definition of done: a small `flowchart TD` of the WP's runtime flow (trigger → jobs/agents → schema check → GitHub writes). A WP split into plan rows ([ADR-0046](0046-status-views-derived-from-beads.md)) adds one per split, named after the row (`wp2a.mmd`, `wp2b.mmd`), and none for the WP row itself.
- `scripts/dev/render-diagrams` puts every `docs/diagrams/wp<N>[x].mmd` into the single block `generated:per-wp` of `docs/diagrams.md`, one section per diagram in the order of the WP table of `docs/plan.md`: a heading with the WP id and package from its row, the row's Done when with a link to the row, then the diagram. A per-WP stem with no plan row (e.g. `wp4x.mmd`) is an error. No per-WP marker is placed by hand. The overview and its `%% lane` handling are unchanged.
- `tests/test_docs_consistency.py` (source against source, [ADR-0047](0047-docs-consistency-tests-source-vs-source.md)) checks that every plan row whose acceptance test exists (`tests/e2e/test_wp<N>[x].py`, or for a split its WP's `test_wp<N>.py`, as `scripts/dev/verify-wp` finds it) has its `.mmd`; the failure names the file to add. It reads no generated block and not `docs/board.jsonl`.
- The orchestrator's sync PR renders the sections (`scripts/dev/render-all`), as for every generated file ([ADR-0036](0036-parallel-operating-model-consolidated.md)).

Why: the diagram is drawn by the session that built the WP, in the PR that builds it; the renderer removes the hand-placed marker that caused the deadlock, and the check turns "remember to draw it" into a CI failure (ADR-0033: wrong or missing output gets a mechanism, a stall does not).

## Consequences

- In-flight WP4, and later WP11a and WP12 (its splits WP12a, WP12b), must add their `.mmd` in their WP PR.
- The check keys on the acceptance test being on `main`, so it catches merged WPs, not started ones; a track PR that adds its test without the diagram fails CI.
- WP2a, WP2b and WP3 diagrams are backfilled here. WP0 has no acceptance test on `main`, so no diagram is required.
- The hand-written intro sentence and "Check on the playground" list of each WP section in `docs/diagrams.md` are replaced by the plan row's Done when.
