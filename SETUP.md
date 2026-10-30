# Setup checklist (manual, before the first session)

Everything here touches accounts or secrets, so you do it yourself. Tick as you go.

## 1. Repos

- [ ] Create `ai-workflows` on GitHub (public is simplest; private works, see step 4).
- [ ] Unzip this pack into a local clone, commit it as the first commit, push.
- [ ] Create `ai-workflows-playground` (public), with a small app and a real test suite.
      Any small project works; the first session can scaffold one if you ask (e.g. a tiny Node or Python library with ~20 tests).

## 2. Claude token

- [ ] On your machine: `claude setup-token` (needs your Claude subscription login). Copy the token once; don't paste it into any chat.
- [ ] Add it as a repository secret on `ai-workflows-playground`:
      Settings → Secrets and variables → Actions → New repository secret → name `CLAUDE_CODE_OAUTH_TOKEN`.
      (On every target repo later, the same.)

## 3. Second GitHub account

- [ ] Create or reuse a second account (free). It plays the outside reporter / fork contributor in tests.
- [ ] Do **not** give it write access to the playground.

## 4. Let target repos call the workflows

- Public `ai-workflows`: nothing to do.
- Private `ai-workflows`: Settings → Actions → General → Access → allow access from repositories owned by you. Callers must also be private/internal and owned by you.

## 5. Branch protection on the playground (needed from WP3)

- [ ] Protect `main`: require a pull request, require 1 approval, dismiss stale approvals. This is what makes the AI's "Request changes" block a merge.

## 6. Chat alerts (needed from WP11)

- Slack: create an Incoming Webhook for a channel → secret `SLACK_WEBHOOK_URL`.
- Telegram: create a bot with @BotFather, get your chat ID → secrets `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

## 7. Local tools

- [ ] Claude Code installed and logged in; `gh` installed and `gh auth login` done with your main account.
- [ ] Open Claude Code in the `ai-workflows` clone and paste the prompt from `KICKOFF.md`.
