# ADR-0032 · Workflow B runs Workflow A on its own fix PRs

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D32`

## Context

In B6, Workflow B opens the fix PR, and during B5 it pushes to `ai-fix/issue-<n>`, with the workflow's `GITHUB_TOKEN`. The spec says only the orchestrator writes to GitHub, and only with that token (`docs/spec.md:208`). It also says "Opening it triggers **Workflow A**" (`docs/spec.md:197`) and that A starts on `pull_request` opened, reopened or synchronize (`docs/spec.md:31`).

GitHub does not start normal workflow runs from `GITHUB_TOKEN` events: "events triggered by the `GITHUB_TOKEN` will not create a new workflow run", except `workflow_dispatch` and `repository_dispatch`. For `pull_request` opened, synchronize or reopened, "the resulting `pull_request` event creates workflow runs in an **approval-required** state", and they start only when "a user with write access to the repository" selects "Approve workflows to run" (https://docs.github.com/en/actions/concepts/security/github_token, under "When `GITHUB_TOKEN` triggers workflow runs"; the older page https://docs.github.com/en/actions/security-for-github-actions/security-guides/automatic-token-authentication now points there). Verified on the playground on 2026-10-31: runs [41189835705](https://github.com/esciara/ai-workflows-playground/actions/runs/41189835705) (CI) and [41189836033](https://github.com/esciara/ai-workflows-playground/actions/runs/41189836033) (AI workflows), actor `github-actions[bot]`, were created as `action_required` with 0 jobs (the API now reports them `completed`/`failure`, still 0 jobs).

So, left alone, neither the target repo's CI nor Workflow A (through the target's caller workflow) runs on a fix PR until a person acts.

## Options considered

- (a) B calls A's reusable workflow as a nested job right after it opens the PR: no new credential, no change to the target's CI config, A always reviews B's PRs; but target CI still does not run until the maintainer acts, so A sees no CI result.
- (b) B opens the PR and pushes with a GitHub App token, which does trigger workflows: CI and A run normally; but it breaks the hard rule that only the workflow's `GITHUB_TOKEN` writes to GitHub (`docs/spec.md:208`, CLAUDE.md hard rules), and adds an App key as a secret in every target repo.
- (c) B starts the target's CI with `workflow_dispatch`: dispatch events do create runs; but it needs a `workflow_dispatch` trigger added to the target's CI workflow, and agents never edit target CI config (`docs/spec.md:294`).

Option (b) was rejected because it breaks a hard rule, option (c) because it needs editing target CI config.

## Decision

Option (a). After B6 opens a non-draft fix PR, a following job in Workflow B calls Workflow A's reusable workflow for that PR (`needs:` the job that opened it, PR number passed as an input). B's own PR comment tells the maintainer that the target's CI has not run on the PR and how to start it: approve the pending runs ("Approve workflows to run" in the PR's merge box), push a commit, or close and reopen the PR.

Verdict on B's PRs (maintainer, 2026-10-31): since B's fix PRs get no target CI, Workflow A's verdict on them is `human-review` (`docs/spec.md:53`, `docs/spec.md:305`), and B always hands them to the maintainer. `docs/spec.md:197` ("its verdict label decides what the maintainer does next") applies only once CI has run on the PR.

Why: it keeps the hard rules (only `GITHUB_TOKEN` writes, no edits to target CI) and still guarantees an independent Workflow A review of every fix PR.

## Consequences

- Workflow A takes the PR number as a workflow input instead of reading it from a `pull_request` event, since the nested run's event is B's (an `issue_comment` for `/fix`, or whatever started B).
- Nesting depth: GitHub allows "a maximum of ten levels of workflows", caller included, and no loops (https://docs.github.com/en/actions/how-tos/sharing-automations/reuse-workflows). Target caller, B, A and any reusable workflow A calls is four levels, well within the limit. A must never call B.
- Permissions "can only be maintained or reduced—not elevated—throughout the chain", and "Secrets are only passed to directly called workflow" (same page). So the caller must grant B's job every scope A's jobs use (`pull-requests: write`, `issues: write`, `contents: read`), and B must pass `CLAUDE_CODE_OAUTH_TOKEN` to A explicitly. The policy tests have to allow this one nested call.
- A's CI gate (`docs/spec.md:53`) sees no CI on the fix PR. Under "CI never completes" A waits up to its budget and then posts `human-review` (`docs/spec.md:305`), so B's PRs get `human-review` until CI has run. If the maintainer approves the pending runs, the target's normal caller also runs A (the approval-required A run), which then sees CI; A must therefore tolerate two runs on the same head (one sticky comment, idempotent labels, ADR-0016).
- Draft PRs (B5 escalation after round 3, `docs/spec.md:195`) are not handed to A, matching A's "drafts are skipped" (`docs/spec.md:31`).
- B's total wall-clock time now includes A's review; the per-run budget must cover both.
- Spec reading: `docs/spec.md:197` ("Opening it triggers Workflow A") and `docs/spec.md:122` ("handed to Workflow A") are read as "B hands the PR to Workflow A", which this ADR does explicitly. The tension with `docs/spec.md:197` ("its verdict label decides") is resolved by the maintainer as stated in the Decision: the verdict label decides only once CI has run.
- Follow-up at WP9: try on the playground whether "Approve workflows to run" on a fix PR starts the target's CI and lets A re-run with a real verdict.
