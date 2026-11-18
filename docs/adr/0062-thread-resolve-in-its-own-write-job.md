# ADR-0062 · Thread resolve runs in its own `contents: write` job

- Status: Accepted (2026-11-18, maintainer: option a on aiwf-atl)
- Date: 2026-11-18
- Deciders: maintainer
- Alias: `D62`
- Amends: [ADR-0057](0057-review-findings-lead-to-fixes.md) (which job of Workflow A holds `contents: write`)

## Context

ADR-0057 point 2 has Workflow A resolve its own inline threads when a finding is fixed. GitHub refuses the `resolveReviewThread` GraphQL mutation with `GITHUB_TOKEN` unless the job has `contents: write` (probe: playground PR #220). The `publish` job held it, so the job that reads the agents' answers and writes the summary, the review and the label also held a repository write scope, although the only call that needs it is the resolve.

## Options considered

- Keep `contents: write` on `publish` (status quo, ADR-0057 amendment): no change; the scope sits next to the code that reads agent output and writes comments, a wider blast radius than the resolve needs.
- A separate `resolve-threads` job holds `contents: write`; `publish` goes back to `contents: read` (chosen): the write scope covers one small command that takes node ids and calls one mutation; one more job and one more output.
- Drop auto-resolve; the maintainer or the dev agent resolves by hand: no write scope at all; reopens the friction ADR-0057 removed (every fixed thread needs a click, with conversation resolution gating merge, until ADR-0060).
- A GitHub App token for the resolve: narrower scope; a second credential path to set up and protect, out of proportion for one call.

## Decision

1. In `review.yml` a new job `resolve-threads` (after `publish`) is the only job with `contents: write` (plus `pull-requests: write`). `publish` has `contents: read`.
2. `publish` still replies in A's own threads, but does not resolve them. It lists the node ids to resolve in its `resolve` output, and counts them as no longer open in the summary's thread count.
3. `resolve-threads` runs `aiwf review-resolve`: it reads that list, shape-checks every id (node-id characters only), and calls the mutation for each. No agent runs in it, it reads no PR text, and it never checks out PR code: its only checkout is this repo at `job.workflow_sha`, as in every other job. A failed resolve is a warning, never a failed run.
4. Callers keep granting `contents: write` to their `review` job, since a called workflow's job cannot exceed what its caller grants. `tests/test_workflow_policy.py` pins that only `resolve-threads` writes contents in `review.yml` and that it has no agent step and no PR checkout.

Why: the write scope shrinks from the whole orchestrator job to one command with a validated input, and the Rule of Two argument stays simple to check by a test.

## Consequences

- The remaining write is an accepted risk (`docs/known-issues.md`): the token in `resolve-threads` could, if the job's code were tampered with, write repository contents; the callers' `review` job must still grant `contents: write`.
- If a resolve fails after the reply, the thread stays open for good: the finding has left A's state, so no later run retries it, and the summary count (which assumed the resolve) says one fewer than GitHub shows. The failure is a warning in the `resolve-threads` job log only, because that job holds no `issues: write` to edit the summary. A person resolves the thread by hand, as before ADR-0057.
- One more job per review run, only when there are threads to resolve.
