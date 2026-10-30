# ADR-0007 · Risk tiers and CI gate

- Status: Accepted
- Date: 2026-10-30
- Alias: `D7`

## Context

The spec does not fix how unmatched paths are tiered or which checks the CI gate waits on.

## Decision

`risk_paths.medium` is optional; paths matching neither list are `low`. The CI gate waits on all check runs on the head SHA except our own; optional config key `required_checks` narrows it to named checks.

Why: works without config on most repos, explicit when needed.

## Consequences

- Works without config on most repos.
- Adds optional config key `required_checks`.
