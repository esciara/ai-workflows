# Known design issues and accepted risks

Hand-maintained. Every entry links an ADR; remove an entry only when the fix merges.

## Design issues

### `verdict` approval rule assumes a personal repo

- Date: 2026-11-13
- What: the `verdict` approval rule (`scripts/aiwf/verdict.py`) identifies the maintainer by the review's `author_association == OWNER`. That works for personal repos, not org-owned ones, where a CODEOWNERS lookup would be needed.
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

### Command groups: callers must copy the new concurrency group, and some queued commands can be replaced

- Date: 2026-11-15
- What: since aiwf-1q2, templates/caller.yml gives a comment that starts with `/fix` or `/no-fix` its own concurrency group, so `/no-fix` stops a running B5 loop (the status-line guard) instead of queueing behind it for hours. Callers keep their old group until they copy the new one when bumping the pin (the playground's callers too; its e2e compares them with the template). Residuals, accepted: a `/fix` or `/no-fix` written with leading spaces or newlines stays in the item's group and queues behind a running loop; a needs-info reply can replace a pending `/retriage`, and any pending B1/B2 command can be replaced silently by a newer starter of another kind, or by a later comment that merely has ` /` in it (a run cancelled while pending cannot post a notice); a second `/fix` while B5 runs finds no `triage: awaiting-maintainer` and changes nothing, but one sent after a re-analysis and before round 1 pushes starts a second loop whose approval supersedes the first (the first stops at its next status-line check, one effective loop); a `/no-fix` after B5 finished (status still the approval) labels `fix: declined` over a pushed branch or an escalation.
- Why it matters: a replaced `/retriage` or `/reproduce` is lost without a trace (the maintainer resends).
- Current mitigation: the maintainer resends; the queued reporter-reply run reads the live labels and skips B2 when `triage: needs-info` is gone.
- Priority: P3.
- ADR: [ADR-0005](adr/0005-command-authors.md)

### Factory-run Workflow A reviews do not resolve their threads

- Date: 2026-11-26
- What: the factory runner's App has no `contents: write` (ADR-0064 decision 2), so it cannot call `resolveReviewThread` (ADR-0062); threads it opens on `factory/*` PRs on the playground stay open after a fix.
- Why it matters: fixed findings stay open until a person resolves them; only affects playground test PRs.
- Current mitigation: none needed in M1. Widening the App's permissions (for example `contents: write`) is a change to ADR-0064 decision 2 and needs the maintainer's go; consider it only if the factory leaves the playground.
- Priority: P3.
- ADR: [ADR-0064](adr/0064-mac-factory-runner-own-github-app-and-secrets-at-rest.md)

### Workflow A's review rules come from the PR's base branch, not the default branch

- Date: 2026-11-27
- What: A reads `REVIEW.md` and `CODEOWNERS` from the branch the PR targets (aiwf-t0z). A PR author, a fork's included, picks that branch, so targeting a stale branch with no or weaker `REVIEW.md` drops the repo's current rules for that review. Each of the three inputs is cut at 20,000 characters without setting `truncated`, and together they share the context cap with the diff.
- Why it matters: only advisory guidance is lost, the author cannot inject text into the rules, and the verdict stays advisory (ADR-0060).
- Current mitigation: none needed; moving to the default branch would be a one-line change.
- Priority: P3.
- ADR: [ADR-0034](adr/0034-workflow-a-agent-inputs-and-ci-gate.md)

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

### Workflow A's `resolve-threads` job holds `contents: write`, and callers must grant it

- Date: 2026-11-18
- What: GitHub refuses `resolveReviewThread` with `GITHUB_TOKEN` without `contents: write`, so since ADR-0062 the `resolve-threads` job of review.yml holds it (and `publish` only `contents: read`), and every caller's `review` job must grant `contents: write` so the called workflow can use it.
- Why it matters: a token with repository write scope exists in a job of every installed repo; a tampered job could push code. The job runs no agent, reads no PR text, checks out only this repo at the workflow SHA, and takes shape-checked node ids.
- Also: a failed resolve (warning in the `resolve-threads` log only) is not retried and the summary's open count does not include it; a person resolves the thread by hand.
- Current mitigation: the policy test pins that only `resolve-threads` writes contents in review.yml, with no agent step and no PR checkout; the job runs from the pinned release SHA.
- Priority: P3, until GitHub allows the mutation with a narrower scope.
- ADR: [ADR-0062](adr/0062-thread-resolve-in-its-own-write-job.md)

### Factory runner: model token inside the sbx VM, secrets decryptable with the age key file

- Date: 2026-11-26
- What: the factory runner on the Mac passes `CLAUDE_CODE_OAUTH_TOKEN` into each sbx VM with `sbx exec -e` (the sbx secret proxy fails with subscription tokens). Tool-less review agents, no GitHub credential in the VM and Anthropic-only egress limit what code in the VM can do. At rest, the token and the factory App key sit in a SOPS-encrypted file whose age key is a 0600 file of the `factory` user, readable by `factory` and by admins.
- Why it matters: a sandbox escape, a mistake in the egress policy or code running as `factory` could read the token (subscription misuse until revoked) and the App key (write on the playground only).
- Current mitigation: accepted risk (maintainer, 2026-11-26). Token never in argv, DBOS records or logs; the App is installed on the playground only with no contents write; FileVault; Time Machine excludes the key file.
- Upgrade trigger (ADR-0064 decision 7): new ADR before any other repo, agents with tools or a workspace mount on the Mac, a second admin or user, or any sign of misuse; it weighs unseal after boot, the age key in the Secure Enclave or a hardware key, a credential proxy, a token vendor.
- Priority: P2, before the factory leaves the playground.
- ADR: [ADR-0064](adr/0064-mac-factory-runner-own-github-app-and-secrets-at-rest.md)

### guard-bash blocks any command whose text merely mentions a push to the main branch (aiwf-2gp)

- Date: 2026-11-26
- What: `scripts/dev/guard-bash` (`aiwf.devguard.decide`) ends with a text pattern that blocks a command containing a `git` push to `main` anywhere in its text, so an `echo` or a `bd create --description` that quotes such a command is blocked too. Real `git worktree add … origin/main` and branch names like `wp1-push-fix` are no longer blocked (fixed earlier). The merge, token and delete patterns in `ALWAYS` match text the same way.
- Why it matters: a false positive costs a retry (put the text in a file, or reword it); it never lets a push through.
- Current mitigation: accepted risk (maintainer, 2026-11-26). The catch-all text pattern stays because it also covers shapes the argv parser can miss (unbalanced quotes fall back to a naive split) and the guard is a CODEOWNERS-protected security control; the ruleset on `main` is the real boundary (ADR-0031).
- Priority: P3, accepted; revisit only if the retries become frequent.
- ADR: [ADR-0031](adr/0031-agents-act-as-their-own-github-app-main-protected-by-a-ruleset.md)
