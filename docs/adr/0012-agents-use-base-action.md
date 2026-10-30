# ADR-0012 · Agents use `claude-code-action/base-action`

- Status: Accepted
- Date: 2026-10-30
- Alias: `D12`
- Amended by: [ADR-0018](0018-agent-jobs-get-no-token-permissions.md)

## Context

ADR-0003 requires agent jobs with `contents: read` only, no `id-token` and no GitHub token. The WP1 spike ran `anthropics/claude-code-action` v1.0.265 under those constraints with only `CLAUDE_CODE_OAUTH_TOKEN`. The main action always sets up a GitHub token: either the `github_token` input or an OIDC exchange for a Claude App token with contents, pull requests and issues write. It failed with `Could not fetch an OIDC token. Did you remember to add id-token: write to your workflow permissions?` ([run 41134061970](https://github.com/esciara/ai-workflows-playground/actions/runs/41134061970), job `main-action`). Its composite `action.yml` also reads `github.token` itself. The `base-action` sub-action in the same repo has no GitHub token input and no `github.token` reference; it ran with only the OAuth secret and returned `{"reply":"pong"}` as `structured_output`, which a second job read as a job output ([run 41133818227](https://github.com/esciara/ai-workflows-playground/actions/runs/41133818227), [run 41134061970](https://github.com/esciara/ai-workflows-playground/actions/runs/41134061970), job `base-action`).

## Decision

Every agent job uses `anthropics/claude-code-action/base-action`, pinned to a full commit SHA (first pin: `6d5ae526d25ce88daa2200be073e1a373167f064 # v1.0.265`), with `claude_code_oauth_token` as its only secret and structured output via `--json-schema`. Agent jobs get their prompts by an unauthenticated `git fetch` of the public `esciara/ai-workflows` at `ai_workflows_ref`, not `actions/checkout`, whose `token` input defaults to `github.token`.

Why: it is the only entry point of the action that runs with no GitHub token and no OIDC, so agent jobs hold no GitHub credential at all (ADR-0003, Rule of Two).

## Consequences

- Agent jobs touch no GitHub token, not even implicitly through an action's defaults. Correction (ADR-0018): base-action's nested setup-node and setup-bun default to `github.token` for public downloads; ADR-0018 makes that token scope-less with `permissions: {}`.
- The main action's GitHub features (tracking comments, branch handling) are not used; the orchestrator does all GitHub writes.
- If `esciara/ai-workflows` ever goes private, the token-free prompt fetch stops working and this needs revisiting.
