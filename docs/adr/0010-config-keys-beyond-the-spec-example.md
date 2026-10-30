# ADR-0010 · Config keys beyond the spec example

- Status: Accepted
- Date: 2026-10-30
- Alias: `D10`

## Context

The spec gives only an example config; keys and defaults beyond it were not specified.

## Decision

Keep `workflows: {review, triage}` from the example config; add top-level `enabled` (repo kill switch, default `true`), optional `model`, optional `required_checks`. Every object rejects unknown keys. Where the spec gives only examples, defaults are:

- `default_branch: main`
- `limits` 400/3/2
- `reporter_silence_days` 4/14/21 (ping < stale < close enforced in code)
- `workflows.review: true`
- `workflows.triage: false`
- `notify: none` (`none | slack | telegram`)
- `fork_prs: on-command` (`on-command | off`)

Why: the spec's example values are the natural defaults; `none` and `off` let a repo opt out.

## Consequences

- Every config object rejects unknown keys.
- A repo can opt out with `enabled: false`, `notify: none` or `fork_prs: off`.
- Ordering ping < stale < close is enforced in code.
