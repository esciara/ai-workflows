# Install guide

This guide sets up the AI workflows on a GitHub repository (the target repo) in about 30 minutes. Workflow A reviews every pull request: it posts one review and labels the PR with a verdict. Workflow B triages new issues, reproduces and analyses bugs, and fixes them on a branch after a maintainer says `/fix`. Start with Workflow A alone (review only); turn on Workflow B later.

## 1. Rights checklist

Check these before you start:

- [ ] Write access to the target repo, to add the workflow file, the config file and the labels.
- [ ] Admin rights on the target repo (the owner, on a personal repo), to add secrets and to set the branch protection or ruleset.
- [ ] A ruleset on the default branch (pull request required, no force-push or deletion, conversation resolution required): the `review` job's token holds `contents: write`, and the ruleset is what keeps it from pushing to the default branch.
- [ ] A Claude subscription, for the model token. There is no Anthropic API key.
- [ ] GitHub Actions is enabled on the target repo.
- [ ] Optional, for chat notifications: a Slack incoming webhook URL, or a Telegram bot token and chat ID.

## 2. Add the model token secret

1. On your machine, run `claude setup-token` (Claude Code CLI) and follow the prompts. It prints a long-lived OAuth token.
2. In the target repo, open Settings → Secrets and variables → Actions → New repository secret.
3. Name: `CLAUDE_CODE_OAUTH_TOKEN`. Value: the token. Save.

Never paste the token anywhere else: not in a file, an issue, a chat or a commit.

Optional chat secrets, same page: `SLACK_WEBHOOK_URL`, or `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

## 3. Keep the Actions approval setting off

In Settings → Actions → General → Workflow permissions:

- "Allow GitHub Actions to create and approve pull requests" stays off (unticked). Workflow A only comments, requests changes and labels; it never approves.
- "Read repository contents and packages permissions" is fine as the default: every job asks for the permissions it needs.
- The caller's `review` job asks for `contents: write`: GitHub refuses to resolve a review thread without it, and Workflow A resolves its own threads once their finding is fixed. Only the publishing job uses it (it runs no AI agent and executes no PR code); the AI agents get no token. Risk: that token can push to unprotected branches; protected branches (your default branch with a ruleset) stay safe.
- Recommended, outside this page: in Settings → Rules → Rulesets (or Settings → Branches, branch protection) for the default branch, turn on "Require conversation resolution before merging", so review threads Workflow A has not closed block the merge. Workflow A replies to and resolves its own thread once a later run finds the finding fixed; other threads are left to people.

## 4. Copy the caller workflow

Copy `templates/caller.yml` from esciara/ai-workflows to `.github/workflows/ai-workflows.yml` in the target repo.

The caller pins every reusable workflow of esciara/ai-workflows to one release: a full 40-character commit SHA, with the release tag in a comment on the same line, for example `uses: esciara/ai-workflows/.github/workflows/review.yml@<40-hex SHA> # v0.2.0`. Keep it that way: never point it at a branch. The template holds the latest release (a tag's commit cannot contain its own SHA, so right after each tag a PR bumps the template's SHA and tag comment to it, and the tag's SHA is checked with `git ls-remote https://github.com/esciara/ai-workflows refs/tags/v0.x.y`); check it against the release list at https://github.com/esciara/ai-workflows/releases (the tag's commit SHA must match). Copy `templates/caller.yml` from the default branch (main) and keep its pin lines, which already point at the latest release: a release tag's own template cannot pin itself, and a copy taken from an older tag, such as v0.1.0, holds that tag's older pins.

Review only (recommended to start): delete the `triage` job from the copied file. Keep `notify` only if you set a chat secret.

The `silence` job runs on the daily cron (and a manual run) only when `workflows.triage` is true: it pings the maintainers on a silent needs-info issue, then actions/stale labels it `stale` and closes it as not planned. Leave the `silence` job out of a review-only install. Deleting only the `triage` job while `workflows.triage` stays true leaves `silence` running, so keep the two together.

## 5. Copy the config

Copy `templates/ai-workflows.example.yml` to `.github/ai-workflows.yml` in the target repo, then edit:

