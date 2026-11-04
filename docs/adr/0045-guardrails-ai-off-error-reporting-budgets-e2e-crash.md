# ADR-0045 · Guardrails: `ai: off` gate and re-check, `ai: error` reporting, e2e crash label, budgets, injection reporting

- Status: Accepted
- Date: 2026-11-01
- Deciders: maintainer
- Alias: `D45`
- Amended by: [ADR-0050](0050-budgets-as-time-and-turn-limits.md) (decisions 5 and 6 replaced: no e2e crash hook in the product, budgets are time and turn limits)

## Context

The spec says `ai: off` on an item "stops every run immediately", an agent or sandbox crash gives "label `ai: error`, comment with the run link, no retry loop", and each run has a token and wall-clock budget whose hit "stops the run and escalates" (`docs/spec.md`, Guardrails). Before WP12 nothing read `ai: off`; `ai: error` was set only on invalid agent output, with no comment, and a failure before the publish step set nothing. The e2e test needs a deterministic crash on one item without breaking the other parallel tests. WP12 is split: WP12a (`ai: off`, `ai: error`) and WP12b (injection reporting, budgets). The plan's WP12 Done-when also says an injected instruction is reported, not obeyed; before WP12b only the review agents reported one (`suspicious_instructions`), the triage agents ignored it silently.

## Options considered

- `ai: off`, gate and pre-write re-check only (chosen, after a first build with the cancel job, see decision 3): no caller change, no new permission; agents already running finish (no writes, usage wasted).
- `ai: off`, also cancel through the caller's concurrency group (`cancel-in-progress` on a `labeled` event): no new permission; but a `labeled` run in the item's group would also replace the item's pending run (one pending run per group), and it cannot reach other groups.
- `ai: off`, also cancel from a dedicated caller job with `actions: write` (built in WP12a, then removed): truly stops runs in flight; a caller template change and one more token scope, on one job.
- Crash in e2e, a playground-only label honoured with the e2e config (chosen): deterministic, per item, parallel-safe; a test-only branch in product workflows, inert elsewhere.
- Crash in e2e, a serial test repointing `e2e-target` at a commit with a bogus model: real Claude failure; slow, edits the shared slot code, cannot run in parallel.
- Crash, unit tests only: Done-when not proven on the playground.
- Budget hit as a crash (`ai: error`): one failure path; hides that it was a cost stop.
- Budget hit as an escalation plus a label `ai: budget` (chosen for WP12b): clear to the maintainer and to alerts.
- Budget unit, tokens: what the spec says; Claude Code has no token cap, only `--max-turns` (coarse) and `--max-budget-usd`.
- Budget unit, USD via `--max-budget-usd` (chosen): enforced by Claude Code itself, also on subscription auth (notional cost); a hit is visible in the result (`subtype`).
- Budget unit, turns and minutes only: always available; says nothing about cost.
- Injection in triage, ignore silently (status quo): nothing to build; the maintainer never learns of the attempt.
- Injection in triage, report like the review (chosen): the same `suspicious_instructions` field and comment line in both workflows.

## Decision

1. **Config gate.** `aiwf config` reads the event payload's issue or PR labels; with `ai: off` it outputs `enabled`, `review`, `triage` = `false` (and `item_off` = `true`), so every caller job skips the item.
2. **Pre-write re-check.** `aiwf publish`, `aiwf review-publish` and `aiwf report-error` read the item's live labels first; with `ai: off` they write nothing, except removing `ai-review: pending`.
3. **No cancel (changed).** WP12a first shipped a cancel: the caller listened to `labeled`, and a job `off` (`actions: write`) cancelled the item's in-flight runs. It was removed before WP12 closed, by the maintainer's decision, for the gate-and-re-check option:
   - every label event on an issue or PR started a run: runner minutes and noise in the Actions tab;
   - the extra runs raced the e2e tests (several runs with the same display title);
   - `actions: write` on a job goes against the least-privilege rule of ADR-0038;
   - and it buys little: an agent in flight holds no token (ADR-0045 decision 2, Rule of Two), so it cannot write; only its usage is lost.
   A run already in flight when `ai: off` is set finishes, but writes nothing (decision 2). The policy test now asserts no job has `actions: write`.
