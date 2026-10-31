# Known design issues and accepted risks

Hand-maintained. Every entry links an ADR and a bead; remove an entry only when the fix merges.

## Design issues

### Single e2e slot for all WP tests

- Date: 2026-10-31
- What: e2e runs on the playground go through one fixed caller that runs `esciara/ai-workflows/...@e2e-target`, and there is a single `e2e-target` pointer. Root cause: `uses: owner/repo/.github/workflows/x.yml@ref` is static, so all e2e runs share one mutable global target and WP tests cannot be isolated from each other.
- Why it matters: issue/comment e2e tests from parallel tracks queue behind one slot, and a stale or wrong pointer would make a test run another WP's code. The maintainer called this unsatisfactory; it must be fixed sooner rather than later.
- Current mitigation: exactly one slot, held under the e2e file lock (ADR-0043), so no test silently runs another WP's code; only items routed to the e2e caller (label `e2e-target`, or same-repo PRs from `e2e/` branches) use it.
- Tracking: bead `aiwf-6k3` (P1).
- ADR: [ADR-0043](adr/0043-e2e-on-the-playground-consolidated.md)

### Bash-capable product agents share a job with `CLAUDE_CODE_OAUTH_TOKEN`

- Date: 2026-10-31
- What: the reproducer (B2) and the implementer (B5) run project commands (`setup`, `test`, repro scripts) with Bash, in the same job as `anthropics/claude-code-action/base-action`, which holds `CLAUDE_CODE_OAUTH_TOKEN` (the maintainer's Claude subscription). A command they run, shaped by untrusted issue text or repo content, can read that token from the environment or the process tree. The spec says these agents get no secrets (`docs/spec.md:130`, agent table `docs/spec.md:210` and `docs/spec.md:212`).
- Why it matters: a prompt-injected or malicious repo command could exfiltrate the token, breaking the Rule of Two for the two agents that execute code; `permissions: {}` (ADR-0039) removes GitHub scopes but not this secret.
- Current mitigation: none yet; no Bash-capable product agent exists yet. Not accepted by the maintainer: an ADR is required before the reproduce WP starts. Candidate options: run project commands in a separate container or job that never receives the token, with the agent driving it through a narrow interface; Claude Code's sandbox hiding the environment from Bash (unverified).
- Tracking: bead `aiwf-3nh` (P1); `aiwf-wp6` (reproduce) depends on it.
- ADR: none yet (required before the reproduce WP).

## Accepted risks

### Unreviewed code on `e2e-target` runs with playground secrets

- Date: 2026-10-31
- What: code pushed to `e2e-target` is unreviewed (review happens at PR time, after e2e), yet it runs in playground Actions with the playground's `CLAUDE_CODE_OAUTH_TOKEN` (the maintainer's Claude subscription) and `GITHUB_TOKEN`.
- Why it matters: a bad WP branch could leak the token (e.g. transformed so log masking misses it, in public logs) or misuse the playground's write rights, by mistake or through prompt injection.
- Current mitigation: only ai-workflows pushers (the maintainer and agents) can put code on `e2e-target`; GitHub damage is limited to the playground; worst case is rotating the Claude token. Accepted by the maintainer on 2026-10-31.
- Tracking: bead `aiwf-71q`.
- ADR: [ADR-0043](adr/0043-e2e-on-the-playground-consolidated.md)