- `maintainers`: your GitHub login (and any co-maintainers). Required.
- `default_branch`: your default branch.
- `risk_paths`: paths whose changes need a human (`high`) or a closer look (`medium`).
- `workflows.review: true`, `workflows.triage: false` for review only.
- `setup`, `test` and `allowed_domains`: needed only for Workflow B, see "Turning Workflow B on". The example file ships npm values (`npm ci`, `npm test`, `registry.npmjs.org`): replace them with your project's, or Workflow B will run the wrong commands.
- `notify`: `none`, `slack`, `telegram` or both (`slack,telegram`).
- `linked_issue`: leave it out (default `issue`) unless your PRs reference work by plan id; see "Linked issues" below.

The config is read from the default branch only, so commit both files to it (a PR is fine; its own review starts once the files are on the default branch). Merge that files PR before the first run: its config/load check fails until the config is on the default branch.

## 6. Run the workflow once by hand

In the Actions tab, open "AI workflows", click "Run workflow" on the default branch (a `workflow_dispatch` run). This creates the labels (`ai-review: merge`, `ai-review: changes-requested`, `ai-review: human-review`, `ai-review: pending` and the triage labels). With a chat channel set, it also sends one test message. A daily scheduled run keeps the labels in sync (on a public repo GitHub disables scheduled workflows after 60 days without repository activity: re-enable it in the Actions tab if the labels or the silence job stop running), and so does a manual run after an upgrade (new releases may add labels). The labels run needs `actions: write`: start it from the Actions tab, or as the repo admin with `gh workflow run`.

## 7. Block merges on Request changes (optional)

In Settings → Rules → Rulesets (or Branches → branch protection) for the default branch of your repo (not ai-workflows): require a pull request before merging, with at least one approval. A Request changes review from Workflow A then blocks the merge until a maintainer approves.

## 8. Check it works

Open a small test PR from a branch of the target repo. Within about 10 minutes:

- one summary comment from github-actions appears, whose state block names the release SHA;
- exactly one `ai-review: …` verdict label is set;
- the run's log has an `aiwf-metrics` line, and the run has an `ai-workflows-metrics` artifact.

Fork PRs are reviewed only when a maintainer comments `/review` on them.

