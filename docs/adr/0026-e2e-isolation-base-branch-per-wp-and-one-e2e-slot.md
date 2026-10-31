# ADR-0026 · e2e isolation: base branch per WP and one e2e slot

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D26`
- Amended by: [ADR-0028](0028-fixed-e2e-caller-on-the-playground.md)

## Context

Swarm-plan decision D3. Parallel tracks run their e2e on the same playground. `issues` and `issue_comment` runs always use the caller on the playground's default branch, whose `uses:` refs are static, so two tracks that each need their own branch cannot test at the same time. `pull_request` runs use the workflow file from the merge ref, so a PR's base branch can carry its own caller.

## Options considered

- Reuse `aiwf-merge-slot` for e2e: simple; blocks rebases for the whole e2e (10–30 min).
- A separate e2e slot as a file lock: does not block merges; one more small script.
- A second playground for Workflow B: real isolation; needs maintainer setup (secrets, tester App install, fork, protection).

Reusing the merge slot stalls merges; a second playground is worth it only if the slot queues for long.

## Decision

- PR-triggered tests open their PRs against a long-lived playground branch per WP (`e2e/wp<N>`), whose caller points at that WP's branch. Main's caller is not touched.
- Issue- and comment-triggered tests take a single e2e slot: a file lock via `flock` on this Mac, auto-released when the holding process dies. The slot is held for the whole test run.

Why: PR tests need no shared state, and the lock serialises the rest without blocking merges or needing a cleanup step after a crash.

## Consequences

- Issue/comment e2e tests run one at a time across tracks.
- Test fixtures stay scoped to their own items: unique titles, no hard-coded or "latest" numbers.
- ADR-0028 replaces the caller flips with a fixed e2e caller.
