# ADR-0035 · Workflow B classifier inputs, dedup and already-fixed check

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D35`

## Context

B1 (`docs/spec.md`, Workflow B) must label the issue class, spot duplicates and spot bugs already fixed on the default branch. The spec does not say what the classifier sees or how its references are checked. The classifier reads untrusted issue text, so it gets no write tools and no secrets (Rule of Two, ADR-0018); its job holds `CLAUDE_CODE_OAUTH_TOKEN`, so it must not get file tools either (ADR-0034).

## Options considered

- (a) Recent window: the classifier gets the last 100 open and 100 closed issues and the last 50 commits inline. Rejected: misses older issues and older fixes, and ignores the version the reporter runs.
- (b) Agent with Read, Grep and Glob on a checkout, searching issues and history itself. Rejected: file tools in a job holding the OAuth token can read it (ADR-0034), and an exploring agent costs far more tokens per issue.
- (c) Two tool-less agent passes with deterministic candidate gathering between them. Chosen.

## Decision

- Pass 1 (`prompts/extractor.md`, `schema/extractor.json`): no tools, issue text inline as untrusted data. Returns `reported_version` (or null), up to 6 `search_phrases` (error messages, key terms) and up to 10 `file_paths` named in the report.
- Orchestrator code (`aiwf triage-candidates`, read-only token) validates pass 1's JSON, then gathers:
  - Duplicate candidates: GitHub issue search over all issues of the repo, open and closed, any age, one query per phrase plus the title. Phrases are reduced to plain words (no qualifiers, quotes or operators). Results are deduplicated, ranked by the number of phrases that found them, exclude the issue itself, PRs and issues closed as not planned, capped at 20.
  - Possible fixes: commits and merged PRs between the reported version's tag and the default branch. The version maps to a tag by name (with or without `v`), then by version number (`1.2` = `v1.2.0`). Inputs are commit subjects, merged-PR titles, "fixes #N" references and changed file paths matched against the files the report names; no code content is read. Ranked by file match and by a "fixes" reference to the issue or a duplicate candidate, then newest first; capped at 30 commits and 20 PRs.
  - Fallback: version unknown or no matching tag gives the range since the latest release, or the last 50 commits when there is no release, with range confidence `low`.
- Pass 2 (`prompts/classifier.md`, `schema/classifier.json`): no tools, issue and candidates inline. Returns `type` and `confidence`, optional `duplicate_of` {number, confidence} and `possibly_fixed_by` {commit or PR, confidence}.
- Publish: references are checked before linking (the duplicate is another issue, open or closed as completed; the commit is on the default branch; the PR was merged into it). A duplicate with high or medium confidence gets `triage: duplicate`; a low-confidence one is only mentioned. A fix is only "possibly fixed by X" in the comment, capped at low confidence when the range was a fallback; it adds no label, and B2's reproduction (WP6) confirms it. WP5 never closes. Low class confidence adds `triage: needs-human`. `/retriage` behaviour is unchanged.

## Consequences

- Duplicates and fixes of any age are found, and the fix range follows the version the reporter runs.
- Two agent calls per issue instead of one, each small and tool-less; a few search API calls per issue (well under the 30 per minute limit).
- Deviation from the spec, approved by the maintainer: "already fixed: label `triage: duplicate`, stop" becomes "possibly fixed" without a label, so B2 still reproduces and confirms or rejects it; a confirmed fix is B2's to report. `docs/spec.md` (B1) is amended in the same PR.
- Issue search depends on GitHub's search index, which can lag a few seconds behind a newly created issue.
