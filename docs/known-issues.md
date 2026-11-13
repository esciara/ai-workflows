# Known design issues and accepted risks

Hand-maintained. Every entry links an ADR; remove an entry only when the fix merges.

## Design issues

### Single e2e slot for all WP tests

- Date: 2026-10-31
- What: e2e runs on the playground go through one fixed caller that runs `esciara/ai-workflows/...@e2e-target`, and there is a single `e2e-target` pointer. Root cause: `uses: owner/repo/.github/workflows/x.yml@ref` is static, so all e2e runs share one mutable global target and WP tests cannot be isolated from each other.
- Why it matters: issue/comment e2e tests queue behind one slot, and a stale or wrong pointer would make a test run another WP's code. The maintainer called this unsatisfactory; it must be fixed sooner rather than later.
- Current mitigation: exactly one slot, held under the e2e file lock (ADR-0043), so no test silently runs another WP's code; only items routed to the e2e caller (label `e2e-target`, or same-repo PRs from `e2e/` branches) use it.
- Priority: P1 (was aiwf-6k3).
- ADR: [ADR-0043](adr/0043-e2e-on-the-playground-consolidated.md)

### Workflow B cannot open PRs with "Allow GitHub Actions to create and approve pull requests" off

- Date: 2026-11-12
- What: the install guide keeps the repo setting "Allow GitHub Actions to create and approve pull requests" off (plan open item, spec: Installing). With it off, the workflow's `GITHUB_TOKEN` cannot create pull requests, yet the spec has the orchestrator open the B5 draft PR and the B6 fix PR with that token.
- Why it matters: Workflow B's fix stage (slice 4: WP9, WP10) cannot open its PRs on a repo set up from the guide.
- Current mitigation: none needed for slice 1 (Workflow A only comments, requests changes and labels); the spec scopes the setting to Workflow A. Slice 4 decides: turn the setting on for B, or open PRs with a GitHub App token (new ADR).
- Priority: P2, before slice 4.
- ADR: [ADR-0052](adr/0052-playground-caller-pins-the-release-metrics-in-a-run-artifact.md) (context); the decision is still open.

### `verdict` approval rule assumes a personal repo

- Date: 2026-11-13
- What: the `verdict` approval rule (PR #90, draft) identifies the maintainer by the review's `author_association == OWNER`. That works for personal repos, not org-owned ones, where a CODEOWNERS lookup would be needed.
- Why it matters: on an org-owned repo a maintainer's approval would not turn `verdict` green.
- Current mitigation: this repo is personal; none needed yet.
- Priority: P3, before an org-owned repo adopts the rule.
- ADR: the merge-gate ADR (D53, ADR number 53; no link while it is not on this stack branch)

## Accepted risks

### Unreviewed code on `e2e-target` runs with playground secrets

- Date: 2026-10-31
- What: code pushed to `e2e-target` is unreviewed (review happens at PR time, after e2e), yet it runs in playground Actions with the playground's `CLAUDE_CODE_OAUTH_TOKEN` (the maintainer's Claude subscription) and `GITHUB_TOKEN`.
- Why it matters: a bad WP branch could leak the token (e.g. transformed so log masking misses it, in public logs) or misuse the playground's write rights, by mistake or through prompt injection.
- Current mitigation: only ai-workflows pushers (the maintainer and agents) can put code on `e2e-target`; GitHub damage is limited to the playground; worst case is rotating the Claude token. Accepted by the maintainer on 2026-10-31.
- Tracking: was aiwf-71q.
- ADR: [ADR-0043](adr/0043-e2e-on-the-playground-consolidated.md)

### Bash-capable product agents share a job with `CLAUDE_CODE_OAUTH_TOKEN`

- Date: 2026-10-31
- What: the reproducer (B2) and the implementer (B5) run project commands (`setup`, `test`, repro scripts) with Bash, in the same job as `anthropics/claude-code-action/base-action`, which holds `CLAUDE_CODE_OAUTH_TOKEN` (the maintainer's Claude subscription). A command they run, shaped by untrusted issue text or repo content, can read that token from the environment or the process tree. The spec says these agents get no secrets (`docs/spec.md:130`, agent table `docs/spec.md:210` and `docs/spec.md:212`).
- Why it matters: a prompt-injected or malicious repo command could exfiltrate the token, breaking the Rule of Two for the two agents that execute code; `permissions: {}` (ADR-0039) removes GitHub scopes but not this secret.
- Current mitigation: accepted risk (maintainer, 2026-11-01), mitigations per ADR-0037: Claude Code's sandbox (bubblewrap, egress allowlist, no unsandboxed fallback), `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1`, repo settings and non-sandboxed tools off, and a gate so these agents run only for trusted authors or after a maintainer command. Impact if bypassed: subscription misuse until the token is revoked; no GitHub write.
- Upgrade trigger (ADR-0037): move to a credential proxy plus container when a target repo goes public with outside contributors, on any sign of token misuse, when a sandbox or scrub bypass becomes known, or when a Claude Code upgrade weakens a setting.
- Priority: P1 (was aiwf-3nh); WP6 (reproduce) depends on it.
- ADR: [ADR-0037](adr/0037-command-running-agents-sandbox-scrub-and-trusted-gate.md)
