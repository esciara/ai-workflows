# ADR-0041 · Review output: sticky summary comment; GitHub review only when needed (consolidated)

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D41`
- Supersedes: [ADR-0008](0008-summary-comment-and-review.md), [ADR-0016](0016-review-summary-in-a-sticky-comment-reviews-only-when-needed.md)

## Context

How Workflow A publishes its result was decided in ADR-0008 (summary in one marker comment updated in place; from WP3 a short review on every run) and ADR-0016 (a review only when something is new; the bot dismisses its own Request changes). ADR-0016 reversed ADR-0008's review on every run, and ADR-0016 leans on ADR-0008 for the sticky comment. Agents read ADRs as live rules, so the reversed text must not stay current. `docs/spec.md` (Workflow A, "How it is sent") now states the ADR-0016 reading.

GitHub facts: a submitted review cannot be deleted, only its body edited or the review dismissed; a `COMMENT` review does not clear an earlier `REQUEST_CHANGES` from the same reviewer; dismissing on a protected branch needs an admin or someone on the dismiss list.

## Options considered

- Keep ADR-0008 and ADR-0016 as they are: no new file; the reader has to merge two ADRs and still meets "a review on every run" as current.
- A consolidated ADR that states only the current rule and supersedes both: one place to read; one more ADR.

The first leaves reversed text that agents read as current; the README rule requires a superseding ADR when part of a decision is removed or reversed.

## Decision

Replaces: ADR-0008 (its short review with inline comments posted on every run from WP3), ADR-0016 (nothing reversed; restated here with the sticky comment it relied on).

- The summary is one issue comment per PR, written by the workflow's bot identity, found by its hidden marker and updated in place on every run. It also carries the run state block ([ADR-0021](0021-run-state-on-the-item-labels-and-marker-comment.md)). Reruns never add a second summary.
- WP2 publishes the summary comment and the verdict label only.
- From WP3, each run submits at most one GitHub review, never Approve: Request changes when the verdict is `changes-requested`, Comment otherwise. It carries that run's new inline comments and a one-line body with the verdict and a link to the summary. No review is submitted when the run has no new inline comments and the review state would not change.
- When the verdict stops being `changes-requested`, the orchestrator dismisses its own last Request changes review with a message linking to the summary.

Why: one place to read the result, a quiet timeline on reruns, and a review state that always matches the verdict.

## Consequences

- WP3 lists the bot's reviews and dismisses its last Request changes review; its acceptance test covers a push with no change (no new review) and a fix after `changes-requested` (old review dismissed).
- Risk: if dismissal is refused (protected branch, `GITHUB_TOKEN` not on the dismiss list), the stale Request changes stays; the orchestrator says so in the summary and the maintainer dismisses it by hand.
- Unverified until WP3: whether a `github-actions[bot]` Request changes review counts towards branch protection on the playground.
