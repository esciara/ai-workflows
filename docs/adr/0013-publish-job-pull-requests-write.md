# ADR-0013 · Publish job gets `pull-requests: write`

- Status: Accepted
- Date: 2026-10-30
- Alias: `D13`

## Context

The orchestrator replies to commands with `POST /repos/{o}/{r}/issues/{n}/comments`. With `GITHUB_TOKEN`, that call returns HTTP 403 `Resource not accessible by integration` on a pull request when the job has only `issues: write` ([run 41137220876](https://github.com/esciara/ai-workflows-playground/actions/runs/41137220876), job `commands / publish`).

## Decision

The caller's `commands` job grants `pull-requests: write`. Inside `commands.yml` only the `publish` job uses it; `labels` keeps `issues: write`, `parse` and `agent` keep `contents: read`, and the agent job still holds no GitHub token (ADR-0003, ADR-0012).

Why: it is the narrowest scope that lets the orchestrator reply on a PR.

## Consequences

- The scope allows commenting, editing a PR's title and body, labels, requesting reviewers, and closing or reopening PRs. `publish` makes one fixed call (a comment on the event's issue or PR) built from strictly validated agent JSON, so the agent cannot steer it.
- Approving or creating PRs is also gated by the repo setting "Allow GitHub Actions to create and approve pull requests". The playground has it off (`can_approve_pull_request_reviews: false`); the install guide must tell installers to keep it off.
- Merging or pushing is impossible without `contents: write`.
- Residual risk is supply chain: callers use a branch ref of ai-workflows, so a compromised or buggy ref could close PRs or edit their bodies (the same class of risk as `issues: write` closing issues). Mitigation: pin callers to a tag or SHA, part of WP14 onboarding.
- Workflow A needs this scope anyway.
