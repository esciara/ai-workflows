# Known design issues and accepted risks

Hand-maintained. Every entry links an ADR; remove an entry only when the fix merges.

## Design issues

### Workflow B cannot open PRs with "Allow GitHub Actions to create and approve pull requests" off

- Date: 2026-11-12
- What: the install guide keeps the repo setting "Allow GitHub Actions to create and approve pull requests" off (plan open item, spec: Installing). With it off, the workflow's `GITHUB_TOKEN` cannot create pull requests, yet the spec has the orchestrator open the B5 draft PR and the B6 fix PR with that token.
- Why it matters: Workflow B's fix stage (slice 4: WP9, WP10) cannot open its PRs on a repo set up from the guide.
- Current mitigation: decided 2026-11-15 (ADR-0061): B never opens a PR; it pushes `ai-fix/issue-<n>` and posts a compare link with the PR text, and the maintainer opens the PR; the setting stays off. B5's escalation now opens no PR (comment with the compare link, label, issue assignment; branch `wp9-compare-link`), so B5 no longer depends on the setting. Remove this entry when WP10 (B6 compare-link comment) merges.
- Priority: P2, before slice 4.
- ADR: [ADR-0061](adr/0061-workflow-b-pushes-a-branch-and-the-maintainer-opens-the-pr.md) (decision); [ADR-0052](adr/0052-playground-caller-pins-the-release-metrics-in-a-run-artifact.md) (context).

### `verdict` approval rule assumes a personal repo

- Date: 2026-11-13
- What: the `verdict` approval rule (PR #90, draft) identifies the maintainer by the review's `author_association == OWNER`. That works for personal repos, not org-owned ones, where a CODEOWNERS lookup would be needed.
- Why it matters: on an org-owned repo a maintainer's approval would not turn `verdict` green.
- Current mitigation: this repo is personal; none needed yet.
- Priority: P3, before an org-owned repo adopts the rule.
- ADR: [ADR-0053](adr/0053-merge-gate-needs-the-maintainer-only-when-there-is-a-reason.md)

### B5's check job has open network egress

- Date: 2026-11-14
- What: B5's check job (WP9a) runs the round's agent-written diff (`setup`, `test`, reproduction command) as an unprivileged user with no secret and no token scope, but with unrestricted network egress; the implementer runs the same code limited to `allowed_domains` (ADR-0037).
- Why it matters: on a private repo, agent-written code could send the source out, or use the runner for up to 40 minutes.
- Current mitigation: no secret or token in the job; the code only runs after a maintainer's `/fix`. Fix: restrict the check user's egress to `allowed_domains` (e.g. an iptables owner match), or accept the risk.
- Priority: P2, before a private repo enables B5.
- ADR: [ADR-0037](adr/0037-command-running-agents-sandbox-scrub-and-trusted-gate.md)

### Upgrading the caller pin past WP9 needs wider `triage` permissions

- Date: 2026-11-14
- What: from WP9a, triage.yml has a job asking for `contents: write` (B5 push; the escalation no longer needs `pull-requests: write`, ADR-0061). A caller that bumps its pin but keeps the old `triage` job permissions (`contents: read`, `pull-requests: read`) fails at startup on every triage event, B1 included.
- Why it matters: installed repos (the playground's normal caller, esciara/pyteleinfo) break on their next upgrade unless they also copy the new permissions from templates/caller.yml.
- Current mitigation: templates/caller.yml has the new permissions; the release note must say so.
- Priority: P2, at the next release.
- ADR: [ADR-0040](adr/0040-code-ref-and-pinning-consolidated.md)

## Accepted risks

### Unreviewed code on `e2e-target-<n>` runs with playground secrets

- Date: 2026-10-31
- What: code pushed to the e2e slot refs `e2e-target-1`, `-2`, `-3` ([ADR-0056](adr/0056-three-fixed-e2e-slots-on-the-playground.md)) is unreviewed (review happens at PR time, after e2e), yet it runs in playground Actions with the playground's `CLAUDE_CODE_OAUTH_TOKEN` (the maintainer's Claude subscription) and `GITHUB_TOKEN`.
- Why it matters: a bad WP branch could leak the token (e.g. transformed so log masking misses it, in public logs) or misuse the playground's write rights, by mistake or through prompt injection.
- Current mitigation: only ai-workflows pushers (the maintainer and agents) can put code on the `e2e-target-<n>` refs; GitHub damage is limited to the playground; worst case is rotating the Claude token. Accepted by the maintainer on 2026-10-31.
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
