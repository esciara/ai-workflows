# ADR-0067 · Empty-password login keychain for `factory`, unlocked at start, so sbx works unattended

- Status: Accepted (2026-11-27, maintainer, option A); the Lima fallback is an Open question
- Date: 2026-11-27
- Deciders: maintainer
- Alias: `D67`
- Amends: [ADR-0064](0064-mac-factory-runner-own-github-app-and-secrets-at-rest.md) (decisions 5 and 6: unattended start)

## Context

On the factory Mac, `sbx create` (Docker Sandboxes) fails when nobody is logged in as `factory`: sbx stores its Docker sign-in in `factory`'s login keychain, the keychain is locked, and sbx reports "SBX could not read Docker credentials because macOS Keychain denied access". Unlocking the keychain by hand fixes it, but the factory must start after a reboot with no GUI session. The cause is from the maintainer's observation; no upstream Docker issue has been verified, so none is cited.

## Options considered

- A, empty-password login keychain with no auto-lock, unlocked by the factory program at start with an empty password: no password stored anywhere, one small function; the keychain protects nothing by password, so it must hold nothing valuable.
- Keychain password stored in the SOPS file: works, but the SOPS key file is the same trust root as an empty password (anyone who is `factory` gets it) and it adds a moving part.
- A dedicated second keychain as the default: untested with sbx (it reads the default login keychain), no real gain over A.
- Lima VM with gVisor and Podman instead of sbx: avoids the keychain and Docker sign-in, but a new sandbox stack to build and secure. Kept as the fallback if the M1.1 spike fails.
- Hosted sandboxes: the model token and the repo leave the Mac.
- Apple `container`, Tart, or Anthropic's sandbox-runtime: weaker isolation or unclear fit with the ADR-0037 sandbox, scrub and gate.

## Decision

Decision A. `factory`'s login keychain gets an empty password and never auto-locks. The factory program (`python -m aiwf.factory run`, the spike and `doctor`) runs `security unlock-keychain -p ""` on that keychain at start, before any sbx call; it is skipped off macOS or when the file is missing. The keychain holds only a read-only Docker access token for sbx. Secrets stay in SOPS + age; the old `aiwf-claude-oauth` keychain item is deleted after M1. `doctor` has a `keychain` check. Setup and revert are in `docs/factory-m1.md` (step 6b).

Why: the keychain only has to hand sbx a Docker sign-in; making that need no password removes the unattended-start blocker with no stored password and the least new code.

## Consequences

- Exposure: a session as `factory` can read the keychain, which holds only a read-only Docker token (worth little). No Claude or GitHub secret is in it.
- Reverting means setting a real password again with `security set-keychain-password`; the unlock then fails and `doctor` reports `FAIL keychain`.
- Open question: if the M1.1 spike still fails with this, the Lima VM + gVisor + Podman backend is the fallback and comes back as an ask (a new ADR).
