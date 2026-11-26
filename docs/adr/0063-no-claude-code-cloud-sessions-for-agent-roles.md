# ADR-0063 · No Claude Code cloud sessions for the agent roles

- Status: Proposed
- Date: 2026-11-19
- Deciders: maintainer
- Alias: `D63`
- Amended by: ADR-0064

## Context

The repo's development agent roles (orchestrator, reviewer, issues and implementer, checkpoint, and any future scheduled role) run as Claude Code sessions on the maintainer's Mac and act on GitHub as the agent App through `scripts/dev/as-agent` ([ADR-0031](0031-agents-act-as-their-own-github-app-main-protected-by-a-ruleset.md)). Claude Code can also run sessions in Anthropic's cloud: Claude Code on the web, `claude --cloud`, and routines (scheduled tasks). The question was whether some or all roles should move there.

What the docs say, checked on 2026-11-19 ([Claude Code on the web](https://code.claude.com/docs/en/claude-code-on-the-web), [cloud environments](https://code.claude.com/docs/en/cloud-environments), [routines](https://code.claude.com/docs/en/routines)):

- GitHub access is either the Claude GitHub App or `/web-setup`, which uploads the user's own `gh` token. Commits, PRs and comments are attributed to the user's own GitHub account. There is no way to use a custom GitHub App identity.
- A GitHub proxy sits between the session and GitHub. It blocks branch deletes and pushes that are not branches (so tags), but does not restrict which branch is pushed; only rulesets do. GraphQL is blocked (403), even with the user's own `GH_TOKEN`, so `resolveReviewThread`, `gh pr` and `gh issue` fail.
- Environment variables are visible to the model and to anyone using the environment. "Network secrets" are injected by the proxy and never enter the VM, but cannot be used for GitHub.
- Egress per environment is None, Limited (allowlist plus custom domains) or Full; GitHub and the Anthropic API are always reachable.
- Each session is a fresh Ubuntu VM with a fresh clone.
- Usage draws on the same Claude subscription. Routines are a research preview, limited to 100 runs per hour per account and 30 per hour per routine.

Inferred, not checked: there is no safe way to hold the agent App's private key inside the VM, and the local Beads store (embedded Dolt in `.beads/`) and shared worktrees do not exist in a fresh VM.

## Options considered

- Cloud sessions acting as the maintainer, with rulesets as the only guard: no setup and no Mac needed; but every agent write becomes the maintainer's (the identity lanes `as-agent`, `as-maintainer` and `as-tester` of ADR-0031 collapse into one), and since the maintainer is repo admin, agents would sit on the admin bypass of the `v*` tag ruleset that holds the release gate ([ADR-0060](0060-release-tag-as-the-only-human-gate.md)).
- Cloud sessions with a minted agent App token in `GH_TOKEN`: keeps the App identity on paper; but the token is readable by the model and by environment users, the key that mints it has no safe home in the VM, and GraphQL is still blocked, so threads cannot be resolved.
- No cloud sessions for agent roles (chosen): GitHub Actions jobs stay the cloud path and local roles stay on the Mac; the cost is that roles need the Mac running and the local isolation work still has to be done.

The first was rejected because it removes the agent identity and widens the admin bypass of the human gate; the second because it exposes the token and still cannot do what the roles need.

## Decision

Decided by the maintainer on 2026-11-19: Claude Code cloud sessions (web, `claude --cloud`, routines and scheduled tasks) are not used to run any of the repo's agent roles. Workflows A and B on GitHub Actions remain the only cloud execution path. Local roles stay on the Mac and are isolated as the pending repo-access security rethink decides (options such as a separate macOS user, a Claude Code sandbox per role, a token vendor); that rethink is not decided here.

Why: a cloud session can only act as the maintainer on GitHub, never as the agent App, which breaks ADR-0031's identity lanes and the release gate of ADR-0060.

## Consequences

- No routine or cloud session is set up for any role, including future scheduled ones; a scheduled role runs on the Mac or as a GitHub Actions job.
- Revisit if Anthropic adds a custom GitHub App identity, secret injection usable for GitHub, or GraphQL access in cloud sessions.
- The facts above are from the docs as of 2026-11-19; the inferred points were not tested.
