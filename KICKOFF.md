# Kickoff prompt

Open Claude Code in the root of this repo (after finishing `SETUP.md`) and paste everything between the lines.

---

You are going to build the `ai-workflows` repo described in this folder.

1. Read `CLAUDE.md`, then `docs/spec.md`, `docs/plan.md` and `docs/progress.md` in full.
2. Check the environment and report what you find:
   - `gh auth status` and that you can see `esciara/ai-workflows`, `esciara/ai-workflows-playground` and its fork `opinionated-digital-center/ai-workflows-playground`;
   - that the playground has the secret `CLAUDE_CODE_OAUTH_TOKEN` (`gh secret list -R esciara/ai-workflows-playground`; names only);
   - that the tester GitHub App `ai-workflows-tester` is installed on `esciara/ai-workflows-playground` (ask me for the App ID; the private key is in the macOS Keychain entry `ai-workflows-tester`, or at the path in `AI_WORKFLOWS_TESTER_KEY_PATH` if I chose the file option; check the key exists without printing it);
   - that `esciara/ai-workflows` is public, so the public playground can call its workflows (`gh repo view esciara/ai-workflows --json visibility`).
3. Give me, in under 40 lines:
   - your understanding of the goal in 3 sentences;
   - anything in the spec or plan that is ambiguous, contradictory or missing for WP0–WP2, each with your recommended answer;
   - your proposal for WP0: stack choice for scripts, file tree, config schema outline, how the caller template works, and how you will run the WP0 "Done when" check.
4. Stop and wait for my "go". After that, follow the per-WP loop in `CLAUDE.md`: one work package per branch and PR, the check's evidence in the PR description, `docs/progress.md` updated, then stop for review before the next package.

Placeholders: my GitHub handle is `esciara`; my maintainer handle for configs is `esciara`; notification channel is `<slack|telegram>`.

---

Replace `<slack|telegram>` before pasting.
