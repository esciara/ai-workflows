# ADR-0045 · Guardrails: `ai: off` gate and cancel, `ai: error` reporting, e2e crash label, budgets

- Status: Proposed
- Date: 2026-11-01
- Deciders: maintainer
- Alias: `D45`

## Context

The spec says `ai: off` on an item "stops every run immediately", an agent or sandbox crash gives "label `ai: error`, comment with the run link, no retry loop", and each run has a token and wall-clock budget whose hit "stops the run and escalates" (`docs/spec.md`, Guardrails). Before WP12 nothing read `ai: off`; `ai: error` was set only on invalid agent output, with no comment, and a failure before the publish step set nothing. The e2e test needs a deterministic crash on one item without breaking the other parallel tests. WP12 is split: WP12a (`ai: off`, `ai: error`, this PR) and WP12b (injection reporting, budgets).

## Options considered

- `ai: off`, gate and pre-write re-check only: no caller change, no new permission; agents already running finish (no writes, usage wasted).
- `ai: off`, also cancel through the caller's concurrency group (`cancel-in-progress` on a `labeled` event): no new permission; but a `labeled` run in the item's group would also replace the item's pending run (one pending run per group), and it cannot reach other groups.
- `ai: off`, also cancel from a dedicated caller job with `actions: write` (chosen): truly stops runs in flight; a caller template change and one more token scope, on one job.
- Crash in e2e, a playground-only label honoured with the e2e config (chosen): deterministic, per item, parallel-safe; a test-only branch in product workflows, inert elsewhere.
- Crash in e2e, a serial test repointing `e2e-target` at a commit with a bogus model: real Claude failure; slow, edits the shared slot code, cannot run in parallel.
- Crash, unit tests only: Done-when not proven on the playground.
- Budget hit as a crash (`ai: error`): one failure path; hides that it was a cost stop.
- Budget hit as an escalation plus a label `ai: budget` (chosen for WP12b): clear to the maintainer and to alerts.

## Decision

1. **Config gate.** `aiwf config` reads the event payload's issue or PR labels; with `ai: off` it outputs `enabled`, `review`, `triage` = `false` (and `item_off` = `true`), so every caller job skips the item.
2. **Pre-write re-check.** `aiwf publish`, `aiwf review-publish` and `aiwf report-error` read the item's live labels first; with `ai: off` they write nothing, except removing `ai-review: pending`.
3. **Cancel.** The caller listens to `labeled` on issues and PRs. A `labeled` run has a concurrency group of its own and runs only the job `off` (config is skipped), gated on the label `ai: off`; it calls `off.yml`, whose job `cancel` (`actions: write`, `contents: read`; the only job with `actions: write`, policy-tested) cancels this workflow's in-flight runs for the item: `pull_request` runs by PR number, `issues`/`issue_comment` runs by display title (the item title at event time). The caller job key is quoted (`"off":`) because YAML 1.1 parsers read a bare `off` as false.
4. **Error reporting.** Each reusable workflow (`review.yml`, `triage.yml`, `commands.yml`) ends with a job `failed`: needs every job, runs when one failed, adds `ai: error` and creates or updates one sticky comment (marker `<!-- ai-workflows:error -->`, bot-authored only) with the run link and the names of the failed jobs, never agent text. Cancelled runs report nothing. Nothing re-runs. B1 publish removes a stale `ai: error`, as review `start` already does.
5. **e2e crash.** `config.yml` adds `"e2e": true` to the config JSON only when `e2e_config` is used, which is honoured only on the playground (ADR-0043); the schema forbids unknown keys, so a repo config cannot set it. With it, the label `e2e-crash` fails the first step of the review and triage `context` jobs.
6. **Budgets (WP12b, recorded here).** USD via `--max-budget-usd` per agent plus a run total checked by the orchestrator (verified on subscription auth; fallback turns and minutes). A hit escalates (A `ai-review: human-review`, B `triage: needs-human`) and adds the label `ai: budget`. This adds `ai: budget` to the spec's label list (Labels table); the orchestrator updates `docs/spec.md` and `schema/labels.yml` with WP12b.

Why: the spec asks for an immediate stop and a visible, non-retried error; the gate and re-check bound writes, the cancel job bounds usage, and the crash label proves the error path on real runs without touching other tests.

## Consequences

- Target repos must copy the new caller template (`labeled` triggers, the concurrency group, the `off` job, the config `if:`); until then the gate and re-check still apply, only the cancel is missing. Every label event on an issue or PR starts a short run (all jobs skipped unless the label is `ai: off`).
- Fork PRs: a `pull_request` `labeled` event from a fork has a read-only token, so the cancel fails there; an in-flight `/review` run on a fork PR finishes, but writes nothing.
- A cancelled review leaves `ai-review: pending` on the PR; the next review's `start` clears it.
- Runs of an issue whose title matches another item's are also cancelled (same workflow only); accepted, it only stops a run.
- `review-fork-push.yml` gets no `failed` job: it may not check out code (ADR-0044); its failures show in the Actions log only.
- WP11b hooks the `ai: error` chat alert onto `guard.report_error`.
