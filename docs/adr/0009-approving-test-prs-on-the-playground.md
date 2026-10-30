# ADR-0009 · Approving test PRs on the playground

- Status: Accepted
- Date: 2026-10-30
- Alias: `D9`

## Context

A solo maintainer cannot approve his own PRs, and branch protection stays on.

## Decision

Test PRs come from the fork (`opinionated-digital-center/ai-workflows-playground`) or the tester App so `esciara` can approve; otherwise the maintainer merges them himself with an admin bypass.

Why: keep branch protection on.

## Consequences

- Branch protection stays on for the playground.
- PRs not from the fork or the tester App need an admin bypass to merge.
