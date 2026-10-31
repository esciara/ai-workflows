# ADR-0016 · Review summary in a sticky comment; GitHub reviews only when needed

- Status: Superseded by ADR-0041
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D16`
- Amends: ADR-0008

## Context

ADR-0008 keeps the summary in one issue comment found by a hidden marker and updated in place, and from WP3 posts a short review with inline comments on every run (`0008-summary-comment-and-review.md:13`). The spec is not consistent on this: `docs/spec.md:102` says "The summary and the inline comments go out together as one GitHub review", while `docs/spec.md:62` says "create or update the single review comment (found by a hidden marker), submit one GitHub review … carrying the inline comments", `docs/spec.md:16` promises "one self-updating review comment", and `docs/spec.md:296` says "One summary comment per PR or issue, updated in place, so reruns never spam the thread". Every push reruns the review (`docs/spec.md:63`). A submitted review cannot be deleted, only its body edited or the review dismissed; only pending reviews can be deleted (REST docs, "Update a review" and "Delete a pending review"). A `COMMENT` review does not clear an earlier `REQUEST_CHANGES` from the same reviewer, so a fixed PR keeps the bot's blocking review until it is dismissed. Dismissing on a protected branch needs an admin or someone on the dismiss list (REST docs, "Dismiss a review"). WP3 builds the review, so this must be settled before WP3 starts.

## Options considered

- Follow `spec.md:102` literally, one review per run with the full summary as its body: one object holds verdict and findings, and the verdict sits in the PR's review state; but every push adds a full, undeletable summary to the timeline, which breaks `spec.md:296`, and older summaries stay visible and contradict the newest.
- Keep ADR-0008, sticky comment plus a review on every run: one place to read the summary; but a push with no new inline findings and an unchanged verdict still adds a review, and a `COMMENT` review after a fix leaves the old Request changes blocking.
- Sticky comment holds the summary; a review is submitted only when there is something new: the review carries the new inline comments and a one-line body (verdict and a link to the summary), and is sent only when the run has new inline comments or the review state must change; when the verdict leaves `changes-requested`, the orchestrator dismisses its own previous Request changes review: reruns add nothing when nothing changed, the summary stays in one place, and the review state always matches the verdict; but it adds logic (find and dismiss the bot's last review) and dismissal may be refused on protected branches.

Option 1 was rejected because it is the spam that `spec.md:296` forbids, and option 2 because its review state can go stale after a fix.

## Decision

Option 3. The summary stays in the sticky comment (ADR-0008). Each run submits at most one GitHub review, never Approve: Request changes when the verdict is `changes-requested`, Comment otherwise, carrying that run's new inline comments and a one-line body linking to the summary. No review is submitted when the run has no new inline comments and the review state would not change. When the verdict stops being `changes-requested`, the orchestrator dismisses its own last Request changes review with a message linking to the summary. `spec.md:102` is read as "inline comments and verdict go out together in one review per run, never split".

Why: it meets `spec.md:62`, `:102` and `:296` together, keeps the timeline quiet on reruns, and keeps branch protection in step with the verdict.

## Consequences

- The maintainer should confirm this reading of `spec.md:102`, or edit the spec, before WP3.
- WP3 needs to list the bot's reviews and dismiss its last Request changes review; its acceptance test should cover push-with-no-change (no new review) and fix-after-changes-requested (old review dismissed).
- Risk: if dismissal is refused (protected branch, `GITHUB_TOKEN` not on the dismiss list), the stale Request changes stays; the orchestrator then says so in the summary and the maintainer dismisses it by hand.
- Unverified until WP3: whether a `github-actions[bot]` Request changes review counts towards branch protection on the playground.
