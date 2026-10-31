# ADR-0031 · Agents act as their own GitHub App; main protected by a ruleset

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D31`

## Context

Development agents (Claude Code sessions and subagents on the maintainer's Mac: the orchestrator and the track agents of ADR-0015) call `gh` and `git` with the maintainer's own credentials, which are admin on `esciara/ai-workflows`. That repo's `main` has no protection: the branch protection API returns 404 and `GET /repos/esciara/ai-workflows/rulesets` returns `[]`. So "agents never merge and never push to main" (CLAUDE.md, ADR-0015 merge rules: the maintainer merges) rests only on Claude Code's auto-mode classifier and on agents following instructions. Nothing deterministic stops an agent from merging, pushing to `main`, or changing repo settings.

A required-approval rule would fix that, but GitHub does not let a PR author approve their own PR. While agents open PRs as the maintainer, the maintainer cannot approve them, so requiring an approval would block every agent PR.

This is about this repo's development process, not the product: the product's hard rule "only the orchestrator writes to GitHub, using the workflow's `GITHUB_TOKEN`" (spec, Roles and permissions) is unchanged. ADR-0020 (self-approval and admin bypass allowed on the playground only) also still holds; this ADR makes approvals on `esciara/ai-workflows` real, which is what ADR-0020 assumed.

## Options considered

- Status quo (maintainer credentials, no protection): no setup; agents hold admin rights, and the rule is not enforced by anything deterministic.
- Ruleset only, agents keep the maintainer's credentials: blocks direct pushes to `main`; but required approval is impossible (the author would be the maintainer), and agents keep admin rights (rulesets, settings, bypass changes).
- Dedicated GitHub App for agents plus a ruleset on `main`: agents lose admin rights, their PRs have an author distinct from the maintainer so the maintainer can approve them, and the ruleset binds everyone; but one App to create, a key to store, and a wrapper so agents use it.
- Fine-grained PAT of a second (bot) user account: same separation; but a second account to manage, and a long-lived token instead of 1-hour installation tokens.

Options 1 and 2 were rejected because they leave agents with admin rights and no real approval. Option 4 was rejected because an App gives short-lived tokens, per-repo installation and per-permission scopes without a second account, and the repo already uses this pattern for `ai-workflows-tester` (`scripts/dev/as-tester`).

### How agents use the App's credentials

- (a) `scripts/dev/as-agent` wrapper, mirroring `scripts/dev/as-tester` (key in Keychain entry `ai-workflows-agent`, App ID in `AI_WORKFLOWS_AGENT_APP_ID`), used as `scripts/dev/as-agent gh …` and `scripts/dev/as-agent git push …`, plus a `PreToolUse` Bash hook in `.claude/settings.json` that blocks bare `gh` write commands and bare `git push` (and `gh auth token`): explicit and greppable, covers both `gh` and `git`, only affects Claude Code sessions in this repo; but every agent command needs the prefix, and the hook is a pattern match an agent could get around.
- (b) A `gh` shim earlier on `PATH` for agent sessions: transparent to agents; but does not cover `git push`, is bypassed by an absolute path (`/opt/homebrew/bin/gh`), and a `PATH` change risks leaking into the maintainer's own shells.
- (c) A git credential helper that mints the App token: transparent for `git push`; but does not cover `gh` (PR creation, comments), and a helper configured on a shared checkout or worktree also catches the maintainer's own pushes there.

Recommendation and decision: (a). It is the only option that covers both `gh` and `git`, it leaves the maintainer's own `gh` and git credentials untouched (the hook only runs in Claude Code sessions), and it reuses a pattern the repo already has. For `git`, the wrapper passes the token through `GIT_CONFIG_*` environment variables (reset `credential.helper`, then `gh auth git-credential`, which reads `GH_TOKEN`), so nothing is written to any git config and the token never appears on a command line.

## Decision

- A dedicated GitHub App, `esciara-ai-workflows-agent` (App names are global; Keychain entry `ai-workflows-agent`), owned by the maintainer, is the identity of all development agents. Repository permissions: contents write, pull requests write, issues write, workflows write (agents change `.github/workflows/*.yml` in this repo, and GitHub refuses pushes touching workflow files without it), metadata read (mandatory). No administration, no commit statuses, no checks, no secrets, no actions write.
- It is installed on `esciara/ai-workflows` and on `esciara/ai-workflows-playground`. On the playground it is needed for e2e setup that does not play the maintainer: pushing test branches, opening test-fixture issues and PRs, labelling them, and reading run results. Actions that must come from the maintainer in e2e tests (maintainer commands such as `/fix` and `/review` under ADR-0005, approvals under ADR-0020) cannot come from the App; they go through `scripts/dev/as-maintainer` (see Maintainer actions in e2e).
- `main` of `esciara/ai-workflows` is protected by a repository ruleset, enforcement Active, target the default branch, with an empty bypass list:
  - Require a pull request before merging, 1 required approval, dismiss stale approvals when new commits are pushed, require approval of the most recent reviewable push.
  - Require status checks to pass: `test` (the job in `.github/workflows/ci.yml`), source restricted to GitHub Actions so nobody else can set it.
  - Block force pushes, restrict deletions; allowed merge method: rebase (the repo's rebase-merge rule).
- Agents run every GitHub write through `scripts/dev/as-agent` (option (a)); a `PreToolUse` hook blocks bare `gh` writes, bare `git push` and `gh auth token` in Claude Code sessions. The hook is a guardrail; the ruleset and the App's missing administration permission are the enforcement.
- The maintainer approves and merges.

Why: GitHub enforces the rule instead of the classifier; agents lose admin rights; and with agent PRs authored by the App, the maintainer's approval is a real, distinct act.

### Are admins bound by a ruleset that has no bypass list?

Yes, as far as the docs say: bypass is granted only through the bypass list, for which repository admins are merely eligible ("Repository admins, organization owners, and enterprise owners" are listed as roles you can add, https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository). The rules page shows admins bound when not listed: with force pushes blocked, "organization owners or repository administrators will be unable to change or rename the default branch" unless they have bypass permission (https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets). No page states it as a general rule, so Maintainer setup step 10 checks it on the repo. The maintainer can still edit or disable the ruleset at any time; the App cannot (no administration permission).

### Can the App merge?

Merging (`PUT /repos/{owner}/{repo}/pulls/{pull_number}/merge`) needs contents write (https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps, section "Contents"), which the App has. So the ruleset, not the App's permissions, prevents agent merges:

- The App authors agent PRs and cannot approve its own PR, so without the maintainer's approval no agent PR can merge.
- Dismiss stale approvals and require approval of the most recent reviewable push stop the App from pushing new code after the maintainer approved and then merging it.
- The required `test` check comes only from GitHub Actions; the App has no commit-status or checks permission and cannot fake it.

Residual, accepted: once the maintainer has approved a PR and `test` is green, the App could technically merge it. That is acceptable, since approval is the maintainer's act on that exact head. The hook also blocks `gh pr merge` and `gh pr review --approve` for agents, so agents do not merge in practice. A second residual: the App could approve a PR authored by the maintainer; the hook blocks it, and the maintainer opens few PRs.

### Maintainer actions in e2e

Some e2e steps must come from the maintainer: maintainer commands such as `/fix` and `/review` (ADR-0005) and approvals of playground PRs (ADR-0020).

- (a) A narrow `scripts/dev/as-maintainer` command that uses the maintainer's `gh` credentials only to post comments and to submit PR reviews and approvals on `esciara/ai-workflows-playground`; the `PreToolUse` hook allows the maintainer's credentials in agent sessions only through it: e2e stays automatic and the exposed surface is two actions on one test repo; but agents can still act as the maintainer on the playground.
- (b) Treat the App as a maintainer in the playground's config: no maintainer credentials in agent sessions; but it needs a bot exception in the product's permission check, so security logic changes for the sake of tests, and GitHub reports bots' collaborator permission as `none` (verified).
- (c) The maintainer posts these by hand: no maintainer credentials for agents at all; but e2e is no longer automatic.

Decision (maintainer, 2026-10-31): (a). (b) was rejected because it changes product security logic for tests, (c) because e2e must stay automatic. The script is not implemented in this PR; it is part of the wiring follow-up.

## Maintainer setup

1. Create the App: GitHub, Settings, Developer settings, GitHub Apps, New GitHub App. Name `esciara-ai-workflows-agent`, homepage `https://github.com/esciara/ai-workflows`, webhook off, "Only on this account".
2. Repository permissions: Contents read and write, Pull requests read and write, Issues read and write, Workflows read and write, Metadata read-only. Leave everything else at No access (in particular Administration, Commit statuses, Checks, Secrets, Actions).
3. Install it on `esciara/ai-workflows` and `esciara/ai-workflows-playground` only ("Only select repositories").
4. Generate a private key (downloads a `.pem`).
5. Store it in the Keychain and delete the file: `security add-generic-password -a "$USER" -s ai-workflows-agent -w "$(base64 -i ~/Downloads/<file>.pem)"`, then `rm ~/Downloads/<file>.pem`.
6. Export the App ID (App settings page, "App ID") in your shell profile: `export AI_WORKFLOWS_AGENT_APP_ID=<id>`.
7. Check the App: `scripts/dev/as-agent gh api repos/esciara/ai-workflows --jq .full_name` prints the repo name.
8. Restart Claude Code sessions (they pick up the env var and the `PreToolUse` hook), then merge the wiring PR and every other open PR authored by your own account: once the ruleset is active you cannot approve your own PRs, so they would be unmergeable.
9. Create the ruleset: repo Settings, Rules, Rulesets, New branch ruleset. Name `main`, enforcement Active, bypass list empty, target "Include default branch". Enable: Restrict deletions; Require a pull request before merging (1 required approval, Dismiss stale pull request approvals when new commits are pushed, Require approval of the most recent reviewable push, allowed merge methods: Rebase); Require status checks to pass (add `test`, source GitHub Actions); Block force pushes. Save.
10. Check the ruleset: from a scratch branch, `git push origin HEAD:main` as yourself is rejected, and an agent PR without your approval shows merging blocked.

After step 9, agents open every PR through `scripts/dev/as-agent gh pr create …`, so the PR author is the App and the maintainer can approve it.

## Consequences

- Agent PRs, comments and pushes are authored by `esciara-ai-workflows-agent[bot]`; the maintainer approves and merges every PR to `main`, including the orchestrator's sync PRs (one more click per PR).
- A rebase pushed by the orchestrator after the maintainer approved needs a fresh approval (most-recent-push rule). Under ADR-0015 the maintainer merges in the orchestrator's order, so approve right before merging.
- Commit authorship is unchanged (git `user.name`/`user.email`); only the pusher and PR author change.
- Follow-up code, as its own PR: `scripts/dev/as-agent` (shipped with this ADR, not yet used) wired into CLAUDE.md, `scripts/dev/as-maintainer`, the `PreToolUse` Bash hook in `.claude/settings.json` (shared path, orchestrator's go needed), and the e2e harness.
- Agents keep a narrow path to the maintainer's credentials through `scripts/dev/as-maintainer` (comments and reviews on the playground), and the maintainer's `gh` token stays on the same machine, so the hook is not a hard boundary; the ruleset is.
- Pushes to the fork `opinionated-digital-center/ai-workflows-playground` are out of scope; they stay as today.
- ADR-0020 is unchanged and now matches reality on `esciara/ai-workflows`: approvals there are the maintainer's, never a self-approval.
- Note (2026-10-31): the wiring has shipped, so the sentences above saying `scripts/dev/as-maintainer` "is not implemented in this PR" and `scripts/dev/as-agent` is "not yet used" no longer hold. `scripts/dev/as-agent`, `scripts/dev/as-maintainer` and the `PreToolUse` hook `scripts/dev/guard-bash` landed in commit 0a4e402 (PR #30); PR #32 made `as-agent` push over HTTPS as the App. The ruleset on `main` is live (id 26279687) and was verified: direct pushes to `main` by the maintainer and by the App are both refused with GH013.
