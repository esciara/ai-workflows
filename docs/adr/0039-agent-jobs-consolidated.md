# ADR-0039 · Agent jobs: own job, `base-action`, no token scope, OAuth secret only (consolidated)

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D39`
- Supersedes: [ADR-0003](0003-agents-in-their-own-read-only-jobs.md), [ADR-0012](0012-agents-use-base-action.md), [ADR-0018](0018-agent-jobs-get-no-token-permissions.md)

## Context

How agent jobs run was decided in ADR-0003 (own read-only jobs), ADR-0012 (`claude-code-action/base-action`) and ADR-0018 (`permissions: {}`). Later changes made parts of them wrong: ADR-0003 gives agent jobs `contents: read`, which ADR-0018 removed; ADR-0012 fetches prompts at the `ai_workflows_ref` input, which ADR-0019 removed, and claims agent jobs touch no GitHub token at all, which ADR-0018 corrected. Agents read ADRs as live rules, so the leftover text must not stay current.

Rule of Two: agents read untrusted text, so they hold no write tools and no GitHub credential. The WP1 spike: the main `anthropics/claude-code-action` always sets up a GitHub token (the `github_token` input, or an OIDC exchange that fails without `id-token: write`, [run 41134061970](https://github.com/esciara/ai-workflows-playground/actions/runs/41134061970), job `main-action`) and reads `github.token` in its composite `action.yml`; its `base-action` sub-action has no GitHub token input, ran with only the OAuth secret and returned structured output that a second job read as a job output ([run 41133818227](https://github.com/esciara/ai-workflows-playground/actions/runs/41133818227)). `base-action` calls `actions/setup-node` and `oven-sh/setup-bun` without a `token:` input; both default to `github.token` and use it only to read public release data.

## Options considered

- Keep ADR-0003, ADR-0012 and ADR-0018 with their amendments and in-place corrections: no new file; the reader has to merge three ADRs and still meets `contents: read` and `ai_workflows_ref` as current.
- A consolidated ADR that states only the current rule and supersedes the three: one place to read; one more ADR.

The first leaves wrong text that agents read as current; the README rule requires a superseding ADR when part of a decision is removed or reversed.

## Decision

Replaces: ADR-0003 (its `contents: read` for agent jobs and its "to be validated in WP2"), ADR-0012 (its prompt fetch at `ai_workflows_ref`, and its claim that agent jobs touch no GitHub token even implicitly), ADR-0018 (nothing reversed; it only amended ADR-0003 and is restated here).

- Agents run in their own jobs, separate from the jobs that write. They hand their answer to a non-agent orchestrator job as a job output or a same-run artifact; the orchestrator validates it against a schema before acting.
- Every agent job declares `permissions: {}`, no `id-token`, and receives no `GITHUB_TOKEN`; its only secret is `CLAUDE_CODE_OAUTH_TOKEN`. The policy test enforces this ([ADR-0038](0038-github-token-permissions-consolidated.md)).
- Every agent job uses `anthropics/claude-code-action/base-action`, pinned to a full commit SHA (today `6d5ae526d25ce88daa2200be073e1a373167f064 # v1.0.265`), with `claude_code_oauth_token`, structured output via `--json-schema`, and `--tools StructuredOutput` (no built-in tools).
- Agent jobs get prompts and schemas by an unauthenticated `git fetch` of `${{ job.workflow_repository }}` at `${{ job.workflow_sha }}` ([ADR-0040](0040-code-ref-and-pinning-consolidated.md)), not `actions/checkout`, whose `token` input defaults to `github.token`.
- Agent jobs get target-repo content (diff, files, issue text, candidates) only from a non-agent job, as a same-run artifact downloaded without a token, inlined in the prompt ([ADR-0034](0034-workflow-a-agent-inputs-and-ci-gate.md), [ADR-0035](0035-workflow-b-classifier-inputs-dedup-and-already-fixed.md)). Any exception is a new ADR.
- The job token still exists for `base-action`'s nested setup-node and setup-bun, which use it for public downloads; with `permissions: {}` it carries no repo scope.
- Bash-capable agents: see ADR-0037 (pending).

Why: `base-action` is the only entry point of the action that runs with no GitHub token and no OIDC, and `{}` leaves the implicit token with nothing to leak, so the job that reads untrusted text holds no GitHub access.

## Consequences

- The main action's GitHub features (tracking comments, branch handling) are not used; the orchestrator does all GitHub writes.
- If `esciara/ai-workflows` ever goes private, the token-free prompt fetch stops working and this needs revisiting.
- Private target repos work, since agent inputs already come through artifacts; each agent role costs a non-agent job that gathers its inputs.
