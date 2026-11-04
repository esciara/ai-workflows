# ADR-0003 · Agents in their own read-only jobs

- Status: Superseded by ADR-0039
- Date: 2026-10-30
- Alias: `D3`
- Amended by: [ADR-0018](0018-agent-jobs-get-no-token-permissions.md)

## Context

Rule of Two: agents read untrusted text, so they must not hold write tools or secrets; reader and writer are split.

## Decision

Agents run in separate jobs with `contents: read` only, no `id-token`, no `GITHUB_TOKEN` passed; they hand JSON (job output or artifact) to a separate orchestrator job that writes.

Why: Rule of Two, reader/writer split.

## Consequences

- To be validated in WP2; if `claude-code-action` insists on a token, stop and ask the maintainer. Validated in WP1: see [ADR-0012](0012-agents-use-base-action.md).
- Agent output reaches the writer only as JSON (job output or artifact).
