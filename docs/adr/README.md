# Architecture decision records

Product and security choices not covered by the spec, approved by the maintainer, one file per decision. Process and how-we-work rules are not ADRs: they live only in `CLAUDE.md`, edited in place, and git history is the record. To add an ADR: take the next free number (`archive/` included), copy the template below to `NNNN-<kebab-slug>.md`, fill it in and list at least two options under Options considered. Status is one of `Proposed`, `Accepted` or `Superseded by ADR-NNNN`; a new ADR stays `Proposed` until the maintainer approves it, then becomes `Accepted`. An ADR may be amended in place while its decision is not yet implemented. Once implemented, change it with a new ADR: `Amends: ADR-NNNN` in the new one and `Amended by: ADR-NNNN` in the old one, or `Supersedes: ADR-NNNN` in the new one and Status `Superseded by ADR-NNNN` in the old one. Superseded ADRs move to `archive/`. The alias `D<n>` keeps older mentions such as "(D4)" resolvable.

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

List this folder (`ls docs/adr`); superseded ADRs are in `archive/`.
