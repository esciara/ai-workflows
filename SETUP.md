# Setup checklist (manual, before the first session)

Everything here touches accounts or secrets, so you do it yourself. Tick as you go.

## 1. Repos

- [x] Create `esciara/ai-workflows` on GitHub (public, so the public playground can call its workflows; see step 4).
- [x] Unzip this pack into a local clone, commit it as the first commit, push.
- [x] Create `esciara/ai-workflows-playground` (public), with a small app and a real test suite. Any small project works; the first session can scaffold one if you ask (e.g. a tiny Node or Python library with ~20 tests).
- [x] Fork `esciara/ai-workflows-playground` into the `opinionated-digital-center` organization. PRs from that fork back to `esciara/ai-workflows-playground` are real fork PRs (no secrets), which is what WP4 tests.

## 2. Claude token

- [x] On your machine: `claude setup-token` (needs your Claude subscription login). Copy the token once; don't paste it into any chat.
- [x] Add it as a repository secret on `ai-workflows-playground`:
      Settings → Secrets and variables → Actions → New repository secret → name `CLAUDE_CODE_OAUTH_TOKEN`.
      (On every target repo later, the same.)

## 3. Outsider stand-ins (no second account needed)

Some checks need someone who is not the maintainer: an outside reporter who opens issues and replies (WP6, WP7), and a commenter without maintainer status (WP1). A GitHub App plays that role.

- [x] Create a GitHub App owned by `esciara` (Settings → Developer settings → GitHub Apps → New), named `ai-workflows-tester`. Homepage URL (required, any URL works): `https://github.com/esciara/ai-workflows`. Permissions: Issues read & write, Pull requests read & write, Metadata read. No webhook (untick Active). Where can this GitHub App be installed: **Only on this account**.
- [x] Note the **App ID** shown at the top of the App's General page (https://github.com/settings/apps/ai-workflows-tester).
- [x] Same page, section "Private keys" → **Generate a private key**. A `.pem` file downloads.
- [x] Install the App on `esciara/ai-workflows-playground` only: left sidebar → **Install App** → **Install** next to `esciara` → choose **Only select repositories** → pick `ai-workflows-playground` → **Install**.
- Store the key on your machine, never committed and never pasted into a chat. Tick the option you chose:
  - [ ] **macOS Keychain (recommended).** No key file left on disk, nothing in dotfiles or backups. Run `security add-generic-password -a esciara -s ai-workflows-tester -w "$(base64 -i ~/Downloads/ai-workflows-tester.*.pem)"`, then `rm ~/Downloads/ai-workflows-tester.*.pem`. Reads via `security` normally don't prompt; if a prompt appears, click **Always Allow** once. Add `-T ""` to the command if you want a prompt on every use instead.
  - [ ] **1Password CLI.** Save the `.pem` as a 1Password item and delete the downloaded file; the script reads it with `op read`.
  - [ ] **File, locked down.** `mv ~/Downloads/ai-workflows-tester.*.pem ~/.ssh/ai-workflows-tester.pem && chmod 600 ~/.ssh/ai-workflows-tester.pem`. Avoid `~/.config`, which is often synced to dotfiles repos.

Why an App and not the Actions bot: issues and comments made with a workflow's `GITHUB_TOKEN` don't trigger other workflows; an App's do.

## 4. Let target repos call the workflows

- [x] `ai-workflows` is public: nothing to do. (A private `ai-workflows` could only be called by private/internal repos, which rules out the public playground.)

## 5. Branch protection on the playground (needed from WP3)

- [x] Protect `main`: require a pull request, require 1 approval, dismiss stale approvals. This is what makes the AI's "Request changes" block a merge.

## 6. Chat alerts (needed from WP11)

- Slack: create an Incoming Webhook for a channel → secret `SLACK_WEBHOOK_URL`.
- Telegram: create a bot with @BotFather, get your chat ID → secrets `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

## 7. Local tools

- [x] Claude Code installed and logged in; `gh` installed and `gh auth login` done with your main account.
- [ ] Open Claude Code in the `ai-workflows` clone and paste the prompt from `KICKOFF.md`.
