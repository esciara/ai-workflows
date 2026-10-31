# ADR-0025 · Seams PR before fan-out

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D25`

## Context

Swarm-plan decision D2. WP2 and WP5 run in parallel but both edit the same shared paths: `scripts/aiwf/cli.py` (subcommands), `scripts/aiwf/publish.py` (sticky comment, labels), `tests/e2e/playground.py` (PR and issue helpers). Under ADR-0015 only one open PR may change a shared path, so without a change WP5 waits for WP2 to merge before touching them.

## Options considered

- A small seams PR by the orchestrator before fan-out: removes most WP2/WP5 conflicts, tracks then mostly add new files; one more PR before wave 1 starts.
- No seams PR, one open PR per shared path: no extra work up front; WP5 is serialised behind WP2 on every shared file.

## Decision

Before fan-out, the orchestrator opens a seams PR, merged before WP5 starts. It adds:

- per-module command registration in `cli.py`: each module registers its own subcommands;
- per-workflow publishers: `publish.py` dispatches by kind to one module per workflow;
- shared e2e helpers for PR and issue fixtures;
- an alternative e2e config file accepted by the reusable workflows (ADR-0028).

Why: the seams turn most later shared-path edits into new files, so parallel tracks rebase cleanly.

## Consequences

- WP5 does not start until the seams PR is merged.
- New workflows add a command module and a publisher module rather than editing `cli.py` and `publish.py`.
- The exact location and source of the e2e config file are decided in this PR (ADR-0028).
