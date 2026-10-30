# ADR-0008 · Summary comment and review

- Status: Accepted
- Date: 2026-10-30
- Alias: `D8`
- Amended by: [ADR-0016](0016-review-summary-in-a-sticky-comment-reviews-only-when-needed.md)

## Context

Reruns must not spam the PR; there should be one place to read the result.

## Decision

The summary is one issue comment found by a hidden marker and updated in place. From WP3 each run also posts a short review with inline comments and a link to the summary. WP2 publishes comment + label only.

Why: one place to read, no spam on reruns.

## Consequences

- WP2 publishes comment + label only.
- WP3 adds the short review with inline comments.
