# ADR-0021 · Run state lives on the item: labels plus a marker comment

- Status: Proposed
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D21`

## Context

The plan leaves open where run state lives and says WP1 decides it (`docs/plan.md:93`). WP1 did not need any state across runs, so the code holds no choice yet: agent JSON reaches the writer as a job output within one run (`.github/workflows/commands.yml:81`, `:124`); the `/ping` reply carries a hidden marker `<!-- ai-workflows:ping -->` but is posted as a new comment each time, not found and updated (`scripts/aiwf/publish.py:40`, `:56`); labels from `schema/labels.yml` already encode where an item stands (`schema/labels.yml:7-22`). Later WPs need state across runs: findings marked resolved or still open on each push (`docs/spec.md:63`), info-request and fix-round counters (`docs/spec.md:135`, `:191-195`), the repro test and its output on the "session record" (`docs/spec.md:134`), and per-run metrics (`docs/spec.md:310`). Agents never push or edit target repos beyond fix branches (`CLAUDE.md`, Hard rules).

## Options considered

- Labels: visible, already in place, cheap to query; but one bit each, no counters or findings lists.
- Hidden-marker comment with a JSON block: per-item, visible next to the work, survives forever, needs only `issues`/`pull-requests: write` already granted; but anyone can post a comment containing the marker, and a comment is capped at 65,536 characters.
- Workflow artifacts: good for bulky logs and transcripts; but they expire (90 days at most on public repos) and are hard to find from the item.
- A state branch in the target repo: unlimited and versioned; but needs `contents: write` and writes to target repos outside fix branches.
- Actions cache: no new permission; but evictable (7 days unused, size cap) and scoped by branch, so not a store.

Labels alone are too thin, a state branch breaks the hard rules, and caches can vanish. Artifacts are kept only for what may expire.

## Decision

Proposed: state lives on the item. Labels carry the phase (as today). The orchestrator's sticky comment (ADR-0008, ADR-0016) ends with a hidden marker and a JSON state block (schema-validated, versioned): finding IDs and status, info-request count, fix-round count, last run link. The repro test and its output go in that comment when they fit, otherwise in the B2 comment as a collapsed block. Bulky per-run material (transcripts, metrics, logs) goes to workflow artifacts linked from the comment. When reading state, the orchestrator only trusts marker comments authored by the workflow's own bot identity, and treats a missing or invalid block as "no prior state".

Why: it reuses permissions and the marker pattern already in place, keeps state where the maintainer looks, and adds no store to secure.

## Consequences

- This closes the open point in `plan.md:93`; the plan checkbox is ticked on acceptance.
- WP2 adds a state schema and the "find my marker comment" helper (author check included); a unit test covers a forged marker from another user.
- Risk: the maintainer can edit the bot's comment and corrupt state; invalid state falls back to a fresh run rather than failing.
- Risk: a very large repro may not fit in a comment; then it is truncated with a link to the artifact, which may expire.
