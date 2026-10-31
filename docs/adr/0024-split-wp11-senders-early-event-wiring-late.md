# ADR-0024 · Split WP11: senders early, event wiring late

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D24`

## Context

Swarm-plan decision D1. WP11's Done-when is "each of the 5 events sends one message". Those events are the Workflow A verdict (WP2), the reporter silent for 4 days (WP7), the B4 analysis (WP8), `fix: needs-maintainer` (WP9) and `ai: error` (WP12). The plan puts WP11 right after WP1, but in the first wave none of these events exist, so its e2e cannot pass.

## Options considered

- Split WP11: the senders and the notify step land early and are tested on their own; the full Done-when stays intact for the second half; one more work package to track.
- Move the whole WP11 to the last wave: no split; the senders get built late and nothing tests them until then.
- Keep WP11 early with a synthetic-event e2e: no reordering; weakens the Done-when, since no real event is checked.

The move-whole option delays work that has no real dependency, and the synthetic-event option tests less than the plan asks for.

## Decision

WP11 is split in two:

- WP11a: the Slack and Telegram senders plus a `notify` step, tested with a dispatch-triggered test event. Runs in an early wave.
- WP11b: wiring of the 5 events and the full Done-when. Runs after WP9 and WP12.

Why: the sender code has no dependency on the events, and the Done-when keeps its full strength in WP11b.

## Consequences

- The board gets two beads in place of WP11; WP11b depends on WP9 and WP12.
- WP11a's e2e uses a `workflow_dispatch` test event, not one of the 5 events.
