# ADR-0046 · Status views derived from beads; split WPs get their own plan rows

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D46`
- Amends: [ADR-0036](0036-parallel-operating-model-consolidated.md), [ADR-0042](0042-factory-loop-consolidated.md)

## Context

The beads board is the status source (ADR-0036), but some views of it were typed by hand and drifted:

- `docs/diagrams/overview.mmd` hand-typed each WP's status class (`:::done`, `:::a`), so WP2 and WP5 showed as not done after their beads closed; `scripts/dev/render-diagrams` only copied the `.mmd` into `docs/diagrams.md`.
- The overview's click links and the link table under it hand-typed line numbers of `docs/plan.md`, which break whenever a row moves.
- The milestones were copied in `docs/plan.md`, `docs/progress.md` and `docs/diagrams.md`.
- `docs/progress.md` keeps only beads with `metadata.wp`, so split WPs (WP2a/WP2b, WP11a/WP11b) are invisible, and `scripts/dev/verify-wp` reads "Done when" only from the WP table of `docs/plan.md`, so a split cannot be verified.
- The three renderers are run one by one in each sync PR.

## Options considered

- Keep status hand-typed in the `.mmd`: no code; drifts every time a bead closes, as it did.
- Derive the status views from `docs/board.jsonl`: the diagram declares each WP's lane, the renderer injects the status class and computes the links from `docs/plan.md`; one small renderer change, and the diagram can no longer drift from the board.
- Generate the whole overview graph from beads (nodes, edges, labels): no `.mmd` to maintain; loses the hand-tuned layout and short labels, for a graph that rarely changes.
- A GitHub Action on `main` that re-renders the views: no sync PR step; beads live only on this Mac, and PRs opened with `GITHUB_TOKEN` do not trigger CI (ADR-0032), so its PRs could not pass the required check.

For split WPs, the maintainer chose to give each split its own row in the WP table of `docs/plan.md`, with its own Depends on, Delivers and Done when (option 1), over keeping splits only in bead descriptions: `verify-wp` then works unchanged on `WP11a`.

## Decision

- Status views are derived from `docs/board.jsonl`, never typed by hand:
  - A `.mmd` with `%% lane <lane>: WP… ` lines is a status view. It declares each WP node's lane (`base`, `a`, `b`, `x`) and the `classDef`s; `scripts/dev/render-diagrams` adds one `class` line per WP from its bead: `<lane>Done` when the WP bead and all its split beads are closed, `<lane>Wip` when one of them is in progress or in review or when some are closed and others not (e.g. the WP bead closed with a split still open), else `<lane>`. `:::` classes, `class` and `click` lines in such a `.mmd` are an error.
  - The renderer computes each node's click link from the line of its `| WP<n> |` row in `docs/plan.md` and writes the same links as a table in the generated block `generated:<name>-links`; a node without a plan row, a node without a lane, a WP without a bead (`metadata.wp`) or a missing `docs/board.jsonl` is an error.
  - A split bead is a child (`parent-child`) of the WP bead titled `WP<N><x> · …`; other children (follow-ups) do not count. `docs/progress.md` lists split beads as rows under their WP.
- A split WP gets its own row in the WP table of `docs/plan.md` (`WP2a`, `WP2b`, …) right under its WP's row, which stays; `verify-wp WP2a` reads that row's Done when. Its acceptance test is `tests/e2e/test_wp<N><x>.py`, or the WP's `tests/e2e/test_wp<N>.py` when the split has none (WP2a and WP2b both used `test_wp2.py`).
- The milestones live only in `docs/plan.md`; other docs link to it.
- `scripts/dev/render-all` runs `render-progress`, `render-adr-index` and `render-diagrams` in that order (progress first: it writes the board export the diagrams read) and stops at the first error; the orchestrator's sync PR runs it.

Why: a view that is computed from the board cannot drift from it, and the line numbers follow the plan; the layout stays hand-tuned where it rarely changes.

## Consequences

- Adds to ADR-0036: `docs/diagrams.md` is rendered from `docs/diagrams/*.mmd`, `docs/board.jsonl` and `docs/plan.md`; the sync PR runs `scripts/dev/render-all`. Nothing in ADR-0036 changes otherwise; the generated files stay a convention with no freshness check.
- Adds to ADR-0042: how a split WP names its acceptance test.
- A new WP node in the overview needs a lane in its `%% lane` line, a row in `docs/plan.md` and a bead with `metadata.wp`, or the render fails with a message saying which.
- A new split needs a plan row and a child bead titled `WP<N><x> · …`; the orchestrator creates the bead, a plan PR adds the row.
