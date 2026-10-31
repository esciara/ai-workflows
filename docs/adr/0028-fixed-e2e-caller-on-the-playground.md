# ADR-0028 · Fixed e2e caller on the playground

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D28`
- Amends: ADR-0026, ADR-0004
- Amended by: ADR-0029

## Context

Swarm-plan decision D8. Issue- and comment-triggered e2e tests need the playground's caller to run the WP branch under test. The caller lives on the playground's default branch and its `uses:` refs are static (ADR-0002, ADR-0026), so each test would need a playground PR to flip the ref, and another to flip it back. Config switches such as turning on triage for WP5 need a playground PR too, since config is read from the default branch only (ADR-0004).

## Options considered

- Agents merge playground caller-flip PRs, pre-authorised by the maintainer: no new caller; needs merges and reverts for every test, and is not deterministic.
- Switch the playground default branch per test: no caller changes; needs admin rights, which agents do not get.
- A fixed e2e caller with three slots (pointers): three tests at once; a test can silently run another WP's code if it picks the wrong slot.
- A fixed e2e caller with one slot: one PR, nothing to merge or revert per test; tests run one at a time.

## Decision

- A one-time playground PR (merged by the maintainer) adds `caller-e2e.yml`. It always runs `esciara/ai-workflows/...@e2e-target`, and only for issues and PRs labelled `e2e-target`; the normal caller skips those.
- To test, an agent pushes its WP branch to the `e2e-target` branch of ai-workflows and opens its test issues with the label set at creation. There is nothing to revert; a stale pointer only affects labelled test issues.
- There is exactly one slot (one `e2e-target` pointer) for now, held under the ADR-0026 e2e slot, so no test silently runs another WP's code.
- Reusable workflows accept an alternative config file (e.g. `.github/ai-workflows.e2e.yml`), used only by the e2e caller, so config switches need no playground PR. It is implemented in the ADR-0025 seams PR, which decides its exact location and source. This is an exception to ADR-0004, limited to the e2e caller.

Why: one PR replaces a merge and a revert per test, and one slot keeps every run attributable to one WP.

## Consequences

- Issue/comment e2e tests stay serialised; the ADR-0026 slot also covers the `e2e-target` push.
- The normal playground caller ignores items labelled `e2e-target`.
- KNOWN DESIGN ISSUE (see [`docs/known-issues.md`](../known-issues.md)): the single slot is a stopgap. Root cause: `uses: owner/repo/.github/workflows/x.yml@ref` is static, so all e2e runs share one mutable global target and WP tests cannot be isolated. The maintainer called this unsatisfactory; it must be fixed sooner rather than later. Tracked by bead `aiwf-6k3` (P1).
- ACCEPTED RISK (see [`docs/known-issues.md`](../known-issues.md)): code on `e2e-target` is unreviewed (review happens at PR time, after e2e), yet it runs in playground Actions with the playground's `CLAUDE_CODE_OAUTH_TOKEN` (the maintainer's Claude subscription) and `GITHUB_TOKEN`. A bad WP branch could leak the token (e.g. transformed so log masking misses it, in public logs) or misuse the playground's write rights, by mistake or through prompt injection. Bounds: only ai-workflows pushers (the maintainer and agents) can put code there; GitHub damage is limited to the playground; worst case is rotating the Claude token. Accepted by the maintainer on 2026-10-31; tracked by bead `aiwf-71q`.
