# ADR-0017 · Top-level `permissions: {}` in caller and reusable workflows

- Status: Proposed
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D17`
- Amends: ADR-0001

## Context

ADR-0001 forbids "a caller-level `permissions: {}` that starves called jobs" (`0001-permissions-granted-per-job-by-caller.md:13`). Today `templates/caller.yml`, `.github/workflows/commands.yml` and `.github/workflows/config.yml` have no top-level `permissions:`; every job has its own block (`templates/caller.yml:29-30`, `:40-43`; `commands.yml:23-24`, `:45-46`, `:78-79`, `:106-108`; `config.yml:35-36`). `ci.yml:7-8` already sets a top-level `contents: read`. The policy test requires a block on every job and rejects write at top level, but does not require a top-level block (`scripts/aiwf/policy.py:109-121`), and it scans both `.github/workflows/*.yml` and `templates/*.yml` (`tests/test_workflow_policy.py:9`). Checked in the GitHub docs (2026-10-31): the token starts from the repo or org default and is "adjusted based on any configuration within the workflow file, first at the workflow level and then at the job level"; "If you specify the access for any of these permissions, all of those that are not specified are set to `none`"; `permissions: {}` disables all of them (workflow syntax, `permissions`). For reusable workflows: "If `jobs.<job_id>.permissions` is not specified in the calling job, the called workflow will have the default permissions for the `GITHUB_TOKEN`", and "The `GITHUB_TOKEN` permissions passed from the caller workflow can be only downgraded (not elevated) by the called workflow"; nested workflows can only stay the same or get stricter (reusable workflows reference).

## Options considered

- Keep ADR-0001 as is, no top-level block: nothing to change; but a job added later without a block gets the repo default, which on older repos and many orgs is read/write on everything, and only the policy test stands between that and production.
- Top-level `permissions: {}` in the caller and in every reusable workflow, with per-job grants kept: least privilege by default, and a job without a block gets nothing instead of the default; the caller's `uses:` jobs keep their own grants, so called jobs are not starved; but it is one more line per file, and an omitted job block now fails at run time (403) rather than silently over-granting.
- Top-level `contents: read` (as in `ci.yml`): jobs can still check out without a block; but it is a grant nobody asked for, and the target repo may be private.

Option 1 was rejected because it relies on the default token, which the installer controls, not us. Option 3 was rejected because it grants by default.

## Decision

Proposed: every workflow in this repo and in `templates/` starts with a top-level `permissions: {}`, and every job, including each caller job that `uses:` a reusable workflow, keeps its own `permissions:` block with the most it needs (ADR-0001's per-job rule stands). The policy test is extended to require the top-level `{}` (`ci.yml` may keep `contents: read`). ADR-0001's ban on a caller-level `{}` is lifted: starvation happens only to a caller job with no block of its own, which the policy test already forbids.

Why: job-level settings are applied after workflow-level ones, so `{}` plus per-job grants is least privilege, and any job that forgets its block fails closed instead of inheriting the repo default.

## Consequences

- One-line change to `templates/caller.yml`, `commands.yml`, `config.yml` and future reusable workflows, plus a policy rule and fixture.
- Verified in the docs: the order of application, the "unspecified become none" rule, `{}` meaning no permissions, and "only downgraded" for called workflows. Not stated in the docs: whether a calling job with no block under a top-level `{}` gets `{}` or the repo default ("default permissions" in the reusable-workflow note is ambiguous). This matters only for a missing block, which the policy forbids; a playground run with the new caller should confirm the WP1 `/ping` path still works before acceptance.
- Installers who copied an older caller keep working; the template change is advisory until WP14.
