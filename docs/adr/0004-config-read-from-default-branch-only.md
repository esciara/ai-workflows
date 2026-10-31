# ADR-0004 · Config read from the default branch only

- Status: Accepted
- Date: 2026-10-30
- Alias: `D4`
- Amended by: [ADR-0028](0028-fixed-e2e-caller-on-the-playground.md)

## Context

A PR must not be able to change the rules it is reviewed under.

## Decision

`.github/ai-workflows.yml` is always read from the target repo's default branch via the contents API, never from the PR head. Exception: the reusable `config.yml` input `config_ref` is honoured only when `github.event_name == 'workflow_dispatch'` (manual runs need write access); it exists for diagnostics such as the WP0 invalid-config check.

Why: a PR must not be able to change the rules it is reviewed under.

## Consequences

- Config changes in a PR take effect only once merged to the default branch.
- `config_ref` is usable only from manual (`workflow_dispatch`) runs, for diagnostics.
