# ADR-0006 · Full label set bootstrapped in WP1

- Status: Accepted
- Date: 2026-10-30
- Alias: `D6`
- Amended by: [ADR-0023](0023-labels-sync-on-dispatch-and-schedule-only.md)

## Context

Later WPs need labels to exist without each creating its own.

## Decision

WP1 label bootstrap creates the full label set, including `ai: error`, `stale`, `keep-open` and `triage: no-response`.

Why: later WPs can assume labels exist.

## Consequences

- Later WPs can assume labels exist.
