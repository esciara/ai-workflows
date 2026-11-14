# ADR-0059 · `verdict` reruns stale failed `verdict` runs on approval

- Status: Accepted
- Date: 2026-11-14
- Deciders: maintainer
- Alias: `D59`
- Amends: [ADR-0055](0055-verdict-check-states-before-a-review-exists.md) (Decision 1 and 4: a newer `verdict` run does not replace an older one across runs; comment reviews end green)

## Context

`verdict` (job of `.github/workflows/ai-review.yml`, required check of ruleset 26279687 on `main`) runs in every AI review workflow run: the `pull_request` run and one `pull_request_review` run per review. Each workflow run is its own check suite with its own `verdict` check run. ADR-0055 assumed that a newer `verdict` run replaces older ones on the head SHA. That holds only inside one suite (a rerun replaces its earlier attempt). Across suites GitHub keeps each suite's latest `verdict`, and a red one in any suite blocks the required check.

Seen on PR #119 (head 9e3c1de): run 43529129510 (`pull_request`) failed while waiting for human review; run 43529502649 (`pull_request_review`, the agent's COMMENTED review) failed in the comment branch (exit 1); the maintainer's approval run 43530786078 was green; the PR stayed BLOCKED until the maintainer reran both failed runs by hand. Every `human-review` PR needs that manual rerun today.

## Options considered

- Rerun the earlier failed `verdict` jobs from the approval run (chosen): on an owner approval of the current head, the `verdict` job lists completed runs of the same workflow on the same head SHA and reruns their failed `verdict` job (`POST /actions/jobs/{id}/rerun`). Each rerun re-evaluates with the existing logic, so it turns green only on that same owner approval of the head. Cons: one new permission, `actions: write`, on the `verdict` job; fork and Dependabot runs keep a read-only token, so their stale runs stay a manual rerun.
- Green (or neutral) while waiting for the maintainer: no red suite left behind; but the ruleset requires 0 approving reviews, so `verdict` is the only gate: a green wait opens it with no human. Rejected (as in ADR-0055).
- Concurrency with `cancel-in-progress`: the runs do not overlap (the review run is long finished when a review is submitted), so nothing gets cancelled; and a cancelled run also blocks the required check. Rejected.
- Commit status `verdict` as the gate: forgeable by any token with `statuses: write`; rejected by ADR-0055 and its playground result (a status does not satisfy a check pinned to the Actions integration). Rejected.
- Status quo, the maintainer reruns failed runs by hand: no change; but every `human-review` PR stays BLOCKED after approval until someone notices, and auto-merge (ADR-0051) never fires. Rejected.
- Remove the duplicate `verdict` entry in the ruleset only: harmless duplicate (same integration 15368), fixes nothing. Admin clean-up, done separately.

## Playground result

On `esciara/ai-workflows-playground` draft PR #135 (closed, `test-fixture`), a test workflow `rerun-exp` with `permissions: actions: write` on one job: run 43536038729 (`pull_request`) failed on purpose on attempt 1; a COMMENTED review by the agent App triggered run 43536078875 (`pull_request_review`, default `GITHUB_TOKEN`), which listed the runs of the same workflow on the head SHA and called `POST /actions/jobs/132265152439/rerun`: accepted. Run 43536038729 attempt 2 ran (triggering actor `github-actions[bot]`) and passed; the commit's latest `verdict` check run in that suite is now success (the failed one only shows with `filter=all`). So a `GITHUB_TOKEN` rerun does start the job, unlike most events made with `GITHUB_TOKEN`.

Not tested: an approval as trigger (only the maintainer can approve; the token's permissions do not depend on the review state), and `mergeStateStatus` leaving BLOCKED because of a required check (the playground has no required checks; the PR stayed BLOCKED by REVIEW_REQUIRED and draft). The first real `human-review` PR after this lands is the check. After-merge check (open, aiwf-qhk): on the next real `human-review` PR, confirm that a stale red `verdict` reruns itself after the maintainer's approval and the PR leaves BLOCKED without a manual rerun.

GitHub docs: fork PRs get a read-only `GITHUB_TOKEN` on `pull_request_review` too; workflows triggered by Dependabot get a read-only token, and a rerun keeps the original run's privileges.

## Decision

1. **Rerun on approval.** When a `pull_request_review` run of `verdict` finds an owner approval of the head SHA (ADR-0053) and goes green, it reruns the `verdict` job of every earlier completed run of the same workflow on that head SHA whose latest attempt ended `failure`, `cancelled` or `timed_out`. Not the current run, not other jobs, never `success` ones. Only on attempt 1 (a rerun does not cascade), only when the head SHA is still the PR's head (else those runs are moot), only for same-repo PRs (`head.repo.full_name == repository`; fork tokens are read-only). A refused rerun is a warning, not a failure.
2. **Comment reviews end green.** A `pull_request_review` run with state `commented` exits 0 and posts no status. Safe because every run is its own suite: a green suite cannot open the gate while another suite on the head is red, and the `pull_request` run's `verdict` still carries the answer.
3. **Permission.** The `verdict` job gets `actions: write`, used only for `POST /actions/jobs/{id}/rerun` of `verdict` jobs; no other job gets it, and no job cancels runs (ADR-0045 unchanged).

Why: the approval already decides the gate (ADR-0053); this only makes every suite on the head see it, without a human clicking rerun and without a new way to turn `verdict` green.

## Consequences

- Security: the rerun never opens the gate by itself: the rerun job evaluates the same rule (owner approval of the head commit, `ai-review: merge` on `pull_request` runs) with no new inputs. `actions: write` would also allow cancelling or rerunning other runs of this repo; the policy test limits it to this job and to single-job reruns. Agent steps still never get `GITHUB_TOKEN`; only orchestrator steps write, with per-job minimal permissions (CLAUDE.md hard rules).
- Fork PRs and Dependabot PRs: a stale failed run stays a manual rerun by the maintainer.
- Concurrency of review-event runs: each `pull_request_review` run gets its own group (`ai-review-verdict-<PR>-<run id>`), so reruns of several stale review runs do not queue in one group and cancel each other (only one pending run per group); a rerun keeps its run id, so its group differs from the approval run's. Review-event runs are no longer serialised; each evaluates the same rule from current GitHub state, so order does not matter.
- Concurrency: a rerun of the `pull_request` run joins its concurrency group `ai-review-<PR>`; if a new push is queued in that group at that instant, the rerun could replace the queued run. The head check in Decision 1 narrows this to a push between that check and the rerun.
- Policy tests: `test_no_job_has_actions_write` gets a single exception for `ai-review.yml`/`verdict` (rerun only, no cancel); the `verdict` permissions and comment-review expectations change accordingly.
- Admin clean-up (maintainer): ruleset 26279687 lists `verdict` twice (same integration 15368); remove one.
