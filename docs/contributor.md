# Contributor guide

This guide is for people who contribute to a repository they do not maintain. The spec's contributor ladder says how far the AI may go; this guide covers level 0 (local plugin) and level 1 (your fork). Levels 2 to 4 need the upstream project's agreement and are not automated here.

## 0. Read the upstream policy first

Before you use any AI on someone else's repository, read its contribution guide and any AI policy, then go no higher than the policy allows.

- Level 0 · Local: the AI reviews your branch and analyses issues; results go to you only. Needs nothing from the repo.
- Level 1 · Your fork: the review workflow runs on pull requests inside your fork, before you open the PR upstream. Needs your fork.
- Level 2 · You post: the AI drafts review replies and issue comments, you post them as yourself. Only if the policy tolerates AI-assisted contributions.
- Level 3 · AI posts, labelled: only if the policy explicitly allows AI comments.
- Level 4 · Installed upstream: the maintainers adopt the workflows (maintainer mode, `docs/install.md`).

## 1. Level 0: the local plugin

The plugin `ai-workflows` (in `plugin/` of esciara/ai-workflows) gives Claude Code two skills. Both are read-only: they print their result in your session and post nothing to GitHub.

- `/ai-workflows:review [base]`: reviews the current branch against its base (default `origin/HEAD`) for correctness, security, tests and maintainability, and gives a verdict (`merge`, `changes-requested` or `human-review`).
- `/ai-workflows:analyse <issue number, URL or pasted text>`: finds the root cause of a bug in your local checkout and proposes a fix.

Install, once:

1. In Claude Code, run `/plugin marketplace add esciara/ai-workflows`.
2. Run `/plugin install ai-workflows@ai-workflows`.

Or try it without installing: `claude --plugin-dir <path to ai-workflows>/plugin`.

What keeps it local: the skills allow only file reads and read-only `git` commands (and `gh issue view` for `analyse`), so they cannot comment, label, push or open anything. It uses your own Claude login; no secret is needed and nothing is installed in the upstream repo.

## 2. Level 1: your fork

In your fork you are the owner, so you set up the workflows exactly like a maintainer (maintainer mode), but on your fork only. Nothing reaches the upstream repo: the review is posted on pull requests you open inside the fork.

1. GitHub disables Actions on a new fork. Open the fork's Actions tab and enable them. Leave "Allow GitHub Actions to create and approve pull requests" off (`docs/install.md`, section 3).
2. Add the `CLAUDE_CODE_OAUTH_TOKEN` secret to the fork (`docs/install.md`, section 2). Forks do not inherit secrets.
3. Copy `templates/caller.yml` to `.github/workflows/ai-workflows.yml` and `templates/ai-workflows.example.yml` to `.github/ai-workflows.yml`, as in `docs/install.md`, sections 4 and 5. Keep the release pin lines. Set `maintainers` to your own login, `default_branch` to your fork's default branch, `workflows.review: true` and `workflows.triage: false`. Delete the `triage` and `silence` jobs from the caller.
4. Commit both files to your fork's default branch only. The config is read from there. Never include them in a PR to upstream.
5. Run the workflow once by hand from the Actions tab to create the labels (`docs/install.md`, section 6).

Daily use:

- Start your work branch from the upstream default branch (`git fetch upstream`, then `git switch -c my-change upstream/main`), not from your fork's default branch, so the caller and config commits are not in it.
- Push the branch to your fork and open a pull request inside the fork (`gh pr create --repo <you>/<repo> --base <default branch> --head my-change`), never against upstream. The review runs there: one summary, inline comments and a verdict label.
- Fix what the review finds and push again. When you are satisfied and the project's policy allows what you did, open the PR upstream from the same branch, yourself, with your own description.
- Check the target before you press enter: `gh pr create` without `--repo` in a fork may offer the upstream repo.

What stays true: the workflows only comment, request changes and label; they never merge or approve. The fork's review is advisory for you alone. If upstream asks you not to use AI at all, stay at level 0 only if the policy allows even that, otherwise do not use the plugin either.
