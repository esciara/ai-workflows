# ai-workflows

Reusable GitHub workflows that put Claude to work on a repo:

- **Workflow A — PR review.** Every pull request gets parallel review passes (correctness, security, anti-slop, tests), one GitHub review that never approves, and a verdict label: `ai-review: merge`, `changes-requested` or `human-review`.
- **Workflow B — Bug issue to fix PR.** New issues are classified; bugs are reproduced (or the reporter is asked for details), analysed, and — after the maintainer replies `/fix` — fixed in at most three implement/adversarial-review rounds, then sent through Workflow A.

A target repo adds one short caller workflow and a `.github/ai-workflows.yml` config. Models run on the maintainer's Claude subscription through Claude Code in GitHub Actions.

## Start here

1. `SETUP.md` — the manual steps (repos, fork, token, secrets, tester App, branch protection).
2. `KICKOFF.md` — the prompt for the first Claude Code session.
3. `docs/spec.md` — what is built. `docs/plan.md` — the order, as 15 work packages. `docs/progress.md` — where things stand.

## Status

Not built yet — see `docs/progress.md`.
