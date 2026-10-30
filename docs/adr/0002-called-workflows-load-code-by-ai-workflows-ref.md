# ADR-0002 · Called workflows load code by `ai_workflows_ref`

- Status: Accepted
- Date: 2026-10-30
- Alias: `D2`
- Amended by: [ADR-0019](0019-scripts-ref-follows-the-workflow-sha.md)

## Context

Each WP must be testable end to end on the playground before merge, and there is no `v1` tag yet.

## Decision

Reusable workflows take input `ai_workflows_ref` (default `main`) and check out `esciara/ai-workflows` at that ref to get scripts, prompts and schema. The playground points at `@wp<N>-…` branches during checks. No `v1` tag yet.

Why: lets each WP be tested end to end before merge.

## Consequences

- The playground points at `@wp<N>-…` branches during checks.
- Callers default to `main` until a `v1` tag exists.
