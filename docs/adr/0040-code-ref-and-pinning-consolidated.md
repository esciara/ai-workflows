# ADR-0040 · Code ref follows the workflow SHA; own reusable refs pinned to a tagged SHA from WP14 (consolidated)

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D40`
- Supersedes: [ADR-0002](0002-called-workflows-load-code-by-ai-workflows-ref.md), [ADR-0019](0019-scripts-ref-follows-the-workflow-sha.md), [ADR-0022](0022-own-reusable-workflow-refs-pinned-to-a-sha-from-wp14.md)

## Context

Where reusable workflows load their code from, and how callers pin them, was decided in ADR-0002 (input `ai_workflows_ref`, playground on `@wp<N>-…` branches), ADR-0019 (load at `job.workflow_sha`, input removed, callers pin a tagged SHA) and ADR-0022 (own refs exempt from the SHA rule until WP14). Later changes made parts of them wrong: ADR-0019 removed `ai_workflows_ref`, and the playground no longer points its caller at `@wp<N>-…` branches during checks: its normal caller uses `@main`, and WP branches are tested through the e2e caller at `@e2e-target` ([ADR-0043](0043-e2e-on-the-playground-consolidated.md)). ADR-0019 and ADR-0022 still say the playground keeps `@wp<N>-…` branches. Agents read ADRs as live rules, so the leftover text must not stay current.

GitHub facts (docs checked 2026-10-31): `job.workflow_sha` is the commit of the workflow file that defines the current job, for a reusable workflow its own file; `job.workflow_repository` is its repository; both are available in `steps.with`, `steps.env` and `steps.run`, and not on GitHub Enterprise Server. `github.workflow_sha` belongs to the caller. Re-running failed jobs reuses the first attempt's SHA.

## Options considered

- Keep ADR-0002, ADR-0019 and ADR-0022 with their amendments: no new file; the reader has to merge three ADRs and still meets `ai_workflows_ref` and `@wp<N>-…` playground refs as current.
- A consolidated ADR that states only the current rule and supersedes the three: one place to read; one more ADR.

The first leaves wrong text that agents read as current; the README rule requires a superseding ADR when part of a decision is removed or reversed.

## Decision

Replaces: ADR-0002 (its `ai_workflows_ref` input defaulting to `main`, and the playground pointing at `@wp<N>-…` branches during checks), ADR-0019 and ADR-0022 (their statement that the playground caller keeps `@wp<N>-…` branches).

- Reusable workflows load scripts, prompts and schema from `${{ job.workflow_repository }}` at `${{ job.workflow_sha }}`: `actions/checkout` in orchestrator jobs, an unauthenticated `git fetch` of that SHA in agent jobs ([ADR-0039](0039-agent-jobs-consolidated.md)). There is no input for the code ref; the YAML and the code it runs come from one commit.
- Releases: this repo cuts semver tags (`v0.x.y`) from `main`. `templates/caller.yml` references each reusable workflow as `@<40-hex SHA> # v0.x.y`, and every install other than the playground pins this way, from WP14 at the latest.
- Policy: `scripts/aiwf/policy.py` exempts refs starting with `esciara/ai-workflows/` (`OWN_REUSABLE_PREFIX`) until the first release tag. No later than WP14 the exemption is dropped, so own reusable-workflow refs follow the same SHA-plus-version-comment rule as third-party actions. Local `./` refs stay exempt. Until then the template stays on `@main`.
- The playground's callers live in the playground repo, outside the policy test: the normal caller references `@main`, the e2e caller `@e2e-target` ([ADR-0043](0043-e2e-on-the-playground-consolidated.md)).

Why: one commit for YAML and code by construction, and a pinned SHA in the caller fixes both at once; the template is what reaches real repos, so it meets the same bar as any other dependency.

## Consequences

- WP14 cuts the first tag, bumps `templates/caller.yml` to its SHA, drops `OWN_REUSABLE_PREFIX` and adds a policy fixture for an unpinned own ref.
- Each release bumps the template SHA and comment (Dependabot or Renovate can propose bumps in target repos).
- GHES installs are unsupported until this is revisited.
- Until WP14, installs other than the playground are not supported.
