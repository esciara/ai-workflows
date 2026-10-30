# Kickoff prompt

Open Claude Code in the root of this repo (after finishing `SETUP.md`) and paste everything between the lines.

---

You are going to build the `ai-workflows` repo described in this folder.

1. Read `CLAUDE.md`, then `docs/spec.md`, `docs/plan.md` and `docs/progress.md` in full.
2. Check the environment and report what you find:
   - `gh auth status` and that you can see `<OWNER>/ai-workflows` and `<OWNER>/ai-workflows-playground`;
   - that the playground has the secret `CLAUDE_CODE_OAUTH_TOKEN` (`gh secret list -R <OWNER>/ai-workflows-playground`; names only);
   - that this repo's Actions access setting lets other repos call its workflows (ask me to confirm if you can't read it).
3. Give me, in under 40 lines:
   - your understanding of the goal in 3 sentences;
   - anything in the spec or plan that is ambiguous, contradictory or missing for WP0–WP2, each with your recommended answer;
   - your proposal for WP0: stack choice for scripts, file tree, config schema outline, how the caller template works, and how you will run the WP0 "Done when" check.
4. Stop and wait for my "go". After that, follow the per-WP loop in `CLAUDE.md`: one work package per branch and PR, the check's evidence in the PR description, `docs/progress.md` updated, then stop for review before the next package.

Placeholders: my GitHub handle is `<OWNER>`; my maintainer handle for configs is `<OWNER>`; notification channel is `<slack|telegram>`.

---

Replace `<OWNER>` and `<slack|telegram>` before pasting.
