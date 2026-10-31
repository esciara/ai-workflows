# ADR-0022 · Own reusable-workflow refs pinned to a SHA from WP14

- Status: Superseded by ADR-0040
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D22`

## Context

The policy test requires every external `uses:` to be a 40-hex SHA with a `# vX` comment (`scripts/aiwf/policy.py:93-107`), but exempts local refs and anything starting with `esciara/ai-workflows/` (`scripts/aiwf/policy.py:21`, `:24-25`, `:98`). The test scans `templates/*.yml` (`tests/test_workflow_policy.py:9`), so `templates/caller.yml`, which installers copy, passes with `@main` (`templates/caller.yml:28`, `:39`). ADR-0019 proposes that callers pin a tagged SHA before any install other than the playground, by WP14.

## Options considered

- Keep the exemption: the template tracks `main` during development with no bump churn; but the template installers copy stays unpinned, which is the supply-chain risk ADR-0013 names.
- Require a tag (`@v0.x.y`): readable, no SHA bumps per commit; but tags can be moved, so it is weaker than the rule applied to every third-party action.
- Require a SHA with a `# v0.x.y` comment, same rule as third-party actions: one rule for everything, immutable; but every release needs a template bump, and nothing in this repo can pin before the first tag exists.

Option 1 was rejected as a permanent state, option 2 because a movable ref is what the pinning rule exists to stop.

## Decision

Keep the exemption until the first release tag, then, no later than WP14, remove the `esciara/ai-workflows/` prefix from `is_exempt` so own reusable-workflow refs follow the same SHA-plus-version-comment rule as third-party actions. Local `./` refs stay exempt. The playground caller lives in the playground repo, outside this test, so it can keep `@wp<N>-…` branches (ADR-0002, ADR-0019).

Why: the template is what reaches real repos, so it must meet the same bar as any other dependency; before a tag exists there is nothing to pin to.

## Consequences

- WP14 cuts the first tag, bumps `templates/caller.yml` to its SHA, drops `OWN_REUSABLE_PREFIX` and adds a policy fixture for an unpinned own ref.
- Each release bumps the template SHA and comment.
- Until WP14 the template stays on `@main`; installs before then are playground-only (ADR-0019).
