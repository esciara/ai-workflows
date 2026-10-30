# Architecture decision records

Choices not covered by the spec, approved by the maintainer, one file per decision. To add one: take the next free number, copy the template below to `NNNN-<kebab-slug>.md`, fill it in, list at least two options under Options considered, and add a row to the index. Status is one of `Proposed`, `Accepted` or `Superseded by ADR-NNNN`; a new ADR stays `Proposed` until the maintainer approves it, then becomes `Accepted`. Never edit the decision of an accepted ADR; write a new ADR instead. If it changes part of the decision, add `Amends: ADR-NNNN` to the new ADR and `Amended by: ADR-NNNN` to the old one; if it replaces the decision fully, add `Supersedes: ADR-NNNN` and update both Status lines. The alias `D<n>` keeps older mentions such as "(D4)" resolvable.

## Template

```markdown
# ADR-NNNN · <title>

- Status: Proposed
- Date: YYYY-MM-DD
- Deciders: maintainer
- Alias: `D<n>`
- Supersedes: ADR-NNNN (omit if none)
- Superseded by: ADR-NNNN (omit if none)
- Amends: ADR-NNNN (omit if none)
- Amended by: ADR-NNNN (omit if none)

## Context

<the problem or constraint that forced a choice>

## Options considered

- <option>: <pros>; <cons>
- <option>: <pros>; <cons>

<why the rejected options were rejected>

## Decision

<what was decided>

Why: <rationale>

## Consequences

- <what follows from it>
```

## Index

| ADR | Alias | Title | Status |
| --- | --- | --- | --- |
| [ADR-0000](0000-stack-python-3-12.md) | D0 | Stack: Python 3.12 | Accepted |
| [ADR-0001](0001-permissions-granted-per-job-by-caller.md) | D1 | Permissions granted per job by the caller | Accepted |
| [ADR-0002](0002-called-workflows-load-code-by-ai-workflows-ref.md) | D2 | Called workflows load code by `ai_workflows_ref` | Accepted |
| [ADR-0003](0003-agents-in-their-own-read-only-jobs.md) | D3 | Agents in their own read-only jobs | Accepted |
| [ADR-0004](0004-config-read-from-default-branch-only.md) | D4 | Config read from the default branch only | Accepted |
| [ADR-0005](0005-command-authors.md) | D5 | Command authors | Accepted |
| [ADR-0006](0006-full-label-set-bootstrapped-in-wp1.md) | D6 | Full label set bootstrapped in WP1 | Accepted |
| [ADR-0007](0007-risk-tiers-and-ci-gate.md) | D7 | Risk tiers and CI gate | Accepted |
| [ADR-0008](0008-summary-comment-and-review.md) | D8 | Summary comment and review | Accepted |
| [ADR-0009](0009-approving-test-prs-on-the-playground.md) | D9 | Approving test PRs on the playground | Accepted |
| [ADR-0010](0010-config-keys-beyond-the-spec-example.md) | D10 | Config keys beyond the spec example | Accepted |
| [ADR-0011](0011-factory-loop-and-independent-verifier.md) | D11 | Factory loop and independent verifier | Accepted |
| [ADR-0012](0012-agents-use-base-action.md) | D12 | Agents use `claude-code-action/base-action` | Accepted |
| [ADR-0013](0013-publish-job-pull-requests-write.md) | D13 | Publish job gets `pull-requests: write` | Accepted |
| [ADR-0014](0014-executable-acceptance-tests.md) | D14 | Executable acceptance tests; verifier reviews the test | Accepted |
