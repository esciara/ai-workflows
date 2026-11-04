# ADR-0049 · Factory loop: post-review acceptance-test changes that keep the assertions are the orchestrator's call (consolidated)

- Status: Superseded by CLAUDE.md (process simplification, 2026-11-04)
- Date: 2026-11-01
- Deciders: maintainer
- Alias: `D49`
- Supersedes: [ADR-0042](0042-factory-loop-consolidated.md)

## Context

[ADR-0042](0042-factory-loop-consolidated.md) stops the loop and goes to the maintainer whenever an acceptance test changes after its `verify-wp` review. In practice most post-review changes do not touch what the test proves: they fix run selection, waits and polling, or fixture data and texts. WP11a and WP12b alone caused three maintainer interruptions for such changes. The stop exists so that a builder cannot weaken a reviewed test to make it pass; that risk lives in the assertions and the Done-when coverage, not in the plumbing around them. Narrowing the stop reverses part of ADR-0042, so per the README rule this ADR restates the full current loop, including what [ADR-0046](0046-status-views-derived-from-beads.md) and [ADR-0048](../0048-per-wp-diagrams-required-and-generated.md) added to ADR-0042.

## Options considered

- Keep ask-always (ADR-0042 as is): the maintainer sees every post-review edit, so no weakening slips through; interrupts the maintainer for edits that change nothing the test proves (three times in one WP), and stalls non-stop WPs.
- Split by effect: changes that keep the assertions and the Done-when coverage (run selection, waits/polling, fixture data/texts) are the orchestrator's call, recorded in the WP's PR description; changes to assertions or Done-when coverage still stop and ask: removes the plumbing interruptions while keeping the maintainer on every change to what the test proves; needs a judgement of which side a change falls on, made by the orchestrator, and the record in the PR is the only trace.
- No rule after review: the test is free to change once reviewed; no interruptions at all; a builder can weaken or drop an assertion to get a green run and nobody is asked, which defeats the test-first review.

Ask-always was rejected for its cost on changes that prove nothing new; no rule was rejected because it removes the guard against weakening a reviewed test.

## Decision

Replaces: ADR-0042 (its stop on any acceptance-test change after review, now limited to changes of assertions or Done-when coverage; the rest restated).

- Stop-WPs are WP1, WP4, WP9 and WP12. Before writing code they post a short plan and wait for the maintainer's "go"; after the PR they stop and wait for review. Every other WP has no plan stop: when the review and the acceptance test pass, it opens its PR and the loop continues without waiting; the maintainer reviews these PRs in batches and always merges.
- Each WP: branch `wp<N>-<slug>` → write the acceptance test `tests/e2e/test_wp<N>.py` (plus shared helpers in `tests/e2e/`), which drives the playground and asserts every Done-when condition → `scripts/dev/verify-wp <WP>` reviews it → build → the WP is done when `AIWF_E2E=1 pytest -n 4 tests/e2e/test_wp<N>.py -v` passes (e2e slot: [ADR-0043](../0043-e2e-on-the-playground-consolidated.md)) → PR whose description holds the e2e output, the run IDs it prints and the review verdict. A split WP's acceptance test is `tests/e2e/test_wp<N><x>.py`, or the WP's `tests/e2e/test_wp<N>.py` when the split has none (ADR-0046).
- The WP's PR also adds its diagram, `docs/diagrams/wp<N>.mmd` (one per split for a split WP), part of the WP's definition of done; the sync PR renders it into `docs/diagrams.md` (ADR-0048).
- Acceptance tests run only when `AIWF_E2E=1`, so CI stays network-free. Timeouts and API failures fail the test, never pass it. Tests create and clean up their own fixtures and stay scoped to their own items.
- `scripts/dev/verify-wp` runs a fresh `claude -p --model sonnet` with no tools, given only the spec, the WP's Done-when and the test source, and returns `{verdict, gaps, notes}` validated against `schema/verifier.json`: does the test assert every condition, with none missing, weakened or vacuous?
- A change to an acceptance test after its review that keeps its assertions and its Done-when coverage (e.g. run selection, waits/polling, fixture data and texts) is the orchestrator's call; the WP's PR description records the change and why. A change that adds, removes, weakens or alters an assertion, or changes which Done-when conditions the test covers, stops the loop and goes to the maintainer. When in doubt, it counts as an assertion change.
- The loop stops and goes to the maintainer when: `verify-wp` fails or errors; the policy tests (`tests/test_workflow_policy.py`) fail; an acceptance test's assertions or Done-when coverage change after its review; a new decision is needed.
- Static properties (pinned actions, job permissions, tokenless agent jobs, no `pull_request_target` head checkout, no `secrets: inherit`) are checked by `tests/test_workflow_policy.py`, not by the acceptance tests.
- At the end of each WP the orchestrator sets the WP bead's `metrics` metadata (maintainer interventions, verifier fails, rework PRs, coordination issues); the next sync PR renders it into `docs/progress.md`.

Why: the stop guards against weakening a reviewed test, and only assertion or coverage changes can do that; plumbing fixes stay visible in the PR description, which the maintainer reads in the batch review.

## Consequences

- Whether the test asserts the right thing is settled by the review, plus the maintainer at stop-WPs and on any post-review assertion or coverage change.
- The maintainer sees plumbing changes only in the PR description, after the fact; a misclassified change is caught there or not at all.
- Acceptance tests cost real Actions runs and model calls on the playground.
