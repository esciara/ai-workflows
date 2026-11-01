# ADR-0037 · Command-running agents: Claude Code sandbox, env scrub and a trusted-author gate

- Status: Accepted
- Date: 2026-11-01
- Deciders: maintainer
- Alias: `D37`

## Context

The reproducer (B2, WP6) and the implementer (B5, WP9) must run target-repo commands on GitHub-hosted runners: `setup` (e.g. `npm ci`), the test suite, repro scripts. Every agent job runs `anthropics/claude-code-action/base-action`, which needs `CLAUDE_CODE_OAUTH_TOKEN` (the maintainer's Claude subscription). Known issue `aiwf-3nh` (`docs/known-issues.md`) records that this breaks the hard rule "agents that read untrusted text get no secrets" and the spec's "no secrets" for both roles (B2 and the roles table), and required an ADR before WP6.

How the token reaches the agent's commands (base-action at the pinned SHA `6d5ae526`, v1.0.265):

- The composite step puts the secret in the environment of the bun process ([base-action/action.yml L202](https://github.com/anthropics/claude-code-action/blob/6d5ae526d25ce88daa2200be073e1a373167f064/base-action/action.yml#L202)); the SDK options copy the whole `process.env` into the Claude process ([parse-sdk-options.ts L279-L294](https://github.com/anthropics/claude-code-action/blob/6d5ae526d25ce88daa2200be073e1a373167f064/base-action/src/parse-sdk-options.ts#L279-L294)).
- Claude Code passes its environment to Bash children by default ([Sandboxing](https://code.claude.com/docs/en/sandboxing)), so `env` or `cat /proc/<pid>/environ` (same Linux user) reveals the token. The Read tool runs inside the Claude process and can open `/proc/self/environ`.
- base-action loads `user`, `project` and `local` settings unless `--setting-sources` is given ([parse-sdk-options.ts L338-L344](https://github.com/anthropics/claude-code-action/blob/6d5ae526d25ce88daa2200be073e1a373167f064/base-action/src/parse-sdk-options.ts#L338-L344)), so a target repo's `.claude/settings.json` could add hooks, which run outside any sandbox.
- Repo code run unsandboxed earlier in the job (e.g. a `postinstall` script) can leave a background process that reads the token once the Claude step starts. The runner user has passwordless `sudo`.

Threat model:

- Attacker: anyone who can open an issue or comment (B2 reads the report), and repo content the agent runs. Injected text leads the agent to run a command (e.g. "to reproduce, run `curl … | sh`") that sends the token out, or to put the token in its JSON output, which the orchestrator posts publicly.
- Impact: a `claude setup-token` OAuth token "can only make model requests" ([Authentication](https://code.claude.com/docs/en/authentication#generate-a-long-lived-token)). The attacker can use or burn the subscription's usage limits (shared with the maintainer's own work) for up to the token's lifetime (one year) or until it is revoked, with an account-flag and ToS exposure. No GitHub write: `GITHUB_TOKEN` never reaches agent steps (ADR-0039), and agents hold no App key (ADR-0031). No access to the maintainer's Mac. Annoying, not catastrophic.
- Scope: GitHub runners only, the two agents that run target-repo commands. Not local use on the maintainer's Mac.
- Secondary: exfiltration of private target-repo code over the network, which the spec's egress allowlist (SEC-06) targets.

Upstream facts relied on:

- `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` strips credentials from the environment of Bash commands, hooks and stdio MCP servers while the Claude Code process keeps them for its own API calls; on Linux it runs Bash in an isolated PID namespace so commands can't read host process environments through `/proc`. It is best effort (matches by name and value shape) and leaves `GITHUB_TOKEN`/`GH_TOKEN` in place ([env-vars](https://code.claude.com/docs/en/env-vars#what-the-subprocess-environment-scrub-removes)). With it set, every command runs sandboxed.
- The sandbox needs `bubblewrap` and `socat`; Ubuntu 24.04 AppArmor blocks bubblewrap's user namespaces unless relaxed. Egress goes through a proxy that allows only `sandbox.network.allowedDomains`. `failIfUnavailable: true` stops a silent fallback to unsandboxed commands; `allowUnsandboxedCommands: false` disables the `dangerouslyDisableSandbox` retry. The sandbox covers shell commands only, not Read, Edit, Write, WebFetch, hooks or MCP servers ([Sandboxing](https://code.claude.com/docs/en/sandboxing)).
- The main claude-code-action already turns the scrub on and installs `bubblewrap socat` for untrusted users ([action.yml](https://github.com/anthropics/claude-code-action/blob/main/action.yml), PRs [#1093](https://github.com/anthropics/claude-code-action/pull/1093), [#1132](https://github.com/anthropics/claude-code-action/pull/1132), [#1148](https://github.com/anthropics/claude-code-action/pull/1148)); its security doc says this "reduces but does not eliminate prompt injection risk" ([docs/security.md](https://github.com/anthropics/claude-code-action/blob/main/docs/security.md)). base-action does none of this setup but passes the job environment through.

## Options considered

- (A) Claude Code's built-in sandbox plus env scrub, plus a trusted-author gate and a recorded upgrade trigger to B. Same job as today; the agent keeps a fast edit-run loop. Pros: least code (workflow YAML and a settings JSON), about 1 to 2 days; vendor-maintained and documented for this case; egress allowlist built in (meets SEC-06); the gate removes the main attacker (strangers' issue text) from the path, which matches the actual exposure (the maintainer's own repos, issues mostly from collaborators). Cons: the boundary is bubblewrap under the same Linux user, set up by us; the scrub is a heuristic; correctness rests on several settings together, which a Claude Code upgrade can silently change; the Claude process itself still holds the token (an injected "print your env" via a non-sandboxed tool would reach it, hence the tool list below); relaxes a hard rule; needs an AppArmor tweak on the runner.
- (B) Credential proxy plus container, microVM as an opt-in upgrade (research survey 2026-10-31). A small proxy holds the real token; Claude Code gets a placeholder `CLAUDE_CODE_OAUTH_TOKEN` and `ANTHROPIC_BASE_URL`; the whole Claude process runs in a secret-free container on an internal Docker network whose only exits are the API proxy and an allowlisting forward proxy; gVisor as a cheap extra layer, Firecracker/Cloud Hypervisor or Docker Sandboxes later behind a `/dev/kvm` probe (nested virtualization on hosted runners is "not officially supported"). Prior art: GitHub's `gh-aw-firewall`. Pros: the only option that keeps the token out of the agent process too (meets SEC-05 "credentials at proxy" literally); strong standard boundary; keeps normal tools inside the container. Cons: about a week of work before WP6 (4 to 6 days plus a 1-day spike); the placeholder swap for subscription OAuth is undocumented; Anthropic's terms forbid intermediating Claude.ai credentials for others, so even a self-run proxy needs a ToS check; base-action no longer runs on the host, which touches the agent-job ADRs.
- (C) Split jobs: the agent job (token, no Bash, no file tools) returns files to write and commands to run as JSON; a separate job with no secrets on another VM applies them and returns the output as an artifact; repeat up to N rounds. Pros: strongest isolation for the token (never on the VM running untrusted code); only primitives already in the repo. Cons: Actions has no loops (unrolled chain or re-dispatch needing `actions: write`); each round trip costs a job start and a fresh `setup` (1 to 3 minutes); iterative reproduce/fix loops get much slower and lose agent state; most workflow code, about 1 to 2 weeks.
- (D) Accept the risk: scrub only, no sandbox setup, rotate the token after any suspicious run. Pros: no work; fastest agent. Cons: without bubblewrap there is no PID-namespace isolation, so `/proc/<pid>/environ` and `sudo` stay open; no egress allowlist; no gate, so any stranger's issue is one injected instruction away; detection is unlikely.

B was not chosen now because its cost (about a week before WP6, an undocumented auth path and an open ToS question) is out of proportion with the impact (subscription misuse, no GitHub write) while the repos are the maintainer's own and issue authors are mostly trusted; it stays the planned upgrade. C was rejected because its latency and lost agent state hurt the edit-run loop B2 and B5 depend on. D was rejected because it leaves the token one injected instruction away from any stranger, with no boundary and no egress control.

## Decision

Option A. For the reproducer (B2) and the implementer (B5) only:

- Env scrub: the agent job sets `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB: "1"` so Bash commands, hooks and MCP servers never see `CLAUDE_CODE_OAUTH_TOKEN`.
- Sandbox: a step before base-action installs `bubblewrap` and `socat` and relaxes the AppArmor userns restriction, failing the job if either fails. Settings passed through base-action's `settings` input: `sandbox.enabled: true`, `failIfUnavailable: true`, `allowUnsandboxedCommands: false`, `network.allowedDomains` limited to the package registries the target repo needs (from config), `filesystem.denyRead` on the runner's own directories.
- Tool and settings lockdown: `--setting-sources user` (no target-repo settings or hooks); tools `Bash` and `StructuredOutput` only (no Read, Edit, Write or WebFetch, which run outside the sandbox in the Claude process); files are read and edited through sandboxed shell commands. No repo code runs outside the agent in that job: `setup` runs as a sandboxed Bash call.
- Gate: a command-running agent starts only when the issue author is trusted, with the same check as command authors (ADR-0005: in `maintainers` and write or admin permission), or after an explicit command from such a user. The implementer already runs only after `/fix` (spec B4), so it is gated as specified. For the reproducer on an outsider's issue, the spec's flow conflicts (see Open points).
- Hard-rule exception: this relaxes "agents that read untrusted text get no secrets" (CLAUDE.md, spec roles table) for the model token only, for these two agents, under all the conditions above. `GITHUB_TOKEN`, App keys and every other secret stay out of agent steps; all other hard rules are unchanged.
- Upgrade trigger to B: write a new ADR adopting B (credential proxy plus container, microVM opt-in, after a playground spike and an Anthropic ToS check) when any of these happens: a target repo using Workflow B goes public or accepts issues from outside contributors without the gate; any sign of token misuse (unexplained usage, an alert from Anthropic, the token seen in a log, output or artifact); a sandbox or scrub bypass for Claude Code becomes publicly known; or a Claude Code upgrade removes or weakens one of the settings above.

Why: the impact of a stolen token is bounded (model requests on the subscription, no GitHub write), and the gate keeps strangers' text away from the two agents that run code, so the built-in sandbox plus scrub reduces the residual risk to a proportionate level at a fraction of B's cost. The upgrade trigger records when that judgement stops holding.

## Consequences

- WP6 builds the shared sandbox setup (install step, settings JSON, job env, tool list); WP9 reuses it.
- The egress allowlist needs a config source for registry domains; WP6 adds the key and an amendment to ADR-0010's config list.
- Tests that need hosts outside the allowlist fail in the sandbox; the reproducer reports "not reproduced: needs network" for the maintainer.
- Policy tests (`tests/test_workflow_policy.py`) gain rules for jobs that run project commands: the scrub env set, the sandbox install step present, settings with `failIfUnavailable: true` and `allowUnsandboxedCommands: false`, `--setting-sources user`, and a tool list of only `Bash` and `StructuredOutput`.
- `docs/known-issues.md` entry `aiwf-3nh` becomes an accepted risk with these mitigations and the upgrade trigger; bead `aiwf-3nh` can close, unblocking WP6.
- If the sandbox can't be made to start on hosted runners (`failIfUnavailable` fails), WP6 stops and a new ADR picks B or C; there is no unsandboxed fallback.
- The maintainer should know how to revoke and replace the token (`claude setup-token`, update the secret) as the response to any trigger.

Verification (WP6 and WP9 acceptance tests and unit tests):

- Scrub: a playground run, started by a maintainer-authored seeded issue that asks for `env` and `cat /proc/*/environ`, finishes with no occurrence of the token: a post-agent step in the job compares the agent's JSON output and Bash transcript against the token value and fails if it appears (it never prints it), and the e2e test asserts that step passed.
- Sandbox: the same run asks for `curl` to a host outside the allowlist and for `sudo id`; the e2e test asserts both failed (from the stored repro output). A unit or policy test asserts the job fails rather than running unsandboxed when the sandbox can't start.
- Gate: an issue opened by the tester App (an outsider) gets no reproducer run (no command-running job in the run), and the same check holds for the implementer without `/fix`; a maintainer-authored issue does start the reproducer.
- Lockdown: policy tests on the workflow YAML for the settings and tool list above.

Open points:

- Reproducer on outsiders' issues: the spec runs B2 automatically after B1 for every bug and says "a reply from the reporter restarts B2"; its command list (`/review`, `/retriage`, `/fix`, `/no-fix`) has no command that starts B2. The gate means an outsider's bug waits for a maintainer action, and a non-trusted reporter's reply cannot restart B2 on its own. Which command starts or restarts B2 (a new command, or reusing `/retriage`) and how this reads in the spec and in WP6's "Done when" ("the reporter's reply reruns it") are for the maintainer to decide before WP6. **Resolved (maintainer, 2026-11-01; WP6):** a new maintainer-only command `/reproduce` starts or restarts B2. On an outsider's bug, B1 stops with `triage: needs-human` and a note until a maintainer posts `/reproduce`; after that, a reply from the reporter while the issue has `triage: needs-info` (set only by B2) reruns B2. A trusted author's bug goes to B2 automatically. Spec (Commands line, B2) and WP6's Done-when ("after `/reproduce`, the reporter's reply reruns it") updated.
- To verify on the playground in WP6: whether `sudo` works inside bubblewrap (no-new-privs should block it); whether runner files outside `/proc` hold secrets readable by the runner user.
