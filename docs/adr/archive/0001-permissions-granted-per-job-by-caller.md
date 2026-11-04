# ADR-0001 · Permissions granted per job by the caller

- Status: Superseded by ADR-0038
- Date: 2026-10-30
- Alias: `D1`
- Amended by: [ADR-0017](0017-top-level-permissions-empty-in-caller-and-reusable-workflows.md)

## Context

A called (reusable) workflow can only reduce, never raise, what the caller grants.

## Decision

The caller workflow grants each job the maximum its called workflow needs; the called jobs narrow it with their own `permissions:`. Never a caller-level `permissions: {}` that starves called jobs.

Why: a called workflow can only reduce, never raise, what the caller grants.

## Consequences

- Caller templates declare `permissions:` per job.
- Called workflow jobs must narrow to their own minimum.
