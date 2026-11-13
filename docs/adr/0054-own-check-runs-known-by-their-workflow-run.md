# ADR-0054 · Own check runs known by their workflow run, not their name

- Status: Proposed
- Date: 2026-11-13
- Deciders: maintainer
- Alias: `D54`
- Amends: [ADR-0034](0034-workflow-a-agent-inputs-and-ci-gate.md) (how the CI gate recognises our own check runs; the `context` job's permissions)

## Context

ADR-0034 says our own check runs are those whose URL contains this run's `/actions/runs/<GITHUB_RUN_ID>/`, which needs only `checks: read`. That only covers this run. Earlier runs of ours on the same head (an `ai: error` run, a `/review` re-run, the `verdict` job) were then told apart by check name (`<caller> / <one of our job ids>`, #82). A target repo's own check with a matching name, such as a red `release / publish` or `ci / verify`, was dropped too, so the verdict could be `ai-review: merge` with red CI. ADR-0034's consequence "runs of our own caller for an earlier event are not excluded" no longer holds either. Check runs carry no workflow identity; only the runs API (`GET repos/{repo}/actions/runs/{id}`) says which workflows a run calls, and it needs `actions: read`, which ADR-0034 rejected.

## Options considered

- Match by workflow run: a check run is ours when it is this run's (URL match, as in ADR-0034) or when its workflow run's `referenced_workflows` has a path under `esciara/ai-workflows/.github/workflows/`: not forgeable by a job name, covers `verdict`, `metrics` and any caller job id with no job list; but needs `actions: read` on the `context` job and on every caller's `review` job.
- Match by check name (`<caller> / <our job id>`, the #82 rule): no new permission; but hides a target repo's real red check that happens to share a name.
- Match the `review / ` prefix only: no new permission; but still forgeable (a repo job named `review / x` is hidden) and misses our other callers' job names (`ai / failed`, `triage / …`, this repo's bare `verdict`).
- Drop name matching, keep the URL match only: no new permission; but our own failed checks from an earlier `ai: error` run (and `verdict`) count as red CI again, so #82's false `changes-requested` returns.
- Amend ADR-0034 in place (as first proposed in #93): one file to read; but ADR-0034 is implemented, and the README says an implemented ADR changes only through a new ADR.

The name-based options were rejected because a target repo picks its job names, so a real red check can be hidden and the verdict can say `merge` with red CI. The in-place amendment was rejected by the README rule.

## Decision

- A check run is ours when its app is `github-actions` and either its URL contains this run's `/actions/runs/<GITHUB_RUN_ID>/`, or its workflow run (run id from `details_url`) has a `referenced_workflows` entry whose path starts with `esciara/ai-workflows/.github/workflows/`.
- `actions: read` goes only on the orchestrator `context` job of `review.yml`, never on an agent step. Callers grant it on their `review` job: `templates/caller.yml`, this repo's `ai-review.yml`, the playground's `caller-e2e.yml`.
- Fail safe: a run that cannot be read (403, 404, bad JSON) is not ours, so its failed checks stay red CI and the verdict is never `merge`; a `::warning::` names the run.
- Lookups are cached per run id across polls.

Why: a red CI check must never be hidden; read-only access on one orchestrator job is a small cost for that.

## Consequences

- Installed callers must add `actions: read` to their `review` job when they upgrade, or GitHub refuses to start `review.yml` (`startup_failure`).
- ADR-0034's "needs only `checks: read`" and its consequence "runs of our own caller for an earlier event on the same SHA are not excluded" are replaced by this ADR: earlier runs of ours are now excluded.
- Any job in a caller workflow that also calls our reusable workflows counts as ours; a repo that puts its real CI in the same workflow file as our caller would have it ignored. The template keeps them separate.
- A PR author who edits workflows to call ours could hide a check, but they can already make any CI green by editing it: no new trust.
- One API call per distinct workflow run on the head SHA.
