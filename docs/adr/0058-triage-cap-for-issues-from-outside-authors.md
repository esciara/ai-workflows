# ADR-0058 · Triage cap for issues from outside authors

- Status: Proposed
- Date: 2026-11-13
- Deciders: maintainer
- Alias: `D58`

## Context

On a public repo anyone can open an issue, and every `issues.opened` event runs B1: the `extract` and `classify` agents on the maintainer's Claude subscription (spec, Runtime), whose usage limits are shared with the maintainer's own use. ADR-0050 bounds one run (fixed `--max-turns` and step `timeout-minutes` per agent) but nothing bounds the number of runs: a burst of issues from one account, or from many, spends the subscription with no limit per day or per author. B2 is already gated for outsiders (an outsider's bug waits for the maintainer's `/reproduce`, spec B2), so B1 is the only agent work an outsider can start alone. `ai: off` is per item and `workflows.triage: false` turns triage off for everyone, so neither fits a flood. The first public target repo (esciara/pyteleinfo, slice 2) makes this real; it is checkpoint item 7.

## Options considered

- No cap, document the kill switches (status quo): nothing to build; a flood is noticed only after the usage is spent, and stopping it turns triage off for everyone.
- Outsiders never auto-triaged: issues from authors not in `maintainers` get `triage: needs-human` and wait for `/retriage`; zero outsider spend, but B1 then does nothing useful on a public repo, which is where it matters most.
- Per-author daily cap only: stops one noisy account; many accounts (or one person with several) still have no bound.
- Repo-wide daily cap only: a hard bound on outsider spend per day; one account can use the whole day's quota and starve real reporters.
- Both caps, per author and repo-wide, counted from GitHub's issue list (recommended): bounds the day and the single account; two config keys; setting either to 0 gives the "outsiders never auto-triaged" option per repo.
- Counting through the search API (`is:issue created:>=…`): one call; but the search index lags, so a burst of issues opened together each sees a low count and all get triaged; rejected for the REST issue list, which is consistent.
- Counting from run state (a state file, cache or counter label): exact runs triaged; needs repo-wide state, while run state lives on each item (ADR-0021); rejected.

## Decision

Recommended (pending the maintainer):

1. Two new `limits` keys in the config (ADR-0010): `triage_per_author_per_day` (default 3) and `triage_per_day` (default 20), integers, minimum 0. They apply to issues whose author is not in `maintainers`; maintainers' issues are never capped.
2. The check runs in triage's `context` job (it already has `issues: read`), before any agent: list the repo's issues created in the last 24 hours with the REST issue list (`state=all`, pull requests dropped), keep those from authors not in `maintainers`, and count only issues numbered at or below the current one. The issue is capped when that count is above `triage_per_day`, or the same count for its author is above `triage_per_author_per_day`. Ordering by issue number makes a burst deterministic: the first N issues are triaged, the rest capped, whatever order the runs finish in.
3. Every issue opened counts, whether or not it was triaged (closed, `ai: off`, already capped). This is conservative and needs no state.
4. A capped issue runs no agent. B1 `publish` labels it `triage: needs-human` and posts one sticky bot comment with a fixed text (no agent output, no counts): automatic triage limit reached for today; a maintainer can run `/retriage`. No new label.
5. `/retriage` from a maintainer is never capped: the maintainer chose to spend it.
6. Setting either key to 0 means issues from outside authors are never triaged automatically.

Why: B1 is the only agent work an outsider can start alone; two counts bound both one account and the whole day, the REST list gives a consistent count without new state, and reusing `triage: needs-human` adds no label.

## Consequences

- Implementation (checkpoint item 7b, aiwf-issues): the config schema and its defaults, the check in `scripts/aiwf` with unit tests (under/at/over each cap, maintainer exempt, `/retriage` exempt, pull requests dropped, ordering by number), `triage.yml` gating `extract` and `classify` on the result, the fixed comment in B1 publish, the install guide and example config. It touches `.github/workflows/triage.yml`, the schema and the spec (Per-repo configuration example, Guardrails caps), so it goes to the maintainer (CODEOWNERS).
- One extra paginated REST call per opened issue, on the workflow's `GITHUB_TOKEN`; at the default caps it is one page.
- The window is a rolling 24 hours, not a calendar day.
- A capped issue is not retried automatically when the window frees up; the maintainer reads `triage: needs-human` items or runs `/retriage`.
- A collaborator with write access who is not in `maintainers` is counted as an outsider; the repo adds them to `maintainers` to exempt them.
- A deleted issue (admin only) drops out of the count; GitHub-hidden spam accounts may too. Both only lower the count for issues that are gone.
