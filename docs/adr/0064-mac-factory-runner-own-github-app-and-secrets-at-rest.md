# ADR-0064 · The Mac runs real workflows: local factory runner, its own GitHub App, secrets at rest

- Status: Accepted
- Date: 2026-11-26
- Deciders: maintainer (decided 2026-11-26, answers 1A 2F 3A 4A 5A 6A on the M1 decision page)
- Alias: `D64`
- Amends: [ADR-0037](0037-command-running-agents-sandbox-scrub-and-trusted-gate.md) (scope "not local use on the maintainer's Mac"), [ADR-0060](0060-release-tag-as-the-only-human-gate.md) (point 1: release-review paths)
- Amended by: [ADR-0065](0065-agent-sessions-as-their-own-macos-user-with-a-token-broker.md) (factory runs only a `v*` tag, own model token, decision 3 enforced in code and `doctor`)
- Relates to: [ADR-0063](0063-no-claude-code-cloud-sessions-for-agent-roles.md) (decides the isolation of the factory runner only, not of the dev agent roles)

## Context

Factory M0 (`scripts/aiwf/factory/m0.py`, `docs/factory-m0.md`) shows that the Mac can run Claude in Docker `sbx` sandboxes through a durable DBOS queue, as the non-admin macOS user `factory`. The subscription OAuth token is read from factory's login Keychain and handed to `sbx exec -e`, so it is inside the VM (accepted for M0); the sbx secret proxy does not work for subscription tokens (401). Verified by the maintainer: no `aiwf-*` sandbox left after a run, no token in `dbos.sqlite`, `kill -9` resumes without duplicates, ssh works, but only after a manual `security unlock-keychain`.

M1 makes the Mac run a real workflow: Workflow A's shape (start, context, 4 review passes, verify, publish) on PRs of the playground repo, with queue concurrency and a reaper. Three things in force do not allow it:

- The architecture page says the Mac is for development only; product workflows run on GitHub Actions (spec, Runtime).
- Hard rule (spec, CLAUDE.md): only the orchestrator writes to GitHub, using the workflow's `GITHUB_TOKEN` with per-job minimal `permissions:`. A process on the Mac has no `GITHUB_TOKEN`, so it needs another identity.
- ADR-0037's threat model covers GitHub runners only and says "not local use on the maintainer's Mac"; the token-in-the-VM risk of M0 is not recorded in an ADR.

Also blocking unattended runs: factory's login keychain is locked in ssh and launchd sessions, so the runner cannot read the token without a manual unlock after each boot or lock.

