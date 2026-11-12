# ADR-0050 · Budgets as time and turn limits; no test-only hooks in the product

- Status: Accepted
- Date: 2026-11-04
- Deciders: maintainer
- Alias: `D50`
- Amends: [ADR-0045](0045-guardrails-ai-off-error-reporting-budgets-e2e-crash.md) decisions 5 (e2e crash label) and 6 (budgets); the rest of ADR-0045 stands

## Context

ADR-0045 gave every agent a dollar cap (`--max-budget-usd agent_budget_usd`), a run total (`run_budget_usd`, summed from per-agent usage records written by `scripts/agent-usage.sh` and passed between jobs), a configurable step timeout (`agent_minutes`), a separate escalation path (`ai: budget` label, sticky budget note, `budget` job output that suppresses `ai: error`), and e2e-only hooks in the shipped workflows (`e2e_config` input, `"e2e": true` config flag, `e2e-crash` and `e2e-budget` labels) to exercise them. Model access is the maintainer's flat Claude subscription: the dollar figures are notional API prices, not money. The critical review of 2026-11-04 found this machinery out of proportion to what it protects, and the test hooks to be product code that only tests use.

## Options considered

- Keep dollar budgets: per-agent and per-run caps in USD; but the cost is notional on a subscription, and it needs usage records, a run total across jobs, a second escalation path and three config keys.
- Time and turn limits (chosen): every agent step has a fixed `timeout-minutes` and claude-code-action's `--max-turns`; a hit fails the agent's job, which the existing `failed` job reports as `ai: error` with the run link. No config key, no usage plumbing, one failure path.

## Decision

- Every agent step (extract, classify, the 4 review passes, verify) has `--max-turns` (2 or 3) and a fixed step `timeout-minutes` (5 or 10), below its job's timeout so a hit is a step failure, not a cancel; policy-tested (`tests/test_workflow_policy.py`).
- A hit fails the job; the `failed` job labels `ai: error` and posts one sticky error comment with the run link; nothing retries. There is no `ai: budget` label, no budget note, no run total and no `limits.agent_budget_usd`, `limits.run_budget_usd` or `limits.agent_minutes` config key.
- The shipped workflows hold no test-only input or hook: `config.yml` has no `e2e_config`, the config JSON no `e2e` flag, `review.yml` and `triage.yml` no `e2e-crash` or `e2e-budget` steps. The playground triggers test cases by ordinary means: its e2e caller passes `config_path: .github/ai-workflows-e2e.yml` (a playground file), and for items labelled `e2e-crash` an invalid model token, so the first agent job fails.

Why: on a subscription the useful bound is how long and how many turns an agent may run; the error path already exists and is what the maintainer watches.

## Consequences

- A run that hits a limit reads as an error (`ai: error`), not a separate escalation; the run log says which step timed out or ran out of turns.
- Per-agent cost and token usage is no longer recorded in the review state block; it stays visible in each agent step's log.
- The e2e config lives in the playground (`.github/ai-workflows-e2e.yml`), no longer on the ai-workflows branch under test; a WP that needs a different e2e config changes the playground file (ADR-0043 amended in place).
- Target repos that set the removed `limits` keys fail config validation (the schema allows no unknown keys); they delete those lines. A stale `ai: budget` label on a repo stays until removed by hand.
