# ADR-0000 · Stack: Python 3.12

- Status: Accepted
- Date: 2026-10-30
- Alias: `D0`

## Context

WP0 had to pick a small, boring stack for the orchestrator scripts (CLAUDE.md offered TypeScript on Node 20 or Python 3.12).

## Decision

Orchestrator scripts are Python 3.12 (pytest, pyyaml, jsonschema), calling GitHub through the `gh` CLI via `subprocess`.

Why: preinstalled on runners, no build step, boring.

## Consequences

- No build step for scripts.
- GitHub calls go through the `gh` CLI, not an HTTP client library.
