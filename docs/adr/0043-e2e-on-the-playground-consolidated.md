# ADR-0043 · e2e on the playground: one e2e caller, routing, single slot, e2e config (consolidated)

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D43`
- Supersedes: [ADR-0026](0026-e2e-isolation-base-branch-per-wp-and-one-e2e-slot.md), [ADR-0028](0028-fixed-e2e-caller-on-the-playground.md), [ADR-0029](0029-e2e-pr-routing-by-branch-prefix.md)
- Amends: [ADR-0004](0004-config-read-from-default-branch-only.md)

## Context

How e2e tests on `esciara/ai-workflows-playground` run a WP's code was decided in ADR-0026 (a playground base branch per WP for PR tests, a file-lock slot for issue and comment tests), ADR-0028 (one fixed e2e caller at `@e2e-target`, routed by the `e2e-target` label, an alternative e2e config) and ADR-0029 (PRs also routed by an `e2e/` head-branch prefix). Later changes made parts of them wrong: PR tests no longer target a per-WP playground base branch, the slot covers every test that points `e2e-target`, PR or not, routing is no longer by label only, and the e2e config is a file of the ai-workflows commit under test, not a playground file. Agents read ADRs as live rules, so the leftover text must not stay current.

Root constraint: `uses: owner/repo/.github/workflows/x.yml@ref` is static, so a caller cannot pick the ref per event. The GitHub API cannot set labels when it opens a pull request, so a PR's `opened` event never carries a label.

## Options considered

- Keep ADR-0026, ADR-0028 and ADR-0029 with their amendments: no new file; the reader has to merge three ADRs and still meets per-WP base branches and label-only routing as current.
- A consolidated ADR that states only the current setup and supersedes the three: one place to read; one more ADR.

The first leaves wrong text that agents read as current; the README rule requires a superseding ADR when part of a decision is removed or reversed.

## Decision

Replaces: ADR-0026 (its long-lived playground base branch `e2e/wp<N>` per WP with its own caller for PR tests, and the slot limited to issue and comment tests), ADR-0028 (routing only items labelled `e2e-target`, and the e2e config as a playground file such as `.github/ai-workflows.e2e.yml`), ADR-0029 (nothing reversed; restated here).

- **Two callers.** The playground has its normal caller (`ai-workflows.yml`, `@main`) and a fixed e2e caller (`caller-e2e.yml`) that always runs `esciara/ai-workflows/...@e2e-target`. Both were added by maintainer-merged playground PRs; tests never change them.
- **Routing.** An event goes to `caller-e2e.yml` when it is a pull request event whose head branch starts with `e2e/` and whose head repo is the playground itself (`github.event.pull_request.head.repo.full_name == github.repository`), or when the item (issue or PR, all comment events included) carries the `e2e-target` label. The normal caller's gate is the exact negation, so each event is handled by exactly one caller; each file holds a `TWIN:` comment pointing to the other. A fork PR on an `e2e/` branch goes to the normal caller unless someone with triage rights labels it.
- **Test fixtures.** Test issues get `test-fixture` and `e2e-target` at creation. Test PRs are opened against the playground's default branch from `e2e/<wp>-<slug>-<suffix>` branches, and get `test-fixture` and `e2e-target` right after creation. Fixtures are scoped to their own items: unique titles or exact-title reuse, never hard-coded or "latest" numbers.
- **Single slot.** There is one `e2e-target` pointer, guarded by one e2e slot: a `flock` on a lock file in the git common directory (`$AIWF_E2E_LOCK` overrides), released by the kernel when the holder dies. With `AIWF_E2E_SLOT=1`, the pytest controller holds the slot for the whole run and pushes `e2e-target` to `HEAD` as the agent App with `--force-with-lease` on the pointer's current value (`scripts/aiwf/e2eslot.py`); a test that uses the `e2e_target` fixture fails without the slot.
- **e2e config.** The reusable `config.yml` takes an input `e2e_config`, passed only by `caller-e2e.yml`: the config is then read from `tests/e2e/config/<name>` of the ai-workflows commit under test (`job.workflow_sha`), never from a playground branch or a PR head. It is honoured only for the playground repo and fails closed elsewhere. This is the only exception to [ADR-0004](0004-config-read-from-default-branch-only.md) besides its `config_ref` on `workflow_dispatch`.

Why: one maintainer PR replaces a caller flip and revert per test; routing is deterministic from a PR's first event; fork PRs always get the normal review; one slot keeps every run attributable to one WP, without blocking merges or needing a cleanup after a crash.

## Consequences

- e2e runs that need `e2e-target` run one at a time across tracks.
- KNOWN DESIGN ISSUE (see [`docs/known-issues.md`](../known-issues.md)): the single slot is a stopgap; all e2e runs share one mutable global target and WP tests cannot be isolated. The maintainer called this unsatisfactory; it must be fixed sooner rather than later. Tracked by bead `aiwf-6k3` (P1).
- ACCEPTED RISK (see [`docs/known-issues.md`](../known-issues.md)): code on `e2e-target` is unreviewed (review happens at PR time, after e2e), yet it runs in playground Actions with the playground's `CLAUDE_CODE_OAUTH_TOKEN` and `GITHUB_TOKEN`. Bounds: only ai-workflows pushers (the maintainer and agents) can put code there; GitHub damage is limited to the playground; worst case is rotating the Claude token. Accepted by the maintainer on 2026-10-31; tracked by bead `aiwf-71q`.
- Verified on the playground: a same-repo `e2e/` PR's first `opened` ran caller-e2e (run 41186421732) and the normal caller skipped it (run 41186421711); an unlabelled fork PR on an `e2e/` branch ran the normal caller (run 41186450769) and caller-e2e skipped it (run 41186450743).
