#!/usr/bin/env bash
# One agent's usage record, printed as one JSON line (plan: Usage limits; budgets, ADR-0045): cost, turns and tokens
# from the Claude Code execution log's result message, plus `subtype` (`error_max_budget_usd` when --max-budget-usd
# stopped the agent) and `timed_out` (the agent step failed after running for its `agent_minutes`).
# Env: EXEC_FILE (may be empty), OUTCOME (steps.claude.outcome), AGENT_START (epoch seconds), AGENT_MINUTES.
set -euo pipefail
now=$(date +%s)
elapsed=$(( now - ${AGENT_START:-$now} ))
minutes=${AGENT_MINUTES:-0}
timed_out=false
if [ "${OUTCOME:-}" != success ] && [ "$minutes" -gt 0 ] && [ "$elapsed" -ge $(( minutes * 60 - 15 )) ]; then
  timed_out=true
fi
if [ -n "${EXEC_FILE:-}" ] && [ -f "$EXEC_FILE" ]; then
  jq -c --argjson t "$timed_out" '([.[] | select(.type == "result")] | last) // {} | {cost_usd: .total_cost_usd,
    turns: .num_turns, duration_ms: .duration_ms, input_tokens: .usage.input_tokens,
    output_tokens: .usage.output_tokens, cache_read_tokens: .usage.cache_read_input_tokens,
    cache_write_tokens: .usage.cache_creation_input_tokens, subtype: .subtype, timed_out: $t}' "$EXEC_FILE"
else
  jq -cn --argjson t "$timed_out" '{timed_out: $t}'
fi
