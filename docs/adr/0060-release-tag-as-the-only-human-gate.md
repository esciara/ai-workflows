# ADR-0060 · Release tag as the only human gate

- Status: Accepted (2026-11-15, maintainer)
- Date: 2026-11-15
- Deciders: maintainer
- Alias: `D60`
- Amends: [ADR-0051](0051-maintainer-gates-up-front-and-auto-merge-on-green.md) (gates up front, CODEOWNERS exceptions, `verdict` as a required check), [ADR-0053](0053-merge-gate-needs-the-maintainer-only-when-there-is-a-reason.md) (points 1 and 2: `verdict` and the ruleset as the merge gate)
- Supersedes: [ADR-0055](archive/0055-verdict-check-states-before-a-review-exists.md) (`verdict` states no longer gate; withdrawn by the maintainer 2026-11-15)

## Context

ADR-0051 moved the maintainer's review to the front (spec text and acceptance tests approved as PR reviews) and let other PRs auto-merge on green; ADR-0053 and ADR-0055 made `verdict` a required check that passes on `ai-review: merge` or on the maintainer's approval of the head commit. In use, the maintainer is still on the merge path of many PRs: every PR touching a CODEOWNERS path (spec, e2e tests, workflows, guard and policy files), every `human-review` verdict, every edit to an approved `tests/e2e/test_wp*.py`, and PRs held by unresolved Workflow A threads. Each new push dismisses the approval, so the same PR can need several approvals, and PRs wait for the daily batch.

What reaches users is not `main` but a release: target repos pin a tagged SHA ([ADR-0040](0040-code-ref-and-pinning-consolidated.md), install guide). The maintainer decided (2026-11-15) to put their one review there.

Scope: this repo's development process only. The product is unchanged: in target repos agents never merge and a human always presses Merge (spec, CLAUDE.md hard rules).

## Options considered

- Keep ADR-0051/0053/0055 (per-PR gates): a human sees owned paths before they land; but the maintainer stays on the merge path of most PRs, approvals are dismissed by each push, and work waits for the batch.
- Per-PR gates only on a narrower path set: fewer asks; but still per-PR, per-push approvals, and the same waits on the paths that matter most.
- No human gate at all (tags cut by agents): fastest; but nothing human checks what ships to target repos.
- Release tag as the only human gate (chosen): PRs merge on green with no approval; the maintainer reviews once per release, on the exact commit that target repos will pin, with the evidence gathered for that commit.

## Decision

Decided by the maintainer on 2026-11-15.

