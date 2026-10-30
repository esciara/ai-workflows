# ADR-0014 · Executable acceptance tests; verifier reviews the test

- Status: Accepted
- Date: 2026-10-30
- Alias: `D14`
- Amends: [ADR-0011](0011-factory-loop-and-independent-verifier.md) (what `scripts/dev/verify-wp` judges)

## Context

Under ADR-0011 the verifier judged a PR's evidence: its body plus each linked run's conclusion and a truncated log. On WP1 it failed a met condition ("non-maintainer ignored") because the `parse` step's "no accepted command" line fell in the part of the run log cut by the 4000 + 8000 character head/tail trim. An LLM judging run logs also hits other edge cases: which run belongs to which condition, a red run that is the expected negative, a claim in the PR body that no log backs up, and output length limits. Each one is a judgement call made again on every WP.

## Decision

- Each WP gets an executable acceptance test, `tests/e2e/test_wp<N>.py` plus shared helpers in `tests/e2e/`, that drives the playground and asserts every Done-when condition. It runs only when `AIWF_E2E=1`, so CI stays network-free. Timeouts and API failures fail the test, never pass it.
- The test is written first and reviewed by `scripts/dev/verify-wp <WP>` before the build. The verifier (fresh `claude -p --model sonnet`, no tools) gets the spec, the Done-when and the test source, and returns `{verdict, gaps, notes}` validated against `schema/verifier.json`: does the test assert every condition, with none missing, weakened or vacuous?
- The WP check is: the reviewed test passes (`AIWF_E2E=1 pytest tests/e2e/test_wp<N>.py -v`). PR evidence is that output plus the run IDs it prints.
- Any change to an acceptance test after its review stops the loop and goes to the maintainer.

Why: a test checks the behaviour the same way every time and reads GitHub's API rather than logs; the LLM judgement moves to one place where it is cheap and static, the test's source.

## Consequences

- Whether the test asserts the right thing is settled by the review, plus the maintainer at stop-WPs (WP1, WP4, WP9, WP12). A verifier fail still stops the loop.
- Static properties (pinned actions, job permissions, tokenless agents, no `pull_request_target` head checkout, no `secrets: inherit`) stay with `tests/test_workflow_policy.py`.
- The run-log evidence pack and its trimming are removed from `scripts/aiwf/verifier.py`.
- Acceptance tests cost real Actions runs and model calls on the playground; they create and clean up their own fixtures, keeping one reusable `test-fixture` issue per WP.
