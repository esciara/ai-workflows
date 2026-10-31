# ADR-0038 · GitHub token permissions: top-level `{}`, caller grants per job, called jobs narrow (consolidated)

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D38`
- Supersedes: [ADR-0001](0001-permissions-granted-per-job-by-caller.md), [ADR-0013](0013-publish-job-pull-requests-write.md), [ADR-0017](0017-top-level-permissions-empty-in-caller-and-reusable-workflows.md)

## Context

Token permissions were decided in ADR-0001 (per-job grants by the caller, no caller-level `{}`), ADR-0013 (`pull-requests: write` for the publish job) and ADR-0017 (top-level `{}` everywhere, lifting ADR-0001's ban). Later changes made parts of them wrong: ADR-0001's ban was reversed by ADR-0017, ADR-0013's `labels` job left `commands.yml` (ADR-0023) and its agent job lost `contents: read` (ADR-0018), and ADR-0017's allowance for `ci.yml` to keep `contents: read` at top level is refused by the policy test. Agents read ADRs as live rules, so the leftover text must not stay current.

GitHub facts behind the rule (docs checked 2026-10-31): job-level permissions apply after workflow-level ones; once any permission is set, unspecified ones are `none`; `permissions: {}` grants nothing; a called workflow can only keep or reduce what the calling job grants, never raise it. `POST /repos/{o}/{r}/issues/{n}/comments` on a pull request returns 403 `Resource not accessible by integration` with `issues: write` alone ([run 41137220876](https://github.com/esciara/ai-workflows-playground/actions/runs/41137220876)).

## Options considered

- Keep ADR-0001, ADR-0013 and ADR-0017 with their amendments: no new file; the reader has to merge three ADRs and still meets a reversed ban, a removed job and an allowance the policy test refuses.
- A consolidated ADR that states only the current rule and supersedes the three: one place to read; one more ADR.

The first leaves wrong text that agents read as current; the README rule requires a superseding ADR when part of a decision is removed or reversed.

## Decision

Replaces: ADR-0001 (its ban on a caller-level `permissions: {}`), ADR-0013 (its `labels` job with `issues: write` in `commands.yml`, and `contents: read` on the agent job), ADR-0017 (its allowance for a top-level `contents: read` in `ci.yml`).

- Every workflow in this repo and in `templates/`, `ci.yml` included, starts with a top-level `permissions: {}`.
- Every job declares its own `permissions:` block with the most it needs. A job that forgets its block gets nothing and fails closed instead of inheriting the repo default.
- The caller grants each job that `uses:` a reusable workflow the maximum its called workflow needs; the called workflow's jobs narrow it with their own blocks.
- A job that comments on or labels a pull request gets `pull-requests: write` alongside `issues: write` (the 403 above). Such a job acts only on schema-validated agent JSON and makes fixed calls (a comment, a label) on the event's item, so the agent cannot steer which call is made.
- Agent jobs get `permissions: {}` ([ADR-0039](0039-agent-jobs-consolidated.md)).
- `tests/test_workflow_policy.py` (`scripts/aiwf/policy.py`) enforces it: top-level `permissions` exactly `{}`, a block on every job, no `write-all`, no `secrets: inherit`, agent jobs `{}`.

Why: least privilege by default, and a called workflow cannot be given more than the caller grants, so grants live on the caller's jobs and are narrowed in the called jobs.

## Consequences

- `pull-requests: write` also allows editing a PR's title and body, labels, requesting reviewers, and closing or reopening PRs; the publish jobs' fixed calls keep agents from steering that.
- Approving or creating PRs with `GITHUB_TOKEN` is also gated by the repo setting "Allow GitHub Actions to create and approve pull requests". The playground has it off; the install guide (WP14) tells installers to keep it off.
- Pushing or merging needs `contents: write`; no job holds it today. The caller already grants it to the `triage` job for Workflow B's fix branches, and the called jobs narrow it to `contents: read` until then.
- Residual supply-chain risk while callers reference a branch of ai-workflows: a compromised or buggy ref could use these scopes. Pinning: [ADR-0040](0040-code-ref-and-pinning-consolidated.md).
- Not stated in the GitHub docs: whether a calling job with no block under a top-level `{}` gets `{}` or the repo default. It matters only for a missing block, which the policy test forbids.
