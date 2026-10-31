# ADR-0019 · Scripts ref follows the workflow SHA; callers pin a tagged SHA

- Status: Superseded by ADR-0040
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D19`
- Amends: ADR-0002

## Context

ADR-0002 has reusable workflows check out `esciara/ai-workflows` at the input `ai_workflows_ref` (default `main`) for scripts, prompts and schema (`0002-called-workflows-load-code-by-ai-workflows-ref.md:13`). The workflow file itself comes from the ref in `uses:`. The two are set independently in the caller (`templates/caller.yml:28` and `:32`, `:39` and `:45`) and used in `commands.yml:7-10`, `:26-29`, `:51-54`, `:84-87`, `:110-113` and `config.yml:6-10`, `:43-46`. A caller can run the YAML of one commit with the scripts of another, and both default to the moving branch `main`. ADR-0013 lists the same supply-chain risk and defers pinning to WP14 (`0013-publish-job-pull-requests-write.md:22`). Checked in the GitHub docs (2026-10-31): the `job` context has `job.workflow_ref`, `job.workflow_sha`, `job.workflow_repository` and `job.workflow_file_path`; `job.workflow_sha` is "The commit SHA of the workflow file that defines the current job", for reusable workflows it refers to the reusable workflow file, the docs give an example that checks out `repository: ${{ job.workflow_repository }}` at `ref: ${{ job.workflow_sha }}`, the `job` context is available in `steps.with`, `steps.env` and `steps.run`, and these fields are not available on GitHub Enterprise Server (contexts reference). `github.workflow_sha` is not usable: the `github` context belongs to the caller (reusable workflows reference). OIDC tokens carry `job_workflow_ref` and `job_workflow_sha` (OIDC reference). Reusable workflows can be referenced by SHA, tag or branch; re-running failed jobs reuses the first attempt's SHA (reusable workflows reference).

## Options considered

- `job.workflow_sha`: each job checks out or fetches `esciara/ai-workflows` at the exact commit its YAML came from; no input to keep in sync, no new permission; but it is not on GHES and has not yet been tried on the playground.
- OIDC claims `job_workflow_ref` / `job_workflow_sha`: same information, signed; but it needs `id-token: write` in every job that loads code, which ADR-0003 and ADR-0012 keep out of agent jobs.
- Keep `ai_workflows_ref` and assert it equals `job.workflow_sha` or the ref in `job.workflow_ref`: catches a mismatch; but the caller still maintains two values, and an assert on a branch name cannot tell two commits of the same branch apart.
- Release tags only, callers pin `uses:` to a tagged SHA: fixes the moving-branch risk; but does nothing about the scripts ref, which still defaults to `main`.

Options 2 and 3 were rejected for the permission cost and the double bookkeeping. Option 4 is needed but not sufficient on its own, so it is combined with option 1.

## Decision

Reusable workflows load scripts, prompts and schema at `${{ job.workflow_sha }}` from `${{ job.workflow_repository }}` (checkout in orchestrator jobs, the token-free `git fetch` of that SHA in agent jobs), and the `ai_workflows_ref` input is removed. Pinning plan: this repo cuts semver tags (`v0.x.y`) from `main`; `templates/caller.yml` references each reusable workflow as `@<40-hex SHA> # v0.x.y`; every install other than the playground pins this way, introduced with WP14 at the latest; the playground keeps `@wp<N>-…` branches during checks (ADR-0002), which now also selects the scripts.

Why: the YAML and the code it runs come from one commit by construction, and a pinned SHA in the caller fixes both at once.

## Consequences

- `commands.yml`, `config.yml`, `templates/caller.yml` and future reusable workflows lose `ai_workflows_ref`; the playground caller is updated with them.
- Before acceptance, a playground run must show `job.workflow_sha` resolves to the `@wp<N>` branch head inside a called job and that `git fetch --depth 1 <url> <sha>` works unauthenticated (GitHub allows fetching a reachable SHA; to be confirmed in that run).
- GHES installs are unsupported until this is revisited.
- Tag cutting and the template SHA bump become a release step (Dependabot or Renovate can propose bumps in target repos).
- Policy follow-up for own reusable refs: ADR-0022.
