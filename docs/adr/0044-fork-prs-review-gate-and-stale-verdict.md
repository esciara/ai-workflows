# ADR-0044 · Fork PRs: a review gate, and a pull_request_target job that clears a stale verdict

- Status: Proposed
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D44`

## Context

The spec reviews fork PRs on public repos only after a maintainer's `/review` (`fork_prs: on-command`), with the fork's code read as text and never executed, and CLAUDE.md forbids `pull_request_target` with checkout-and-execute. Two gaps were open for WP4. First, review.yml took the PR number and head SHA from the `pull_request` payload, so a `/review` comment (an `issue_comment` event) could not start a review, and nothing kept fork PR events out. Second, a fork's own `pull_request` run has a read-only token and no secrets: after a `/review`, a new fork push cannot remove the verdict label, so `ai-review: merge` would stay on code nobody reviewed.

## Options considered

- Gate in review.yml, no new trigger for the review itself: a first `gate` job decides from the event (same-repo non-draft PR event, or `/review` from a maintainer per ADR-0005) and hands the PR number and head SHA to the other jobs; fork PR events start nothing. Pros: one review path for both events, the existing caller routing is enough; cons: a few seconds pass between `/review` and the checkout, so the context job checks the head is still the gated SHA.
- Review fork PRs from a `pull_request_target` run: pros: secrets available at once; cons: exactly the pattern the hard rules forbid once code is checked out.
- Stale verdict, option A: a fork-only `pull_request_target` (synchronize) job in the caller, calling `review-fork-push.yml`: no checkout, no secret, API calls only, `pull-requests: write`; it removes the verdict label and posts a note asking for a new `/review`. Pros: no verdict on unreviewed code; cons: adds the `pull_request_target` trigger to the caller.
- Stale verdict, option B: do nothing, the summary shows the reviewed SHA. Pros: simplest; cons: a stale `merge` label invites merging unreviewed code.

The maintainer chose the gate and option A (WP4 plan, Q1 = A).

## Decision

review.yml gets a `gate` job (`contents: read`, `pull-requests: read`) running `aiwf review-gate`, which reads the event payload from `$GITHUB_EVENT_PATH`: a `pull_request` event of a same-repo non-draft PR is reviewed; a fork PR event never is; `/review` on an open PR from a maintainer reviews its current head (a forced run on a same-repo PR, drafts included), except a fork PR when `fork_prs: off`. Every later job takes the PR number and head SHA from the gate's outputs; the context job checks out `refs/pull/<n>/head` without credentials, fails if it is not the gated SHA, and reads it as text only (ADR-0034); agent jobs keep `permissions: {}`.

The caller adds `pull_request_target: [synchronize]` and a `review-fork-push` job, fork PRs only, `pull-requests: write`, no secrets, calling `review-fork-push.yml`: API calls only, PR fields through env vars; it removes `ai-review: merge`, `changes-requested` or `human-review` and, when it removed one, posts a note. Its runs use their own concurrency group so the review queue cannot cancel them. A policy rule enforces, for every job that can run on `pull_request_target`: no checkout at all, no event data in `run:`, no secrets; a policy test pins the caller job and the reusable workflow to `pull-requests: write`.

Why: one review path, fork code never executed, and no verdict outlives the commit it was given for.

## Consequences

- Target repos that copied the caller before WP4 must add the `pull_request_target` trigger and the `review-fork-push` job; the e2e caller in the playground needs the same change (maintainer edit) before the stale-verdict job can be tested end to end. WP4's acceptance test covers the gate only.
- A fork push during a running review is not caught: the label it then publishes is for the older SHA, which the summary shows. A push between `/review` and the checkout fails the run (`ai: error`); the maintainer comments `/review` again.
- Fork PR runs from first-time contributors may wait for approval; they review nothing either way.