- Dependabot PRs get `ai-review: human-review` with no model call: GitHub gives its runs no secrets. A maintainer's `/review` still reviews one.
- PRs already open at install are not reviewed until their next push (or a maintainer's `/review`).
- `ai: off` on an issue or PR is the maintainer's kill switch: every workflow skips that item. `ai: error` means a run failed on that item (agent crash, time or turn limit, invalid output): open the run link in the comment. Nothing retries; remove the label and push or comment `/review` or `/retriage` to run again.
- With Workflow B on, open a test issue: within about 10 minutes it gets a `triage: …` label and one comment. The daily scheduled run never triages.

## Linked issues

By default (`linked_issue: issue`) a PR needs a linked GitHub issue: put a closing keyword in the PR body (for example `Fixes #12`) or link the issue in the PR sidebar. Workflow A reads the issues GitHub reports as closed by the PR. A PR with none gets `ai-review: human-review` with the reason "no linked issue": the reviewer has no acceptance criteria to judge against, so a maintainer decides. That is a request for a human look, not a failure.

Set `linked_issue: issue-or-plan-ref` if your PRs reference a work package or plan row instead (ADR-0053): a WP id such as `WP14` or `docs/plan.md` in the PR title or body then also counts. In that mode a PR from a branch named `wp<N>-...` also needs a GitHub Actions run ID or run URL in its description, else it gets `ai-review: human-review` ("WP PR without e2e run IDs"). A `human-review` verdict shows the verdict check as waiting for the maintainer's approval (ADR-0055).

## Upgrading

Each release is a tag `v0.x.y` on esciara/ai-workflows. To upgrade, in `.github/workflows/ai-workflows.yml` replace the SHA and the tag comment on every `uses: esciara/ai-workflows/…` line together, with the new tag's commit SHA (`git ls-remote https://github.com/esciara/ai-workflows refs/tags/v0.x.y`). Compare the new `templates/caller.yml` with yours for new jobs or permissions. Dependabot or Renovate can propose these bumps.

Upgrading to the release with WP18 (review thread replies and resolves, ADR-0057): first set `contents: write` on the `review` job (only the called workflow's `resolve-threads` job uses it, ADR-0062) of your caller (before, or in the same commit as, the pin bump). A caller that still grants `contents: read` makes GitHub refuse the whole run, not just the resolve, so a Dependabot or Renovate bump alone breaks the review.

## Turning Workflow B on

Put the `triage` and `silence` jobs back from `templates/caller.yml`, and set `workflows.triage: true` in `.github/ai-workflows.yml`. Then fill in the config below and check the runner.

What Workflow B does:

- B1 classifies every new issue (`triage: …` label and one comment). Only bugs go further.
- B2 reproduces a bug as a failing test, or asks the reporter for details (`triage: needs-info`).
- B3 and B4 find the root cause, post the analysis, label `triage: awaiting-maintainer` and wait.
- B5 runs only after a maintainer comments `/fix` (or `/fix <guidance>`; `/no-fix <reason>` declines): up to `limits.fix_rounds` implement and review rounds, each pushed to the branch `ai-fix/issue-<n>`.
- B6 posts one comment with a compare link and the PR text to paste. Workflow B never opens a PR (ADR-0061): the maintainer opens it, and Workflow A then reviews it. If the loop gives up, the issue gets `fix: needs-maintainer`, an assignment to the maintainer and a compare link to the branch.

Config for B (all three in `.github/ai-workflows.yml`):

- `setup`: the command that installs the project in the sandbox, for example `pip install -e .[test]`.
- `test`: the command that runs the tests. B2 reproduces with it and B5 uses it as the exit condition.
- `allowed_domains`: the hosts the sandbox may reach while running `setup` and `test`, for example `[pypi.org, files.pythonhosted.org]` for Python or `[registry.npmjs.org]` for npm. The default `[]` means no network: the reproducer then cannot install anything.
- The schema does not enforce `setup`, `test` or `allowed_domains` (only `maintainers` is required), but without them B2 and B5 have no install or test command and no network. Treat them as required. A diff that touches `.github/` (including this config) is never pushed by B5.

Who can start what:

- B2 starts by itself only on a bug from a trusted author: in `maintainers`, with write or admin permission (ADR-0037). On anyone else's bug, B1 stops with `triage: needs-human` and a note until a maintainer comments `/reproduce`.
- `/retriage`, `/reproduce`, `/fix` and `/no-fix` are accepted only from users listed in `maintainers` who also have write or admin permission (ADR-0005): a collaborator with write access who is not in `maintainers` is ignored.

Runner and permissions:

- The command-running jobs (B2, B5) pin `runs-on: ubuntu-24.04`: the sandbox does not start on ubuntu-26.04. They install bubblewrap with `sudo` and lift an AppArmor restriction, so they need a runner with passwordless `sudo`: GitHub-hosted `ubuntu-24.04` has it. A self-hosted runner needs the same.
- The caller's `triage` job asks for `contents: write`, `issues: write` and `pull-requests: read`. `contents: write` is for the B5 jobs that push `ai-fix/issue-<n>` (never `.github/`); that token can push to unprotected branches, so keep a ruleset on the default branch. The model token reaches the reproducer and implementer, which run project commands under the sandbox (ADR-0037, accepted risk in `docs/known-issues.md`): enable B only on a repo whose code and issue text you accept running there.
- An upgrade that keeps the old `triage` permissions (`contents: read`) fails at startup on every triage event: copy them from `templates/caller.yml`.

Reporter silence (`silence` job): after B2 asks the reporter for details, `reporter_silence_days` (default 4, 14, 21) counts from that comment. The maintainers are pinged at day 4, the issue is labelled `stale` at day 14 and closed as not planned at day 21; the stale and close days count from the issue's last update by anyone, so a maintainer's comment pushes them back. A reply from the reporter restarts B2; `keep-open`, `ai: off` and `ai: error` exempt the issue. This is the only close Workflow B makes. Removing or leaving out `silence` means needs-info issues just stay open; the `triage` job alone never closes anything.

On a public repo anyone can open an issue, and each triage run uses your Claude subscription. Two caps bound that for authors not in `maintainers`: `limits.triage_per_author_per_day` (default 3) and `limits.triage_per_day` (default 20), over a rolling 24 hours. An issue over a cap runs no agent: it gets `triage: needs-human` and a comment saying the limit is reached; comment `/retriage` on it to triage it anyway. Set either cap to 0 to never triage outside authors automatically. Your own issues, and those of anyone in `maintainers`, are never capped.
