# ADR-0018 · Agent jobs get `permissions: {}`

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D18`
- Amends: ADR-0003

## Context

ADR-0003 gives agent jobs `contents: read` (`0003-agents-in-their-own-read-only-jobs.md:13`). ADR-0012 then removed every use of that scope: prompts come from an unauthenticated `git fetch` of the public repo, not `actions/checkout` (`0012-agents-use-base-action.md:13`). The agent job in `commands.yml` still declares `contents: read` (`.github/workflows/commands.yml:78-79`). Its steps are the token-free fetch and a `jq` call (`commands.yml:83-90`) and `anthropics/claude-code-action/base-action` with only the OAuth secret (`commands.yml:91-99`). `base-action/action.yml` at the pinned SHA `6d5ae526` has no GitHub token input, but it calls `actions/setup-node@48b55a01` (v6.4.0) and `oven-sh/setup-bun@0c5077e5` (v2.2.0) without a `token:` input (`base-action/action.yml:113-125`). At those SHAs both actions default `token` to `${{ github.server_url == 'https://github.com' && github.token || '' }}` (setup-node `action.yml:18-20`, setup-bun `action.yml:42-44`) and use it only to read public release data (Node distributions, Bun tags) without hitting anonymous rate limits. So the job token is used implicitly, but no step needs `contents: read` on the target repo. ADR-0012's consequence "Agent jobs touch no GitHub token, not even implicitly through an action's defaults" is therefore not exact.

## Options considered

- Keep `contents: read`: no change; but the token that setup-node and setup-bun receive can read the target repo, including a private one, inside the job that handles untrusted text.
- `permissions: {}` on agent jobs: the token still exists for setup-node and setup-bun's public reads but carries no repo scope, so a leak exposes nothing; but it has to be confirmed on the playground that base-action still installs Node and Bun.
- `{}` plus overriding the nested `token` inputs: would remove the token entirely; but base-action exposes no input to pass through, so it needs a fork or wrapper of base-action.

Option 1 was rejected because it grants a scope nobody uses. Option 3 was rejected as too costly for the residual gain.

## Decision

Every agent job declares `permissions: {}`. The caller keeps granting `contents: read` to the `commands` job for the jobs that need it (`parse` today). The policy test requires `{}` on agent jobs instead of only "no write". Future agents that need the target repo's code (WP2 diff, WP6 reproducer) get it from a non-agent job as an artifact, or by a token-free fetch on public repos; any exception is a new ADR.

Why: nothing in the agent job uses `contents: read`, and with `{}` the implicit token handed to nested setup actions holds no repo access.

## Consequences

- One-line change in `commands.yml` and a stricter policy rule.
- Before acceptance, a playground `/ping` run with `{}` must show base-action still works; if setup-node or setup-bun fails without repo scope, stop and ask.
- ADR-0012's "not even implicitly" claim is corrected there (Correction note under its Consequences).
- Risk: private target repos will need the artifact route for agent inputs, which costs an extra job in WP2 and WP6.
