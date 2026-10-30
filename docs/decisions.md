# Decisions

Choices not covered by the spec, approved by the maintainer. Newest last. Format: decision · why · date.

## D0 · Stack: Python 3.12

Orchestrator scripts are Python 3.12 (pytest, pyyaml, jsonschema), calling GitHub through the `gh` CLI via `subprocess`. Why: preinstalled on runners, no build step, boring. Date: 2026-10-30.

## D1 · Permissions granted per job by the caller

The caller workflow grants each job the maximum its called workflow needs; the called jobs narrow it with their own `permissions:`. Never a caller-level `permissions: {}` that starves called jobs. Why: a called workflow can only reduce, never raise, what the caller grants. Date: 2026-10-30.

## D2 · Called workflows load code by `ai_workflows_ref`

Reusable workflows take input `ai_workflows_ref` (default `main`) and check out `esciara/ai-workflows` at that ref to get scripts, prompts and schema. The playground points at `@wp<N>-…` branches during checks. No `v1` tag yet. Why: lets each WP be tested end to end before merge. Date: 2026-10-30.

## D3 · Agents in their own read-only jobs

Agents run in separate jobs with `contents: read` only, no `id-token`, no `GITHUB_TOKEN` passed; they hand JSON (job output or artifact) to a separate orchestrator job that writes. To be validated in WP2; if `claude-code-action` insists on a token, stop and ask the maintainer. Why: Rule of Two, reader/writer split. Date: 2026-10-30.

## D4 · Config read from the default branch only

`.github/ai-workflows.yml` is always read from the target repo's default branch via the contents API, never from the PR head. Exception: the reusable `config.yml` input `config_ref` is honoured only when `github.event_name == 'workflow_dispatch'` (manual runs need write access); it exists for diagnostics such as the WP0 invalid-config check. Why: a PR must not be able to change the rules it is reviewed under. Date: 2026-10-30.

## D5 · Command authors

A slash command is accepted only if its author is in `maintainers` AND has write or admin permission on the repo. `/ping` is a maintainer-only diagnostic command (WP1). Why: config alone could list a login without rights; rights alone include collaborators who are not maintainers. Date: 2026-10-30.

## D6 · Full label set bootstrapped in WP1

WP1 label bootstrap creates the full label set, including `ai: error`, `stale`, `keep-open` and `triage: no-response`. Why: later WPs can assume labels exist. Date: 2026-10-30.

## D7 · Risk tiers and CI gate

`risk_paths.medium` is optional; paths matching neither list are `low`. The CI gate waits on all check runs on the head SHA except our own; optional config key `required_checks` narrows it to named checks. Why: works without config on most repos, explicit when needed. Date: 2026-10-30.

## D8 · Summary comment and review

The summary is one issue comment found by a hidden marker and updated in place. From WP3 each run also posts a short review with inline comments and a link to the summary. WP2 publishes comment + label only. Why: one place to read, no spam on reruns. Date: 2026-10-30.

## D9 · Approving test PRs on the playground

A solo maintainer cannot approve his own PRs. Test PRs come from the fork (`opinionated-digital-center/ai-workflows-playground`) or the tester App so `esciara` can approve; otherwise the maintainer merges them himself with an admin bypass. Why: keep branch protection on. Date: 2026-10-30.

## D10 · Config keys beyond the spec example

Keep `workflows: {review, triage}` from the example config; add top-level `enabled` (repo kill switch, default `true`), optional `model`, optional `required_checks`. Every object rejects unknown keys. Where the spec gives only examples, defaults are: `default_branch: main`, `limits` 400/3/2, `reporter_silence_days` 4/14/21 (ping < stale < close enforced in code), `workflows.review: true`, `workflows.triage: false`, `notify: none` (`none | slack | telegram`), `fork_prs: on-command` (`on-command | off`). Why: the spec's example values are the natural defaults; `none` and `off` let a repo opt out. Date: 2026-10-30.

## D11 · Factory loop and independent verifier

The build session stops for maintainer review only at WP1, WP4, WP9 and WP12, and whenever a new decision is needed; only those WPs keep the "post a plan and wait for go" step. Every other WP runs build → Done-when check → PR → `scripts/dev/verify-wp` pass → next WP, and the maintainer reviews those PRs in batches and always merges. `scripts/dev/verify-wp` runs a fresh `claude -p --model sonnet` with no tools, given only the spec, the WP's Done-when text and the evidence pack (PR body, linked run conclusions and truncated logs), and returns JSON validated against `schema/verifier.json`. A verifier fail or a policy-test fail (`tests/test_workflow_policy.py`: pinned actions, explicit job permissions, agent jobs without tokens or write scopes, no `pull_request_target` head checkout, no `secrets: inherit`) stops the loop. Interventions, verifier fails, rework PRs and coordination issues per WP go in the Metrics table of `docs/progress.md` for a later comparison. Why: fewer maintainer stops where the risk is low, with an independent check that cannot see the builder's reasoning; stops kept at the security-heavy WPs. Date: 2026-10-30.