4. **Error reporting.** Each reusable workflow (`review.yml`, `triage.yml`, `commands.yml`) ends with a job `failed`: needs every job, runs when one failed, adds `ai: error` and creates or updates one sticky comment (marker `<!-- ai-workflows:error -->`, bot-authored only) with the run link and the names of the failed jobs, never agent text. Cancelled runs report nothing. Nothing re-runs. B1 publish removes a stale `ai: error`, as review `start` already does.
5. **e2e crash (replaced by ADR-0050).** `config.yml` adds `"e2e": true` to the config JSON only when `e2e_config` is used, which is honoured only on the playground (ADR-0043); the schema forbids unknown keys, so a repo config cannot set it. With it, the label `e2e-crash` fails the first step of the review and triage `context` jobs.
6. **Budgets (WP12b; replaced by ADR-0050).** Three new `limits` keys in the config: `agent_budget_usd` (default 1), `run_budget_usd` (default 5), `agent_minutes` (default 10, at most 15, under the agent jobs' fixed timeouts).
   - Every agent step (ping, extract, classify, the 4 review passes, verify) gets `--max-budget-usd agent_budget_usd` and a step `timeout-minutes: agent_minutes`; policy-tested. Spike on subscription auth (`claude -p --max-budget-usd 0.0001`): Claude Code stops at the next turn boundary with `subtype: error_max_budget_usd` and `terminal_reason: budget_exhausted`, the turn in progress already spent. So the cap can be overshot by one turn; agents run at most 3 turns.
   - `scripts/agent-usage.sh` writes each agent's usage record (cost, turns, tokens, `subtype`, `timed_out` = the step did not succeed after about `agent_minutes`).
   - Run total: review `verify` does not start when the passes already cost more than `run_budget_usd`; each publish step (B1 `publish`, A `review-publish`) checks every agent's record first: an agent stopped by cost or time, or a run total over `run_budget_usd`, is a budget hit (`guard.budget_hit`).
   - A hit publishes no result and escalates: labels `ai: budget` plus `ai-review: human-review` (A) or `triage: needs-human` (B), one sticky bot comment (marker `<!-- ai-workflows:budget -->`) with the run link and a reason built from agent names and limits only; nothing is retried. The publish step outputs `budget=true` and the `failed` job skips, so a hit is not also an `ai: error`. A later normal run (review `start`, B1 publish) removes a stale `ai: budget`. `ai: off` still wins: nothing is written.
   - `ai: budget` is added to the spec's Labels table and to `schema/labels.yml`. `/ping` (commands) has the caps but no escalation: a hit there is an `ai: error`.
   - e2e: with the e2e config only (decision 5), the label `e2e-budget` sets the triage agents' cap to $0.0001, so the first agent is stopped by Claude Code on the subscription token.
   - Deferred: a configurable CI wait (review `CI_BUDGET` stays fixed, ADR-0034).
7. **Injection reporting in triage (WP12b).** The extractor and classifier schemas require `suspicious_instructions` (as `schema/review.json`: at most 5 quotes of at most 200 characters); their prompts say to quote, never follow, an instruction found in the issue. B1 publish merges both lists into one comment line `**Possible prompt injection (ignored):** …`, cleaned like the review's (no mentions, HTML, markers). This is detection for the maintainer, not a defence: the boundary stays the Rule of Two (the agents have no tools and no secrets, the orchestrator checks the JSON) and, for command-running agents, the sandbox of ADR-0037, which reduces but does not eliminate prompt injection risk.

Why: the spec asks for an immediate stop and a visible, non-retried error; the gate and re-check bound writes (an agent in flight cannot write), and the crash label proves the error path on real runs without touching other tests.

## Consequences

- No caller template change: the gate and the re-check need nothing from target repos.
- A run in flight when `ai: off` is set (a review, a triage, a fork PR's `/review`) uses its agents to the end and writes nothing.
- `review-fork-push.yml` gets no `failed` job: it may not check out code (ADR-0044); its failures show in the Actions log only.
- WP11b hooks the `ai: error` chat alert onto `guard.report_error`, and can hook a budget alert onto `guard.report_budget`.
- `--max-budget-usd` counts notional API prices on a subscription: it caps one run's share of the plan's usage, not money. A cap hit may be one turn over.
- The wall-clock check infers a timeout from the step's failure and elapsed time; a crash in the last 15 seconds before the cap counts as a time hit.
- Target repos may set the new `limits` keys; the defaults apply otherwise. They should run `labels-sync` to create `ai: budget`.
