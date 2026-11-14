# Install guide

This guide sets up the AI workflows on a GitHub repository (the target repo) in about 30 minutes. Workflow A reviews every pull request: it posts one review and labels the PR with a verdict. Workflow B triages new issues. Start with Workflow A alone (review only); turn on Workflow B later.

## 1. Rights checklist

Check these before you start:

- [ ] Write access to the target repo, to add the workflow file, the config file and the labels.
- [ ] Admin rights on the target repo (the owner, on a personal repo), to add secrets and to set the branch protection or ruleset.
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
- The caller's `review` job asks for `contents: write`: GitHub refuses to resolve a review thread without it, and Workflow A resolves its own threads once their finding is fixed. Only the publishing job uses it; the AI agents get no token.
- Recommended, outside this page: in Settings → Rules → Rulesets (or Settings → Branches, branch protection) for the default branch, turn on "Require conversation resolution before merging", so review threads Workflow A has not closed block the merge. Workflow A replies to and resolves its own thread once a later run finds the finding fixed; other threads are left to people.

## 4. Copy the caller workflow

Copy `templates/caller.yml` from esciara/ai-workflows to `.github/workflows/ai-workflows.yml` in the target repo.

The caller pins every reusable workflow of esciara/ai-workflows to one release: a full 40-character commit SHA, with the release tag in a comment on the same line, for example `uses: esciara/ai-workflows/.github/workflows/review.yml@<40-hex SHA> # v0.2.0`. Keep it that way: never point it at a branch. The template already holds the latest release; check it against the release list at https://github.com/esciara/ai-workflows/releases (the tag's commit SHA must match). Copy `templates/caller.yml` from the default branch (main) and keep its pin lines, which already point at the latest release: a release tag's own template cannot pin itself, and a copy taken from an older tag, such as v0.1.0, holds that tag's older pins.

Review only (recommended to start): delete the `triage` job from the copied file. Keep `notify` only if you set a chat secret.

The `silence` job runs on the daily cron when triage is on: it pings the reporter, then actions/stale labels and closes needs-info issues (not_planned). A review-only install should leave the `silence` job out too.

## 5. Copy the config

Copy `templates/ai-workflows.example.yml` to `.github/ai-workflows.yml` in the target repo, then edit:

- `maintainers`: your GitHub login (and any co-maintainers). Required.
- `default_branch`: your default branch.
- `risk_paths`: paths whose changes need a human (`high`) or a closer look (`medium`).
- `workflows.review: true`, `workflows.triage: false` for review only.
- `notify`: `none`, `slack`, `telegram` or both (`slack,telegram`).
- `linked_issue`: leave it out (default `issue`) unless your PRs reference work by plan id; see "Linked issues" below.

The config is read from the default branch only, so commit both files to it (a PR is fine; its own review starts once the files are on the default branch). Merge that files PR before the first run: its config/load check fails until the config is on the default branch.

## 6. Run the workflow once by hand

In the Actions tab, open "AI workflows", click "Run workflow" on the default branch (a `workflow_dispatch` run). This creates the labels (`ai-review: merge`, `ai-review: changes-requested`, `ai-review: human-review`, `ai-review: pending` and the triage labels). With a chat channel set, it also sends one test message. A daily scheduled run keeps the labels in sync, and so does a manual run after an upgrade (new releases may add labels). The labels run needs `actions: write`: start it from the Actions tab, or as the repo admin with `gh workflow run`.

## 7. Block merges on Request changes (optional)

In Settings → Rules → Rulesets (or Branches → branch protection) for the default branch: require a pull request before merging, with at least one approval. A Request changes review from Workflow A then blocks the merge until a maintainer approves.

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

## Turning Workflow B on

Put the `triage` and `silence` jobs back from `templates/caller.yml` and set `workflows.triage: true` in `.github/ai-workflows.yml`. Workflow B classifies new issues; it fixes bugs only after a maintainer comments `/fix`.

On a public repo anyone can open an issue, and each triage run uses your Claude subscription. Two caps bound that for authors not in `maintainers`: `limits.triage_per_author_per_day` (default 3) and `limits.triage_per_day` (default 20), over a rolling 24 hours. An issue over a cap runs no agent: it gets `triage: needs-human` and a comment saying the limit is reached; comment `/retriage` on it to triage it anyway. Set either cap to 0 to never triage outside authors automatically. Your own issues, and those of anyone in `maintainers`, are never capped.
