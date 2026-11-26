# ADR-0065 · Agent sessions run as their own macOS user, GitHub tokens come from a broker

- Status: Accepted (direction, maintainer, 2026-11-26); design details are refined per migration step, each in its own PR
- Date: 2026-11-26
- Deciders: maintainer
- Alias: `D65`
- Amends: [ADR-0031](0031-agents-act-as-their-own-github-app-main-protected-by-a-ruleset.md) (where App keys live, how agents get tokens, the maintainer's credentials in agent reach), [ADR-0064](0064-mac-factory-runner-own-github-app-and-secrets-at-rest.md) (factory deploys from a `v*` tag, own model token, decision 3 enforced in code and `doctor`), [ADR-0060](0060-release-tag-as-the-only-human-gate.md) (point 1: release-review paths gain the broker; pre-release `v*-rc*` tags with a narrower review, for factory tests)
- Relates to: [ADR-0063](0063-no-claude-code-cloud-sessions-for-agent-roles.md) (this is the repo-access rethink it leaves pending)

## Context

A read-only security review of the Mac's credential model (2026-11-26) found that every Claude Code session, in every repo, runs as the maintainer's macOS user and can silently read the maintainer's admin GitHub token:

- `gh` is logged in as the maintainer with an OAuth token (`gho_`, no expiry, scopes `repo`, `workflow`, `gist`, `read:org`) stored in the login Keychain; git has a second copy as an internet password for `github.com`.
- The `v*` tag ruleset (ADR-0060 Transition step 1) has one bypass actor, the repository admin role, and the API answers `current_user_can_bypass: always` for that login. So any session holding the token can create or move a release tag and skip the one human gate of ADR-0060, edit rulesets, or push as the maintainer to any of the maintainer's repos.
- `scripts/dev/guard-bash` is a text filter configured in this repo only: one line of Python, `security find-generic-password … -w`, or the Read tool on `~/.config/gh` gets around it, and sessions in other repos have no filter at all. ADR-0031 already says the hook is not a hard boundary.
- The agent and tester App private keys sit in the maintainer's login Keychain, which never locks, and `as-agent` reads them without a prompt; any process of the same user can copy them once and mint tokens from anywhere until the keys are rotated.

The same review raised factory points (ADR-0064): the runner runs `main` HEAD, which is unreviewed between tags (ADR-0060 Consequences), on the host next to its App key and model token; "tool-less agents, Anthropic-only egress" (ADR-0064 decision 3) is not enforced in code yet; and the factory likely shares the model token used by GitHub Actions and the maintainer.

ADR-0031 and ADR-0063 named the residual "maintainer's token on the same machine"; ADR-0063 left the fix to this rethink.

## Options considered

- Status quo plus guard-bash at user level for every repo: cheap; but still a text filter, not a boundary (kept only as a stopgap guardrail).
- Claude Code's Bash sandbox per session, same macOS user: blocks some reads from Bash; but not the other tools or MCP, and the session can change its own settings, so not a boundary.
- Fine-grained token for the maintainer, nothing else: removes the admin bypass from agent reach; but App keys stay readable and any session still reads the remaining token.
- Own macOS user for agent sessions, App keys copied into that user: real boundary for the maintainer's files; but a session holds a raw key and mints any permission on any installed repo at any time.
- Own macOS user plus a broker that holds the keys and mints narrowed 1-hour tokens (chosen): the session never sees a key or an admin token; but a new process to build and run.
- One sbx VM per dev session: strongest isolation; but interactive sessions, worktrees, Beads and the e2e harness do not fit a fresh VM today (possible later upgrade).
- Claude Code cloud sessions: they can act on GitHub only as the maintainer, never as the agent App (facts in ADR-0063).
- Second GitHub bot account with a PAT: rejected by ADR-0031 (long-lived token, second account).
- Remove the admin role from the tag ruleset bypass list: an empty list blocks the maintainer too, and any token with admin reach could put it back.

## Decision

Direction decided by the maintainer on 2026-11-26. Each point below is the target; names, paths and interfaces are refined in the PR of the migration step that builds it.

1. **Agent sessions run as their own non-admin macOS user.** The development roles (`aiwf-orch`, `aiwf-review`, `aiwf-issues`, `aiwf-checkpoint` and their subagents) run Claude Code as a dedicated non-admin user (working name `aiwf-agent`), with its own clone, worktrees, `.venv`, Beads store and Claude Code login. The maintainer's home (0700), `gh` login and login Keychain are not readable from it. The agent user has no `gh` login, no git credential and no SSH key of its own; its reads (bare `gh` in sessions, the e2e harness in `tests/e2e/`) go through a broker `read` profile (for example `GH_TOKEN` set by a read wrapper), wired in migration step 4.
2. **A broker mints narrowed 1-hour App installation tokens.** A small host process (working name `aiwf-broker`), running as its own non-admin macOS user from a checkout at a maintainer-created release `v*` tag (not an rc tag, never `main`, never a checkout the agent user can write; it refuses to start otherwise, like the factory in point 5), holds the private keys of the agent and tester Apps (moved out of the maintainer's login Keychain, new keys generated for it). Agent sessions ask it over a local socket for a token by profile (for example `push`, `pr`, `comment`, `resolve`, `read`) and repository; the broker checks the caller's uid and a static allow-list shipped in that tagged checkout (so agents cannot widen it without a maintainer tag), mints an installation token restricted to that one repository and the profile's permissions, never more than the App has, and logs the request without the token. `scripts/dev/as-agent` and `as-tester` become broker clients; the Keychain read is removed. Tokens expire after one hour and are revoked when the wrapped command ends where practical. Limit: every role and subagent shares the agent uid, so the broker cannot tell roles apart; a compromised session can still ask for any allow-listed profile on any allow-listed repo. Profiles bound mistakes and token lifetime and keep keys out of sessions; they do not separate roles from each other (one uid per role is a later upgrade). The factory keeps its own key and SOPS store under ADR-0064; folding it into the broker is a later choice.
3. **No admin GitHub token in agent reach.** The maintainer's `gh` OAuth login is replaced by two separate fine-grained tokens, both with an expiry date and no contents or administration write on this repo, so neither carries the tag bypass: the maintainer's own CLI token (read on the maintainer's repos), which stays in the maintainer's user and is never given to the broker; and an `as-maintainer` token limited to `esciara/ai-workflows-playground` (issues and pull requests write, metadata read), held by the broker and handed only to `scripts/dev/as-maintainer`. The `as-maintainer` token is long-lived and cannot be narrowed per request; that residual is accepted because it reaches the playground only. The `github.com` internet password used by git is removed, and the maintainer's SSH key gets a passphrase that is not cached (no `UseKeychain`, no `AddKeysToAgent`), or is removed from the GitHub account; a cached key would let any process of the maintainer's user push a `v*` tag as admin through the agent socket.
4. **Release tags are created by the maintainer in the browser.** Admin acts (tags, rulesets, settings, secrets) happen in the GitHub web UI under the maintainer's own login, never from a CLI token on the Mac. No Claude Code session drives a browser profile logged in to GitHub as the maintainer (for example through a browser-automation extension). Agents never create, move or delete tags (unchanged, ADR-0060 point 4).
5. **Factory hardening (amends ADR-0064).**
   - The factory uses its own model token (`claude setup-token` run for the factory only), separate from the maintainer's own use and from the GitHub Actions secret, so it can be revoked alone and misuse is attributable.
   - The factory runs only a maintainer-created `v*` tag, never `main`: `~factory/factory/src` is checked out at a tag, and `aiwf-factory doctor` and the runner refuse to start when HEAD is not exactly a `v*` tag. Unreleased factory code (the M1 real checks and the local factory e2e) runs from a maintainer-created pre-release tag (for example `v0.4.0-rc1`) on a commit of `main`, so each factory test iteration costs the maintainer one tag. This amends ADR-0060 point 1 for pre-release tags only: before an rc tag the maintainer reviews the diff since the last tag of the factory and broker paths (`scripts/aiwf/factory/`, `templates/factory/`, the broker paths) and of `scripts/dev/`, not the full release-candidate report; rc tags are never pinned by target repos. The report format is refined in M1.1.
   - ADR-0064 decision 3 is enforced in code and checked by `doctor`: an explicit tool allow-list (`StructuredOutput` only), `--strict-mcp-config` and `--setting-sources user` in the agent argv, and no host mount in the `sbx` call, pinned by unit tests; the sbx egress policy denies everything except `api.anthropic.com`, and `doctor` fails on any other allowed domain; the per-step token mint body is unit-tested; the publish step refuses a review event `APPROVE`.
6. **Release-review paths (amends ADR-0060 point 1).** The broker code and its allow-list join the list (working path `scripts/aiwf/broker/`), as they hold a security boundary.

Why: a macOS user boundary is enforced by the OS, not by instructions or text filters; a broker keeps keys out of every session, runs only reviewed code, and gives short-lived tokens limited to one repo and one profile; removing every admin token from agent reach restores the tag as a human-only gate; the factory changes close the gap between what ADR-0064 promises and what runs.

## Migration order

Each step is its own PR or maintainer action; the old path keeps working until step 6 proves the new one.

1. Stopgaps, no ADR needed: factory-only model token (maintainer); `chmod 700` on `~factory` and `Umask 077` in the LaunchDaemon plist; the user-level guard hook for every repo, with blocks for `security find-*-password -w|-g`, `~/.config/gh` and `~/.ssh` (maintainer go, outside the repo).
2. Factory enforcement (point 5): tool allow-list, egress check in `doctor`, refused `APPROVE`; before M1.3a reads real PR text. Then deploy the factory from a `v*` tag and make `doctor` refuse anything else.
3. Broker: code, unit tests (uid check, allow-list, request body per profile, no token in logs, refusal of a non-tag checkout), its macOS user and LaunchDaemon, deployed from a maintainer `v*` tag, new agent and tester App keys loaded into it; `as-agent` and `as-tester` use it, with the Keychain path still present as fallback.
4. Agent macOS user: account, clone, worktrees, `.venv`, Beads, Claude Code login, the `read` profile for bare `gh` and the e2e harness; one role at a time moves to it.
5. Fine-grained token for the maintainer (point 3) and `as-maintainer` through the broker; tags and admin acts in the browser from now on.
6. End-to-end proof from the agent user: a WP PR opened, reviewed, threads resolved and merged on green; the e2e suite green on `main`; a release-candidate report posted; the maintainer tags in the browser.
7. Irreversible, last and only after step 6 is green: revoke the old `gh` OAuth token; delete the old agent and tester App private keys on GitHub; delete their Keychain items and the git internet password; remove the Keychain fallback from `as-agent` and `as-tester`.

## Consequences

- The broker is a new single point of failure: while it is down, agent sessions cannot write to GitHub (the factory is unaffected, it keeps its own key). Mitigation: LaunchDaemon with `KeepAlive`, a broker check in the dev tooling, and the maintainer can always act in the browser. After step 7 there is no fallback to the Keychain keys, by design.
- The broker is a high-value target: a bug in its allow-list or uid check hands out tokens. It stays small, is unit-tested, runs only a maintainer tag, and its code is in the release-review diff (point 6). A broker fix needs a maintainer tag to take effect.
- Migration cost: a second and third macOS user to set up, a fresh clone and toolchain for the agent user, every role session restarted from the new user, and `CLAUDE.md` paths and identity lines to update once the new path works. Until step 7, both paths exist and the old risk remains.
- The revoke of the old token and keys is irreversible and comes last, only after the new path works end to end (step 6); revoking earlier would stop all agent work with no way back but new setup.
- Bare `gh` and the e2e harness stop working for the agent user until the `read` profile is wired (step 4); the old path stays until then.
- The maintainer loses admin acts from the CLI on the Mac (tags, rulesets, settings in the browser). Sessions that still run as the maintainer's user (other repos) no longer reach an admin token, but keep residual admin reach through the logged-in browser and any cached SSH key; points 3 and 4 close these by rule, not by an OS boundary, so only sessions under the agent user are bounded by the OS.
- The agent sessions' Claude Code login is a further model token on the Mac; whether it shares the maintainer's subscription token or gets its own is decided in step 4.
- `docs/known-issues.md` entries and the spec or `CLAUDE.md` wording that mention the Keychain, `as-agent`'s key source or the maintainer's `gh` login are updated by the PR of the step that changes them, not here.