Out of scope, postponed: a token vendor or broker, credential lanes per role, a shared Beads store, Workflow B on the Mac, fork PRs, the isolation of the dev agent roles (ADR-0063's pending rethink), and any repo other than the playground.

Threat model for the local runner:

- Attacker: whoever writes PR text, diffs or commit content on the reviewed repo (on the playground: the maintainer, the agent App, the tester App; later, anyone who can open a PR).
- Assets: the subscription token (model requests only, ADR-0037), the factory App's private key (GitHub writes on the repos it is installed on), the maintainer's macOS account and files, the dev agent App key and the maintainer's `gh` token on the same Mac.
- Boundaries: the sbx microVM (no host mount, egress policy), the macOS user split (`factory` is non-admin and cannot read the maintainer's home), and the App's installation scope and permissions.

## Options considered

Where the real workflow runs:

- Stay on GitHub Actions only: no new boundary; but the Mac's sandboxes and durable queue stay unused and the factory roadmap stops at M0.
- Self-hosted Actions runner on the Mac: keeps `GITHUB_TOKEN` and the workflows; but it executes repo workflow code on the host (not in sbx), GitHub advises against it on repos taking outside PRs, and it skips the DBOS queue M0 built.
- Local factory runner, as user `factory`, DBOS queue, agents in sbx, its own GitHub App (chosen): reuses M0 and the `aiwf` modules; but a new identity, a secret at rest and an amended hard rule.

Local writer identity (decision 2):

- A. One new App `esciara-ai-workflows-factory`, tokens narrowed per step (chosen): same shape as per-job `permissions:`, one author login so the marker and review matching in `ghapi.py` keep working, installed on the playground only; but one key gives full App write on the playground if stolen from the host.
- B. Two Apps, reader and writer: a reader-key-only process cannot write; but no gain in M1, since the host process holds both keys, and twice the keys to keep.
- C. One App per role or step: separate audit names; but several writer logins break "find my own comment" (duplicates, reviews not dismissed), and many keys on one host give no real separation.
- Reuse the dev agent App: it has contents and workflows write on this repo, so a compromised factory could push here (ADR-0031 lanes).
- The maintainer's `gh` token: writes as an admin with tag-ruleset bypass; ADR-0063 rejected it for the same reason.

Secrets at rest (decision 5):

- F. SOPS + age: one encrypted YAML file, one age key file (chosen): open source (MPL-2.0, BSD-3), no server or daemon, nothing to unlock, safe in backups and copies, key can later move to a hardware key or the Secure Enclave; but against code running as `factory` or an admin it protects exactly as much as plain files, since they can read the key file.
- A. Plain 0600 files: simplest; but plaintext in backups and copies.
- B. Own keychain with empty password: keeps Keychain code; but an empty password adds nothing over file modes, its access list trusts `security` which any `factory` process can run, and sleep can lock it.
- C. Login keychain unlocked at boot with a stored password: the password then sits in a file (no better than A) or the System keychain (the daemon would need root).
- D. Auto-login of `factory`: macOS disables it with FileVault on, and an always-logged-in GUI user is a bigger surface.
- E. Unseal by the maintainer after each boot: nothing on disk; but nothing runs after a reboot until the maintainer acts, so not unattended (kept as an upgrade trigger).
- G. gopass: unattended unlock needs a stored passphrase or preset gpg-agent, fiddly under launchd, for the same protection as F.
- H. OpenBao: audit log and policies; but a second daemon, with its unseal key and login token in files again.
- I. Infisical self-hosted: UI and rotation; but needs Postgres and Redis, its machine credential is a file again.
- J. KeePassXC with a key file: heavier desktop tool for the same protection as F.
- Not open source, excluded: HashiCorp Vault (BSL), Bitwarden Secrets Manager, Doppler, 1Password.

Review agents reading PR text on the Mac (decision 3):

- A. Accept, tool-less agents, same limits as on GitHub (chosen): uses M0 as is; no tools means injected text cannot run a command or send the token elsewhere; but the token is inside the VM.
- B. Wait for a credential proxy that keeps the token out of the VM: an escape would not reveal it; but sbx's proxy fails with subscription tokens, our own is about a week of work with an open ToS question, and M1 stops until then.

PRs the factory reviews (no numbered decision):

- A. Head branch starts with `factory/` (chosen): known when the PR opens, so no race; one-line skip in the playground caller; easy to e2e; but moving a PR between reviewers needs a new branch.
- B. A label: switchable; but the label lands after `opened`, so Actions has often started and both review.
- C. A second playground repo: full separation; but a repo to create, seed and sync, with fixtures and slots copied.

Thread resolution (no numbered decision):

- A. Skip in M1, threads stay open (chosen): the App cannot push code; less to build; but fixed findings on `factory/*` PRs stay open until someone resolves them.
- B. Grant contents write on the playground: same behaviour as on GitHub; but a stolen key can push code there.

Runner start (decision 6):

- A. LaunchDaemon as `factory` (chosen): starts at boot with nobody logged in, restarts after a crash, not root; but the maintainer installs it once with `sudo`.
- B. LaunchAgent: no admin install; but it runs only while `factory` is logged in to the screen, which needs auto-login, which FileVault forbids.
- C. Start by hand over ssh: nothing to install; but it stops at reboot or crash, so not unattended.

## Decision

1. **The Mac runs real workflows, through the factory runner only.** A long-running DBOS process (`aiwf.factory`) as macOS user `factory` (non-admin, no access to the maintainer's home) runs Workflow A's shape on PRs of `esciara/ai-workflows-playground`, selected by head branch prefix `factory/`, not draft, same-repo only (fork PRs are skipped). It finds work by polling the GitHub API (no inbound webhook, no tunnel). "Mac = dev only" on the architecture page becomes "Mac = dev, plus the factory runner on repos listed in this ADR". Adding a repo needs a new ADR. The playground caller skips heads starting with `factory/`, so each PR has exactly one reviewer. A maintainer `/review` comment (an `issue_comment` event, no head ref) cannot be skipped by the caller `if:`; M1.5 must make `review.yml`'s gate skip `factory/*` heads after it resolves them, or document `/review` on those PRs as unsupported.
2. **Local writer identity (amends the hard rule).** On the factory runner, "only the orchestrator writes to GitHub, using the workflow's `GITHUB_TOKEN` with per-job minimal permissions" reads: only the factory's host orchestrator (the Python process outside any sandbox) writes to GitHub, using installation tokens of the App `esciara-ai-workflows-factory`, minted per step with the narrowed permissions of the matching `review.yml` job (context: contents read, pull requests read, issues read, checks read, actions read, as the `context` job of `review.yml`; start and publish: pull requests write, issues write, contents read; no step gets more), restricted to the one repository, never stored in DBOS records (step arguments or return values), logs or step arguments. The App has pull requests write, issues write, contents read, checks read, actions read, metadata read; no contents write, workflows, administration, checks write, statuses, secrets or actions write; it is installed on the playground only. Thread resolution (needs contents write, ADR-0062) is not done in M1. Everything else in the hard rules is unchanged. On GitHub Actions the rule is unchanged.
3. **Rule of Two under the local runner.** The host orchestrator holds the App key and the model token and reads no untrusted text as instructions: it moves PR data as bytes into prompts and reads agent output only after schema validation. Agents run only inside sbx VMs: no host mount, no GitHub credential of any kind, tools `StructuredOutput` only (no Bash, Read, Write, WebFetch, MCP), `--setting-sources user`, egress limited by the sbx policy to the Anthropic API. The model token inside the VM is the only exception, as in ADR-0037, and with no tools the agents cannot run commands to read it. The host never checks out PR code to run it; files read for context come through the API or a clone with hooks, filters and submodules off.
4. **Model token in the VM, accepted risk.** The subscription token is passed to each VM with `sbx exec -e` from the host process's memory, never in argv, DBOS records, step arguments or logs. Impact if stolen: model requests on the subscription until revoked (ADR-0037). Recorded in `docs/known-issues.md`. A new ADR is required before agents get tools on the Mac.
5. **Secrets at rest: SOPS + age.** The token (`claude_oauth`) and the App key (`factory_app_pem`) live in `~factory/.config/aiwf/secrets.enc.yaml`, encrypted by SOPS to the age key in `~factory/.config/aiwf/age.key` (dir 0700, key file 0600, owner `factory`). The runner refuses to start when owner or mode differ, decrypts each value once at startup with `sops decrypt --extract` (value read from stdout into memory, never in argv, logs or DBOS records), and keeps the env override only for tests. The Keychain read of M0 is removed. The disk is FileVault-encrypted; Time Machine excludes the key file.
6. **Unattended start.** A LaunchDaemon (installed by the maintainer, `UserName` `factory`, `KeepAlive`) starts the runner at boot without any login. A stop file (`~factory/factory/STOP`) and the `ai: off` label act as kill switches; `launchctl bootout` is the hard stop.
7. **Upgrade triggers.** Write a new ADR before any of: installing the factory App on a repo other than the playground, or on a repo that takes outside PRs; running agents with Bash or a workspace mount on the Mac (Workflow B shape); a second macOS user or person on the Mac with admin rights; any sign of token or App key misuse. The ADR then weighs unseal after boot, the age key in the Secure Enclave or a hardware key, a credential proxy, and a token vendor.

Why: the factory reuses M0's sandbox and queue and the existing Workflow A code; a separate App with per-step narrowed tokens keeps the "minimal permissions per job" property of `GITHUB_TOKEN` and bounds a leak to the playground; tool-less agents in a VM keep the Rule of Two; SOPS + age removes the only unattended blocker with a standard open-source store, without pretending to more protection than a key on disk gives.

## Consequences

- Amendment to the hard rule "only the orchestrator writes with `GITHUB_TOKEN`": on the factory runner the host orchestrator writes with factory App installation tokens (decision 2). The spec (agent table TL;DR, Orchestrator row, Runtime paragraph) and `CLAUDE.md` hard rules were updated with the wording of this amendment in later PRs.
- Accepted risk: the model token is inside every sbx VM during a run, and the token and App key are decryptable by anyone who can read the 0600 age key file (`factory` and admins). Against an agent that escapes its VM this protects no more than plain files; a key not on disk is the upgrade path (decision 7).
- A new App to create and its key to store (maintainer setup below); the dev agent App and the maintainer's `gh` token are never visible to `factory`.
- `scripts/aiwf/ghapi.py` takes the bot login from config (`AIWF_BOT_LOGIN`, default `github-actions[bot]`), since marker comments and dismissable reviews are found by author (ADR-0021); `publish_review.BOT_LOGIN` follows.
- The playground caller must skip PRs whose head branch starts with `factory/`, or Actions and the factory fight over the same marker comment and verdict label (playground PR, via `as-agent`).
- Release-review paths (ADR-0060 point 1) gain `scripts/aiwf/factory/` and the LaunchDaemon template, since they hold a security boundary; this ADR amends ADR-0060's list now, because `scripts/aiwf/factory/` (M0) is already on `main`.
- `docs/known-issues.md` gains two accepted risks (token inside the VM; secrets decryptable with the age key file) and one design issue (threads opened by the factory are not resolved in M1).
- e2e for the factory needs the Mac's daemon running; it is a local-only suite, skipped unless `AIWF_E2E_FACTORY=1`, not part of the GitHub-run e2e.
- Factory runs count against the same subscription limits as the maintainer's own Claude use; concurrency is capped by the queue (default 2).
- The work is planned as slices M1.0 to M1.5 in `docs/plan.md`.

### Maintainer setup

1. Create the App `esciara-ai-workflows-factory` ("Only on this account", webhook off), permissions: Pull requests read and write, Issues read and write, Contents read, Checks read, Actions read, Metadata read; nothing else.
2. Install it on `esciara/ai-workflows-playground` only.
3. As `factory`: `brew install sops age`, `mkdir -m 700 -p ~/.config/aiwf`, `(umask 077; age-keygen -o ~/.config/aiwf/age.key)`, then `sops edit ~/.config/aiwf/secrets.enc.yaml` to paste the token and the downloaded `.pem`, and delete the download.
4. Install the LaunchDaemon plist from `templates/factory/` into `/Library/LaunchDaemons/` (admin), then `sudo launchctl bootstrap system <plist>`.
5. Check: `ssh factory@localhost 'aiwf-factory doctor'` prints ok for files, sbx policy and the App token mint.