1. **The tag is the gate.** PRs on this repo merge on green (GitHub auto-merge, rebase, enabled by the App) without the maintainer approving them. The maintainer creates a `v*` tag only after reviewing a release-candidate report for one commit of `main`:
   - the e2e results for that commit (point 2), with run IDs;
   - the diff since the last tag of the release-review paths: the maintainer's base list `tests/e2e/`, `docs/spec.md`, `.github/workflows/`, plus the security-boundary files this ADR's Consequences flag as otherwise unreviewed: `scripts/aiwf/policy.py`, `tests/test_workflow_policy.py`, `scripts/dev/` (guard-bash, `as-*`), `scripts/aiwf/devguard.py`, `.claude/settings.json`, `templates/`, and the ADR-0037 sandbox and scrub code once it lands. This list is the single source; CLAUDE.md points here;
   - the advisory Workflow A findings on the PRs merged since the last tag, and what happened to each (fixed in a commit, won't fix with the reason, or still open).
   Not a full code diff. Only the maintainer creates, moves or deletes `v*` tags (tag ruleset, Transition step 1).
2. **E2e on `main`.** Per slice, the e2e suite runs against `main` HEAD after the slice's PRs merge; that commit is the candidate that gets tagged. A red e2e is fixed forward on `main` (new PRs, merged on green) and the suite runs again on the new HEAD before any tag. E2e runs on WP branches while building stay useful but are advisory.
3. **Workflow A is advisory on this repo.** It still reviews every PR, labels it and opens threads; agents still reply to and resolve every thread (CLAUDE.md). Its verdict and unresolved threads no longer block merge; they feed the findings list of point 1.
4. **Unchanged.** Agents never merge directly (only `--auto`), never approve, never create or move tags; the App has no administration permission; the ruleset on `main` keeps "pull request required", no force-push, no deletion and the required checks `test` and `gitleaks`. Stop-and-ask items in CLAUDE.md (policy-test failure, new ADR, relaxing a hard rule or security boundary, irreversible actions) still go to the maintainer. No hard rule changes.

Why: the maintainer reviews once, on what ships, with the evidence for that exact commit; routine work stops waiting on per-PR, per-push approvals; target repos only ever pin reviewed commits.

## Transition (in this order)

1. Tag ruleset on `refs/tags/v*` (maintainer, now; tightening only): restrict creation, update and deletion; bypass list the maintainer only (not the App, not GitHub Actions).
2. This ADR and the matching CLAUDE.md update (this PR).
3. CODEOWNERS PR (separate, later): removes the maintainer-review requirement for the ADR-0051 exception paths (with `tests/test_codeowners.py`). It touches `.github/CODEOWNERS`, so it is the last PR that waits for the maintainer under the old rule.
4. Ruleset `main` (maintainer): drop `verdict` from the required checks and untick "Require conversation resolution before merging"; keep the rest as in point 4.
5. Peer sessions (`aiwf-review`, `aiwf-issues`, `aiwf-checkpoint`) reload CLAUDE.md.

Until step 4 is done, GitHub still enforces the old gates (code-owner review, `verdict`, resolved threads) and they are met as before.

## Follow-ups (own PRs, not this one)

- `.github/CODEOWNERS` and `tests/test_codeowners.py` (Transition step 3).
- `verdict` job in `.github/workflows/ai-review.yml`: once not required, decide whether it stays (red now means "listed for the tag review", not "blocked"), turns into a warning, or is removed on this repo.
- Optional: a `scripts/dev/` helper that builds the release-candidate report (diffs since the last tag, findings and their outcome from the merged PRs' threads).
- `known-issues.md` entries tied to the old gate (e.g. the `verdict` approval rule assuming a personal repo) are reviewed when step 4 is done.

## Consequences

- The maintainer's review moves from many PRs to one report per release. Routine PRs, and PRs that used to need an approval (spec, e2e tests, workflows, guard and policy files), merge on green.
- Risk: `docs/spec.md` and `tests/e2e/test_wp*.py` edits land unreviewed and steer later work until the next tag review. A wrong spec or a weakened test can be built on for a whole slice; the tag review catches it late, and the fix is forward, on `main`.
- Risk: `main` holds unreviewed code. Whatever uses `main` directly runs it: this repo's own Workflow A caller (it calls main's copy, with `CLAUDE_CODE_OAUTH_TOKEN`), the playground's normal caller (`@main`), and new installs copying `templates/caller.yml` from `main`. Target repos that pin a tag are unaffected. `templates/` is in the release-review diff (point 1), and the install guide's step "check the SHA against the release list" also protects new installs from a wrong template pin.
- Risk: files outside the reviewed diff carry security boundaries: `scripts/aiwf/policy.py` and `tests/test_workflow_policy.py` (enforce the hard rules on workflow YAML), `scripts/dev/guard-bash`, `scripts/dev/as-*`, `scripts/aiwf/devguard.py`, `.claude/settings.json`, and the ADR-0037 sandbox and scrub code. Once CODEOWNERS no longer covers them, an agent change to them merges unreviewed; it is seen at the next tag review because these files are in the release-review diff (point 1), which extends the maintainer's three decided paths for consistency with this risk. The CODEOWNERS PR (step 3) may still keep some of them owned; until then they stay owned.
- Risk: the `review` job on this repo holds `contents: write` (resolving threads, ADR-0057), so its token can push to any unprotected branch, including open PR branches. It runs no agent and no PR code, and `main` stays protected by "pull request required". A push made with `GITHUB_TOKEN` starts no workflow, so `test` and `gitleaks` would not run on the new head and the PR would not auto-merge. Tags are covered by the tag ruleset (step 1), which the token cannot bypass.
- Verdict semantics change on this repo: `ai-review: merge`, `changes-requested` and `human-review` become advisory. A PR can merge before Workflow A finishes or with a red `verdict` (ADR-0055's explained red now reads "waiting for maintainer approval" on PRs that merge anyway) until the `verdict` follow-up. Findings that arrive after merge are fixed forward and appear in the findings list. In target repos nothing changes: the verdict and the human Merge stay as specified.
- ADR-0053 points 3 to 6 (configurable linked issue, 400-line split, e2e run-ID rule, devguard wording) stay; the e2e run-ID rule now only shapes an advisory verdict.
- Once all transition steps are done, a consolidated ADR may supersede ADR-0051 and ADR-0053; they stay live until then because the old gates are still enforced.
