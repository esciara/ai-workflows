# ADR-0066 · Release-candidate report does not wait for the full e2e

- Status: Accepted (2026-11-27, maintainer)
- Date: 2026-11-27
- Deciders: maintainer
- Alias: `D66`
- Amends: [ADR-0060](0060-release-tag-as-the-only-human-gate.md) (points 1 and 2)

## Context

ADR-0060 point 2 runs the full e2e on `main` HEAD after a slice's PRs merge, and point 1 puts its results in the report the maintainer reads before tagging. The full e2e is slow, so the maintainer's review waits on it.

## Options considered

- Keep e2e before the report: every tag has green e2e; the review waits for the slowest step.
- Report at once, e2e in parallel: the maintainer reviews the diff and findings while e2e runs; a tag can land on a SHA that later turns out red, fixed by a new tag.

Decided for the second: the diff and findings review is the human gate, and the e2e result arrives as a comment before anything depends on the tag.

## Decision

Once a slice's PRs have merged, `aiwf-orch` posts the release-candidate report at once: diff of the release-review paths, Workflow A findings, and the full e2e marked running. The maintainer may tag on that report. The full e2e runs in parallel on the SHA named in the report, not on a later `main` HEAD, and its results and run IDs are appended to the report as a comment. A red e2e is fixed forward on `main`; the fix gets its own release-candidate report and a new tag (agents cannot move or delete the red tag; the maintainer may). The `templates/caller.yml` pin bump, the playground pin bump, and enabling a new workflow stage on a real repo (pyteleinfo) wait for a green e2e on the tagged SHA.

Why: the maintainer's review no longer idles behind e2e, while nothing that spreads a tag (pins, real-repo rollout) happens before a green e2e on that SHA.

## Consequences

- A tag can exist on a SHA whose e2e is red. Our own pins (template, playground) and the pyteleinfo rollout wait, but target repos can already pin the tag or get a Dependabot or Renovate bump; the next tag replaces it. Accepted risk, recorded in `docs/known-issues.md`.
- ADR-0060 point 4 and the rest are unchanged.
