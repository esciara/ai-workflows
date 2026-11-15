# ADR-0061 · Workflow B pushes a branch; the maintainer opens the PR

- Status: Accepted
- Date: 2026-11-15
- Deciders: maintainer
- Alias: `D61`
- Supersedes: [ADR-0032](archive/0032-workflow-b-runs-workflow-a-on-its-own-fix-prs.md)

## Context

The spec had Workflow B open a draft PR when B5 escalates and the `Fixes #n` PR in B6, both with the workflow's `GITHUB_TOKEN`. The install guide keeps the repo setting "Allow GitHub Actions to create and approve pull requests" off, and with it off that token cannot create PRs (known-issues, "Workflow B cannot open PRs"). Even when it can, a PR opened with `GITHUB_TOKEN` starts the target's CI and Workflow A only after a person approves the pending runs, which is why ADR-0032 had B call A as a nested job. ADR-0032 left open how B gets a PR at all with the setting off.

## Options considered

- (a) Turn the setting on for B: B opens its PRs as built; but it widens what every workflow's token can do on the target repo (create and approve PRs), and CI still waits for a person (ADR-0032).
- (b) Open PRs with a GitHub App token: CI and A run normally; but it breaks the hard rule that only the workflow's `GITHUB_TOKEN` writes to GitHub, and adds an App key to every target repo.
- (c) B opens nothing and only reports the branch: no new permission; but the maintainer has to write the PR text.
- (d) B pushes `ai-fix/issue-<n>` and posts a compare link with the prepared PR title and body; the maintainer opens the PR: no new permission or credential, and the PR is the maintainer's, so the target's CI and Workflow A run on it as on any PR; one click more for the maintainer.

(a) was rejected because it widens the token's power on every target repo, (b) because it breaks a hard rule, (c) because (d) costs the same and saves the maintainer the writing.

## Decision

Option (d), decided by the maintainer on 2026-11-15. Workflow B never opens a PR. B5's pushes to `ai-fix/issue-<n>` stay as built. On an approved round (B6), the orchestrator posts one issue comment that mentions the maintainer, with the compare link from the default branch to the branch (title and label `ai-fix` pre-filled) and the PR body to paste. On escalation (B5), the comment gives the same compare link when something was pushed, labels `fix: needs-maintainer` and assigns the maintainer the issue; there is no draft PR and no review request. The setting stays off for both workflows. The CI-path blocklist on B5's pushes stays as built (wider than `.github/`).

Why: it keeps every hard rule and the token's scope unchanged, and a PR opened by a person gets the target's real CI and a normal Workflow A run, which B's own PRs never had.

## Consequences

- Supersedes ADR-0032: with no PR opened by B, there is no nested A call and no "no CI, so `human-review`" rule for B's PRs; A runs on the maintainer's PR from the target's caller.
- Code to change (follow-up): `scripts/aiwf/fix_escalate.py` and the `escalate` job in `.github/workflows/triage.yml` drop the draft PR, its assignment and review request (and `pull-requests: write`); WP10 posts the compare-link comment instead of opening a PR.
- `tests/e2e/test_wp9.py` scenario 2 asserts a draft PR; that edit goes to the maintainer (approved e2e test).
- ADR-0057 point 4 (A's findings back into B5, WP19) relied on the nested A run; it needs a new trigger, decided when WP19 is planned. Any later B push to a branch that already has a PR is a `GITHUB_TOKEN` push, so its CI and A runs wait for a person's approval.
- The install guide and the "Installing" text no longer scope the setting to Workflow A only: it stays off for the whole repo.
