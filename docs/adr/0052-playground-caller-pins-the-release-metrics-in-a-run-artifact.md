# ADR-0052 · Playground caller pins the release; per-run metrics in a run artifact

- Status: Accepted
- Date: 2026-11-12
- Deciders: maintainer
- Alias: `D52`
- Amends: [ADR-0040](0040-code-ref-and-pinning-consolidated.md) (the playground's normal caller references `@main`)

## Context

Slice 1 puts Workflow A in use on `esciara/pyteleinfo`, set up from the install guide alone, and records the first usage numbers (`docs/plan.md`, Slices). Its acceptance tests (`tests/e2e/test_wp14.py`, `tests/e2e/test_wp15.py`) need two choices the spec does not make:

- WP14 must prove a second install, set up from `templates/caller.yml` and `docs/install.md`, reviews a PR with the pinned release. The playground is the only repo tests may write to, but [ADR-0040](0040-code-ref-and-pinning-consolidated.md) keeps its normal caller on `@main` (and today it has no `review` job). Workflow files on the playground can only be changed by the maintainer: the agent App has no workflows permission.
- WP15 (spec: Usage per run) needs one JSON line of usage metrics per Workflow A run, readable later by tests and by the maintainer. The spec says it lives on the session record; [ADR-0021](0021-run-state-on-the-item-labels-and-marker-comment.md) puts bulky material in artifacts, and [ADR-0050](0050-budgets-as-time-and-turn-limits.md) removed usage from the summary comment's state block.

## Options considered

Where the second install for WP14 runs:

- Pin the playground's normal caller to the release (chosen): the playground becomes a real install from the template, tested by an ordinary PR; but the maintainer bumps its pin at each release, and tests of the normal caller exercise the release, not `main`.
- A third caller on the playground (e.g. routed by a `release/` branch prefix): leaves the normal caller on `@main`; but adds routing next to the e2e twin `if:`s (ADR-0028), one more file to keep in step.
- Give the agent App workflows write so a test PR swaps the caller for the template on its branch: no playground config change; but widens the App's rights over CI files, a security boundary, for a test convenience.

Where the per-run metrics line goes:

- A run artifact `ai-workflows-metrics` holding `metrics.jsonl`, the same line also echoed to the job log (chosen): on the session record as ADR-0021 defines it, one API call to read, no comment noise; but artifacts expire with the repo's retention (90 days by default).
- The job log only: no artifact; but reading it means downloading and grepping log archives, and logs are easy to lose among steps.
- The summary comment's state block: visible on the PR, survives retention; but ADR-0050 removed usage from it on purpose, and it grows the comment on every run.

## Decision

- The playground's normal caller (`.github/workflows/ai-workflows.yml` in `esciara/ai-workflows-playground`) references each reusable workflow of this repo as `@<40-hex SHA> # vX.Y.Z`, the release `templates/caller.yml` pins, set up from `docs/install.md`; it keeps only its e2e routing `if:` on the `config` job ([ADR-0028](archive/0028-fixed-e2e-caller-on-the-playground.md), consolidated in [ADR-0043](0043-e2e-on-the-playground-consolidated.md)). `caller-e2e.yml` stays on `@e2e-target`, unchanged. The change is a separate playground PR that the maintainer merges.
- Every Workflow A run uploads one artifact `ai-workflows-metrics` with one file `metrics.jsonl` holding exactly one JSON line (fields as asserted by `tests/e2e/playground.py`, `check_metrics`), and prints the same line to the job log.

Why: a pinned playground caller is exactly what a target repo runs, so WP14's test proves the template and the release, not a test-only path; the artifact is the session record ADR-0021 already defines, and needs no new rights or comment changes.

## Consequences

- Each release bumps the playground's normal caller with the template (maintainer PR on the playground); until bumped, the normal caller runs the previous release.
- Tests that use the playground's normal caller run the release, not `main`; WP tests keep using the e2e caller at `@e2e-target`.
- Usage numbers older than the artifact retention are gone unless recorded; the first numbers go into `docs/plan.md` (Usage limits).
- [ADR-0040](0040-code-ref-and-pinning-consolidated.md) carries `Amended by: ADR-0052`.
