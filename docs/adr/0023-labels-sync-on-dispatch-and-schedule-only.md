# ADR-0023 · Labels sync on dispatch and schedule only

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D23`
- Amends: ADR-0006

## Context

ADR-0006 has WP1 bootstrap the full label set (`0006-full-label-set-bootstrapped-in-wp1.md:13`) but says nothing about when. Today the `labels` job in `commands.yml` has no `needs:` and no `if:`, holds `issues: write`, and runs `aiwf labels-sync` on every call (`.github/workflows/commands.yml:20-39`), in parallel with, not after, the author check in `parse` (`commands.yml:41-68`). The caller calls `commands.yml` on every `issue_comment` when the config is enabled (`templates/caller.yml:35-39`), so any comment by anyone, including a non-maintainer or a bot, starts a write-scoped job. Each sync lists all labels (one paginated call) and creates or patches only what differs (`scripts/aiwf/labels.py:48-62`); it never reads comment text. The caller already has `schedule` and `workflow_dispatch` triggers (`templates/caller.yml:13-20`).

## Options considered

- Keep it on every call: labels self-heal immediately; but a runner, checkout and `pip install` per comment, a write token started by untrusted triggers, and a race with publish jobs that add labels.
- Run it after the author check: only maintainers' commands trigger it; but it still runs per command, and the labels it guarantees are needed by event-driven jobs (`issues.opened`, `pull_request`) that never pass through `parse`.
- Run it only on `workflow_dispatch` and `schedule`: no write job on untrusted triggers, near-zero cost; but a fresh install has no labels until the first dispatch or daily run, and a deleted label stays missing up to a day.
- Skip it when labels already exist (cheap read first): fewer writes; but the job still starts on every comment with a write token, and the saving is small since sync already writes only differences.

Options 1, 2 and 4 all keep a per-event job; option 3 is the only one that takes label maintenance off untrusted triggers.

## Decision

Labels sync runs only on `workflow_dispatch` and `schedule`, as its own reusable workflow or job called by the caller for those events, with `issues: write` only there. The install guide (WP14) tells installers to run the workflow once by hand after install. A publisher that hits a missing label fails visibly, with a message telling the maintainer to run the sync, rather than creating labels itself.

Why: label maintenance does not need to run per comment, and no write-scoped job should start just because someone commented.

## Consequences

- `commands.yml` loses its `labels` job; the caller gains a sync job gated on `workflow_dispatch || schedule`.
- The WP1 acceptance test ("all labels exist") may need a dispatch step before its check; changing a reviewed acceptance test needs the maintainer's go (CLAUDE.md).
- Risk: up to a day without a deleted label; mitigated by the manual dispatch.
- Unverified: whether GitHub's add-labels endpoint creates a missing label on the fly; WP2 should check this on the playground before relying on either behaviour.
