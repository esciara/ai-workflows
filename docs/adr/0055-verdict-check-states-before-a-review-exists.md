# ADR-0055 · `verdict` check states before a review exists

- Status: Proposed
- Date: 2026-11-13
- Deciders: maintainer
- Alias: `D55`
- Amends: [ADR-0053](0053-merge-gate-needs-the-maintainer-only-when-there-is-a-reason.md) (what the `verdict` check shows while no review or no owner approval exists yet)

## Context

ADR-0053 makes `verdict` (job of `.github/workflows/ai-review.yml`, a required check of the ruleset on `main`) pass on `ai-review: merge` or on the owner's approval of the head commit, and fail otherwise. In use, "fail" covers states that are not problems:

- Draft PRs: the review job is skipped (Workflow A does not review drafts), so `verdict` runs with no verdict label and goes red. Every draft PR shows a red required check.
- Waiting for the maintainer: a `human-review` verdict (owned path, size, "no linked issue", ...) or a Dependabot PR (no secrets, no review) with no owner approval of the head SHA yet. This is the normal path of ADR-0053, but it shows red.
- A comment-only review: a `pull_request_review` run (submitted) by anyone, with state `commented`, re-evaluates `verdict`; outside a `pull_request` run the label is not trusted, so with no approval the check goes red, even on a PR that was green with `ai-review: merge`.

To the maintainer, red means "problem found" or "could not review". When red also means "draft" or "waiting for you", the signal is lost: real problems and normal waits look the same, and a green PR can turn red for no reason.

Problem cases that must stay red: `ai-review: changes-requested`, and a review that errored.

## Options considered

- Grey on draft, `verdict` skipped on draft PRs (chosen, for drafts): a skipped job shows grey (skipped), not red; GitHub counts a job skipped by its `if:` as passing for a required check, but a draft PR cannot be merged at all, so nothing merges early; the `ready_for_review` event already re-runs the workflow, so the check runs when the PR leaves draft. Cons: none found; covers drafts only.
- Always green, with the block carried elsewhere (e.g. by CODEOWNERS or the label only): no red ever for waits; but the required check stops gating, so a `human-review` PR on an unowned path would merge with no human seeing it, the case ADR-0053 rejected. Rejected.
- Checks API with a `neutral` conclusion: a distinct grey-ish state for "waiting"; but GitHub counts `neutral` as passing for required checks, so the PR would merge without the approval; it also needs `checks: write` and a check run created by the job instead of the job's own result, with two runs of the same name. Rejected.
- Explained red, `::error title::` annotation plus `$GITHUB_STEP_SUMMARY`: no new permission, keeps the block, tells the reader why; but the merge box still shows red, the reason is one click away, and waits still look like failures. Kept as the fallback if the pending status below does not work, and used for the problem cases (changes-requested, error) in any case.
- Pending commit status, context `verdict`, for "waiting for maintainer approval" (chosen, for waits): shows as yellow pending in the merge box with its description inline, blocks merge like any unmet required check, reads as "waiting", not "failed". Cons: needs `statuses: write` on the `verdict` job; a commit status and a check run with the same name on the same commit must be verified to behave (see Decision 2); one more moving part.

## Decision

1. **Drafts.** The `verdict` job gets `!github.event.pull_request.draft` in its `if:`. On a draft it is skipped (grey). A skipped job counts as passing for a required check, which is harmless here because GitHub never merges a draft. `ready_for_review` (already a trigger) runs the review and `verdict` again on the same head SHA, and that newer `verdict` run replaces the skipped one; the PR blocks while it is in progress.
2. **Waiting for the maintainer.** When the outcome is a `human-review` verdict or a PR that was not reviewed for a known reason (Dependabot), and there is no owner approval of the head SHA, the job publishes a commit status on the head SHA: context `verdict`, state `pending`, description `waiting for maintainer approval of <short sha> (<human-review reason>)`, then ends without failing. Only the `verdict` job gets `statuses: write`. An owner approval later turns `verdict` green (ADR-0053, point 1): the `pull_request_review` run sets the status `verdict` to `success` as well. Before relying on it, verify on the playground that (a) a pending status `verdict` keeps the PR blocked and shows in the merge box, (b) it does not conflict with the `verdict` check run of the same name (GitHub matching the required check to either, a green check run satisfying it while the status is pending), and (c) the later `success` clears it. Known risk for (b): the job itself ends green, so its check run `verdict` is a passing run of the required name; if GitHub accepts it, the PR merges with no approval. Candidate fix, to settle with the verification: give the job another check name (e.g. `verdict-eval`) and make the required `verdict` only the commit status, which the job then sets on every outcome (`success`, `pending`, `failure`). If none of this works: fall back to explained red, i.e. the job fails with `::error title=waiting for maintainer approval::<reason>` and the same text in `$GITHUB_STEP_SUMMARY`.
3. **Problems stay red, explained.** `ai-review: changes-requested` and a review that errored (review job failed or cancelled for an unknown reason) fail the job, each with an `::error title=...::` annotation and a `$GITHUB_STEP_SUMMARY` line saying which case it is.
4. **Review events.** A `pull_request_review` run acts only on review states `approved` and `dismissed`. Any other state (e.g. `commented`) leaves the result as it was, so a comment-only review cannot turn a green PR red. Caveat: a run cannot be avoided (triggers cannot filter on review state), and a new `verdict` check run, even skipped, replaces the previous one on the head SHA and counts as passing; so "leaves the result as it was" holds only if the required `verdict` is the commit status (candidate fix in point 2), which such a run does not touch. The implementation must not let a comment turn a red PR green either.

Deferred: requesting the maintainer's review automatically when `verdict` is waiting.

Why: red keeps its meaning ("something is wrong"), waits read as waits, drafts read as not-yet, and every state still blocks merge until `ai-review: merge` or the owner's approval of the head commit, as ADR-0053 decided.

## Consequences

- The merge-gate rule of ADR-0053 is unchanged: what may merge is the same; only how a not-yet-mergeable PR is shown changes.
- The `verdict` job gets one more permission, `statuses: write`, scoped to that job (owned path, policy tests may need an update).
- If the pending-status checks of Decision 2 fail on the playground, waits show as explained red; the ADR is amended in place before implementation.
- Draft PRs show `verdict` skipped, which GitHub treats as passing; safe only because drafts cannot merge. To verify on the playground with Decision 2: after `ready_for_review`, the new `verdict` run, not the skipped one, is what the ruleset reads.

## Follow-ups (own PRs, after acceptance)

- `.github/workflows/ai-review.yml`, `verdict` job: draft condition, pending status for waits, explained red for problems, review-state filter (owned path, exception PR). The reusable review workflow may need to expose the `human-review` reason as an output for the status description.
- Playground check of Decision 2 (a)–(c) before this repo relies on it.
