# ADR-0056 · Three fixed e2e slots on the playground

- Status: Accepted
- Date: 2026-11-13
- Deciders: maintainer
- Alias: `D56`
- Amends: [ADR-0043](0043-e2e-on-the-playground-consolidated.md)

## Context

[ADR-0043](0043-e2e-on-the-playground-consolidated.md) gives the playground one fixed e2e caller (`caller-e2e.yml`, `@e2e-target`) and one e2e slot: a `flock` held by the pytest controller with `AIWF_E2E_SLOT=1`, which points the single `e2e-target` ref at `HEAD`. Parallel sessions (`aiwf-review`, `aiwf-issues`, and the orchestrator or checkpoint) now run e2e at the same time, so they queue behind one slot for up to an hour per run. [`docs/known-issues.md`](../known-issues.md) lists the single slot as a P1 design issue the maintainer wants fixed.

Root constraint (unchanged): `uses: owner/repo/.github/workflows/x.yml@ref` is static, so a caller cannot pick its ref per event; one ref per caller. The playground's `main` is PR-only and its callers are added by maintainer-merged PRs, so a caller cannot be created on the fly by a test.

## Options considered

- Keep one slot: no change; sessions keep queueing, and the P1 known issue stays open.
- Three fixed slots, each a fixed caller at its own ref, picked per run: parallel e2e for the three sessions; three callers to keep in step (a drift guard covers it), more playground workflows and labels.
- Dynamic slots (a ref and a caller per session or per run, created on demand): no fixed limit; needs a write to the playground's protected `main` (or an admin bypass) per run, plus cleanup of stale callers and refs after crashes; agents have no admin rights and the playground's `main` is PR-only.

One slot is the problem being fixed. Dynamic slots need writes to the playground's `main` that agents cannot and should not make, and crash cleanup that today's kernel-released `flock` avoids. Three matches the number of sessions that run e2e in parallel.

## Decision

Replaces from ADR-0043: the **Single slot** bullet, the single `e2e-target` ref and label, and the single `caller-e2e.yml`. Its two-caller routing principle, test fixtures rules and e2e config stay, applied per slot.

- **Three slots, `n` = 1, 2, 3.** Each slot has its own ref `e2e-target-<n>` on `esciara/ai-workflows`, its own fixed caller `caller-e2e-<n>.yml` on the playground running `esciara/ai-workflows/...@e2e-target-<n>`, its own label `e2e-target-<n>` and its own PR branch prefix `e2e/<n>/`. Other e2e-only playground workflows that call this repo at the ref under test (today `notify-e2e.yml`) get one copy per slot the same way (`notify-e2e-<n>.yml`). Workflow names carry the slot (`AI workflows (e2e <n>)`) so tests find their runs. The old `e2e-target` ref, label and `caller-e2e.yml` are removed once the three slots work.
- **Routing.** Slot `n`'s caller runs for a same-repo pull request whose head branch starts with `e2e/<n>/`, or an item (issue or PR, comment events included) labelled `e2e-target-<n>`. The normal caller's gate is the exact negation of the union of the three slot gates, so each event is handled by exactly one caller. A fork PR routes only by label, as in ADR-0043. An item with two slot labels is a test bug; the helpers add exactly one.
- **Picking a slot.** `AIWF_E2E_SLOT=<n>` (1, 2 or 3) makes the pytest controller wait for slot `n`; `AIWF_E2E_SLOT=any` takes the first free slot and waits when all three are busy. Each slot is its own `flock` on `aiwf-e2e-<n>.lock` in the git common directory (an env override keeps working for unit tests), released by the kernel when the holder dies. The controller pushes `HEAD` to `e2e-target-<n>` as the agent App with `--force-with-lease` on that ref's current value, then exports the slot number to xdist workers; the e2e helpers derive the label, branch prefix and workflow names from it. A test that uses the `e2e_target` fixture fails without a slot, as today. `AIWF_E2E_SLOT=1` in existing commands keeps working and now means slot 1.
- **Drift guard.** The playground drift test (`tests/e2e/test_callers_match.py`, read-only, no slot) covers all three slot callers: each matches `templates/caller.yml` (permissions and concurrency, group prefix `ai-workflows-e2e-<n>-` normalised), each has the required jobs, the three are identical once the slot number is substituted, and the normal caller's gate is the exact negation of their union. Any playground caller or label drift fails this test before an e2e run hits it.
- **Secrets and permissions.** No new secret, token or permission. The three callers use the playground's existing `CLAUDE_CODE_OAUTH_TOKEN` and per-job `GITHUB_TOKEN` permissions, identical to today's `caller-e2e.yml`; the notify copies use the existing notify secrets. Only the agent App pushes the three refs, as for `e2e-target` today.
- **Rollout.** The playground callers, labels and the removal of `caller-e2e.yml` come in one maintainer-merged playground PR; the ai-workflows side (`scripts/aiwf/e2eslot.py`, `tests/e2e/conftest.py`, `tests/e2e/playground.py`, the drift test, `CLAUDE.md`'s e2e command) comes in one PR here, reviewed by the maintainer since it touches acceptance-test files. Deleting the old `e2e-target` ref is a remote branch deletion, done by the maintainer.

Why: up to three sessions run e2e at once with no shared mutable target between them, while keeping ADR-0043's properties: deterministic routing from a PR's first event, fork PRs always normally reviewed, every run attributable to one commit, no crash cleanup.

## Consequences

- Up to three e2e runs at once; a fourth waits, as every run waits today.
- Two runs share the playground's `CLAUDE_CODE_OAUTH_TOKEN` and subscription limits at the same time; a run that hits a usage limit fails like any agent error.
- The accepted risk "Unreviewed code on `e2e-target` runs with playground secrets" ([`docs/known-issues.md`](../known-issues.md)) now covers three refs; bounds unchanged (only ai-workflows pushers can move them, damage limited to the playground, worst case rotating the Claude token).
- The known issue "Single e2e slot for all WP tests" is closed when the implementation merges; until then ADR-0043's single slot is what runs.
- Three playground callers to keep in step; the drift test is the mechanism, not memory.
