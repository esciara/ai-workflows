# ADR-0005 · Command authors

- Status: Accepted
- Date: 2026-10-30
- Alias: `D5`

## Context

Config alone could list a login without rights; rights alone include collaborators who are not maintainers.

## Decision

A slash command is accepted only if its author is in `maintainers` AND has write or admin permission on the repo. `/ping` is a maintainer-only diagnostic command (WP1).

Why: config alone could list a login without rights; rights alone include collaborators who are not maintainers.

## Consequences

- Both checks (config membership and repo permission) are required for every command.
- `/ping` is added in WP1.
