# ADR-0020 · Test-PR approval and admin bypass on the playground only

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D20`
- Amends: ADR-0009

## Context

ADR-0009 lets `esciara` approve test PRs that come from the fork `opinionated-digital-center/ai-workflows-playground` or the tester App, and otherwise merge with an admin bypass (`0009-approving-test-prs-on-the-playground.md:13`). It does not say where this applies. The maintainer controls both the fork's organisation and the `ai-workflows-tester` App (`CLAUDE.md`, Testing), so such an approval is a self-approval in all but name: branch protection is satisfied without a second person looking. WP1 already used it for three playground merges, #4, #7 and #10 (`docs/progress.md:30`).

## Options considered

- Leave ADR-0009 unscoped: no change; but nothing stops the same shortcut on `esciara/ai-workflows` or a real target repo, where approval is meant to be a real check.
- Scope it to the playground, with each use logged: keeps the playground practical for a solo maintainer, keeps approvals meaningful elsewhere, and leaves an audit trail; but logging is a manual step.
- Ban it everywhere and turn off required approvals on the playground: honest about who approves; but loses the branch-protection behaviour that WP3 (Request changes blocks merge) needs to test.

Option 1 was rejected because the self-approval risk is invisible, option 3 because the playground must keep realistic branch protection.

## Decision

Approving test PRs from the fork or the tester App, and admin-bypass merges, are allowed only on `esciara/ai-workflows-playground`, never on `esciara/ai-workflows` or any real target repo. Each use is logged in the description of the `esciara/ai-workflows` WP PR that needed it: playground PR number, approval or bypass, and why.

Why: on the playground the approval is a test mechanism, not a review; elsewhere it would silently defeat branch protection.

## Consequences

- The WP PR template or checklist gains a "playground approvals / bypasses" line.
- Risk accepted: playground approvals prove nothing about review quality; they only exercise branch protection.
- WP14's install guide must not suggest the fork or tester-App trick to installers.
