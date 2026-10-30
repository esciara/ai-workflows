# ADR-0011 · Factory loop and independent verifier

- Status: Accepted
- Date: 2026-10-30
- Alias: `D11`

## Context

Fewer maintainer stops are wanted where the risk is low, with an independent check that cannot see the builder's reasoning; stops are kept at the security-heavy WPs.

## Decision

The build session stops for maintainer review only at WP1, WP4, WP9 and WP12, and whenever a new decision is needed; only those WPs keep the "post a plan and wait for go" step. Every other WP runs build → Done-when check → PR → `scripts/dev/verify-wp` pass → next WP, and the maintainer reviews those PRs in batches and always merges.

`scripts/dev/verify-wp` runs a fresh `claude -p --model sonnet` with no tools, given only the spec, the WP's Done-when text and the evidence pack (PR body, linked run conclusions and truncated logs), and returns JSON validated against `schema/verifier.json`.

A verifier fail or a policy-test fail (`tests/test_workflow_policy.py`: pinned actions, explicit job permissions, agent jobs without tokens or write scopes, no `pull_request_target` head checkout, no `secrets: inherit`) stops the loop.

Why: fewer maintainer stops where the risk is low, with an independent check that cannot see the builder's reasoning; stops kept at the security-heavy WPs.

## Consequences

- Interventions, verifier fails, rework PRs and coordination issues per WP go in the Metrics table of `docs/progress.md` for a later comparison.
- A verifier fail or policy-test fail stops the loop.
