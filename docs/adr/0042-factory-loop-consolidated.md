# ADR-0042 · Factory loop: stop-WPs, test-first acceptance, `verify-wp` reviews the test (consolidated)

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D42`
- Supersedes: [ADR-0011](0011-factory-loop-and-independent-verifier.md), [ADR-0014](0014-executable-acceptance-tests.md)

## Context

The build loop was decided in ADR-0011 (stop-WPs, an independent verifier judging each PR's evidence pack) and ADR-0014 (an executable acceptance test written first; the verifier reviews the test). ADR-0014 removed ADR-0011's evidence pack (PR body, run conclusions, truncated logs) and moved the check before the build, and the metrics moved from a hand-edited table to the WP bead's `metrics` metadata ([ADR-0036](0036-parallel-operating-model-consolidated.md)). Agents read ADRs as live rules, so the removed text must not stay current. Background: on WP1 the log-judging verifier failed a met condition because the evidence fell in the trimmed part of a run log.

## Options considered

- Keep ADR-0011 and ADR-0014 as they are: no new file; the reader has to merge two ADRs and still meets the evidence pack and the build-then-check order as current.
- A consolidated ADR that states only the current loop and supersedes both: one place to read; one more ADR.

The first leaves removed text that agents read as current; the README rule requires a superseding ADR when part of a decision is removed or reversed.

## Decision

Replaces: ADR-0011 (its verifier judging an evidence pack of PR body, run conclusions and truncated logs; its order build → check → PR → verify; the Metrics table in `docs/progress.md` as the place metrics are written), ADR-0014 (nothing reversed; restated here).

- Stop-WPs are WP1, WP4, WP9 and WP12. Before writing code they post a short plan and wait for the maintainer's "go"; after the PR they stop and wait for review. Every other WP has no plan stop: when the review and the acceptance test pass, it opens its PR and the loop continues without waiting; the maintainer reviews these PRs in batches and always merges.
- Each WP: branch `wp<N>-<slug>` → write the acceptance test `tests/e2e/test_wp<N>.py` (plus shared helpers in `tests/e2e/`), which drives the playground and asserts every Done-when condition → `scripts/dev/verify-wp <WP>` reviews it → build → the WP is done when `AIWF_E2E=1 pytest -n 4 tests/e2e/test_wp<N>.py -v` passes (e2e slot: [ADR-0043](0043-e2e-on-the-playground-consolidated.md)) → PR whose description holds the e2e output, the run IDs it prints and the review verdict.
- Acceptance tests run only when `AIWF_E2E=1`, so CI stays network-free. Timeouts and API failures fail the test, never pass it. Tests create and clean up their own fixtures and stay scoped to their own items.
- `scripts/dev/verify-wp` runs a fresh `claude -p --model sonnet` with no tools, given only the spec, the WP's Done-when and the test source, and returns `{verdict, gaps, notes}` validated against `schema/verifier.json`: does the test assert every condition, with none missing, weakened or vacuous?
- The loop stops and goes to the maintainer when: `verify-wp` fails or errors; the policy tests (`tests/test_workflow_policy.py`) fail; an acceptance test changes after its review; a new decision is needed.
- Static properties (pinned actions, job permissions, tokenless agent jobs, no `pull_request_target` head checkout, no `secrets: inherit`) are checked by `tests/test_workflow_policy.py`, not by the acceptance tests.
- At the end of each WP the orchestrator sets the WP bead's `metrics` metadata (maintainer interventions, verifier fails, rework PRs, coordination issues); the next sync PR renders it into `docs/progress.md`.

Why: a test checks the behaviour the same way every time and reads GitHub's API rather than logs; the LLM judgement moves to one cheap, static place, the test's source, by a reviewer that cannot see the builder's reasoning; maintainer stops stay at the security-heavy WPs.

## Consequences

- Whether the test asserts the right thing is settled by the review, plus the maintainer at stop-WPs.
- Acceptance tests cost real Actions runs and model calls on the playground.
