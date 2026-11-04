# ADR-0029 · e2e test PRs routed by an `e2e/` branch prefix

- Status: Superseded by ADR-0043
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D29`
- Amends: ADR-0028, [ADR-0026](0026-e2e-isolation-base-branch-per-wp-and-one-e2e-slot.md)

## Context

ADR-0028 routes e2e test items to the playground's `caller-e2e.yml` by the `e2e-target` label. The GitHub API cannot set labels when it opens a pull request, so a test PR's first event, `opened`, never carries the label. It went to the normal caller and ran main's code, so a PR-opened test (WP2's core review, for one) never exercised the WP branch.

## Options considered

- Route PRs by a head-branch prefix `e2e/` as well as the label: the branch name is known on the first event, so routing is deterministic from `opened`; it needs a same-repo condition, or a fork PR named `e2e/...` would skip the normal caller and escape review.
- Test PR-opened behaviour only after the WP is on main: no change to the callers; but WP2 and similar WPs get no real e2e before merge.
- Same as the first option without the same-repo condition: simpler; but any fork can opt out of the normal review by naming its branch.

The second option leaves PR-triggered WPs untested before merge. The third lets an outside contributor bypass review.

## Decision

A playground event goes to `caller-e2e.yml` when:

- it is a pull request event and the head branch starts with `e2e/` and the head repo is the playground itself (`github.event.pull_request.head.repo.full_name == github.repository`), or
- the item carries the `e2e-target` label (issues, PRs and all comment events; comment events carry no head ref, so they route by label only).

The normal caller's gate is the exact negation of that expression, so each event is handled by exactly one caller. Each file holds a `TWIN:` comment pointing to the other. The e2e helpers create test PRs from `e2e/<wp>-<slug>-<suffix>` branches and add the `test-fixture` and `e2e-target` labels right after creation.

Why: deterministic from the first event, with no extra API job, and fork PRs always get the normal review.

## Consequences

- A fork PR is routed to caller-e2e only if someone with triage rights adds the `e2e-target` label.
- Verified on the playground: a same-repo `e2e/` PR's first `opened` ran caller-e2e (run 41186421732) and the normal caller skipped it (run 41186421711); an unlabelled fork PR on an `e2e/` branch ran the normal caller (run 41186450769) and caller-e2e skipped it (run 41186450743).
- The single shared e2e target remains a known design issue (`docs/known-issues.md`, bead `aiwf-6k3`).
