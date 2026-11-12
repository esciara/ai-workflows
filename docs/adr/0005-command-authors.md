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

## Amendment 2026-11-12: one parse, no `/ping`

- The comment is parsed and its author checked once per run, in `config.yml`'s `load` job; it outputs `command`, one of a fixed list (`review`, `retriage`, `fix`, `no-fix`) or `''`, and puts it in the config JSON (`command`, `command_args`) that callers already pass on. `review.yml` and `triage.yml` gate their jobs on that value, so a comment that is not an accepted command runs only the config job, and callers need no new input.
- `/ping` and `commands.yml` are dropped: not in the spec. WP1's Done-when becomes "a command from a maintainer is accepted, from a non-maintainer is refused; all labels exist", checked with `/review` and `/retriage`.
- Callers must remove their `commands` job (`templates/caller.yml`): a call to a missing reusable workflow fails the whole run.
