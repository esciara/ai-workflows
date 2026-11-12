# ADR-0051 · Maintainer gates up front; PRs on this repo auto-merge when green

- Status: Accepted (2026-11-12, maintainer)
- Date: 2026-11-12
- Deciders: maintainer
- Alias: `D51`
- Amends: [ADR-0031](0031-agents-act-as-their-own-github-app-main-protected-by-a-ruleset.md) ("the maintainer approves and merges"; the ruleset on `main`)

## Context

Every PR on `esciara/ai-workflows` waits for the maintainer to approve and merge it ([ADR-0031](0031-agents-act-as-their-own-github-app-main-protected-by-a-ruleset.md), CLAUDE.md "always does the merges"). Most of that review comes after the work is done, when the cheap moment to steer (what to build, how we prove it works) has passed. PRs pile up (e.g. #63, #79 waited days), branches go stale and need rebases, and each rebase needs a fresh approval (last-push rule).

The maintainer agreed in principle (2026-11-12) to move their review to the front: approve what to build and how it is proven, then let green PRs merge on their own. This changes who may merge on `main` and the ruleset that enforces it, a security boundary set by ADR-0031, so it is an ADR and not only a CLAUDE.md process edit.

Scope: this repo's development process only. The product is unchanged: in target repos, agents never merge and a human always presses Merge (spec, Workflow A; CLAUDE.md hard rules).

## Options considered

How normal PRs reach `main`:

- Status quo, maintainer reviews and merges every PR: strongest human check; but late, slow, and the main source of stale branches and rebases.
- Up-front gates plus auto-merge on green: the maintainer steers where it matters (spec, acceptance tests) and is not on the merge path for routine PRs; but AI code is reviewed by AI (Workflow A) before it lands.
- Auto-merge on green with no up-front gates: fastest; but nothing human checks what is built or how it is proven, so a wrong test can certify wrong code.

How the exception paths (below) are detected deterministically:

- (a) CODEOWNERS listing the exception paths with the maintainer as owner, plus "Require review from Code Owners" in the ruleset, general required approvals set to 0: native GitHub, enforced at merge time, auto-merge simply waits for the maintainer's approval on those PRs, and the maintainer can pre-approve; but CODEOWNERS is path-based, so it cannot tell an assertion change from a fixture-data change in the same test file.
- (b) A required status check that fails when the diff touches an exception path: also deterministic; but a failing required check blocks everyone, so it needs an override (a label or re-run) that the App could also trigger, unless the check reads the maintainer's approval, which rebuilds (a) by hand.
- (c) Agents skip `--auto` on those PRs by instruction: no setup; but it is a "must remember" rule, not enforcement.

Recommendation: (a). (b) rebuilds what GitHub already does; (c) is not deterministic.

## Decision

- **Gates up front.** Per feature or WP, before build, the maintainer approves (1) the spec text and (2) the acceptance tests, i.e. the Done-when assertions in `tests/e2e/test_wp<N>.py`. Both arrive as PRs touching CODEOWNERS paths (`docs/spec.md`, `tests/e2e/test_wp*.py`), so the approval is a GitHub review, not a chat message. For a stop-WP (CLAUDE.md), the plan stop becomes this gate. These two gates replace the maintainer's per-PR merge review for normal PRs.
- **Auto-merge.** A PR on this repo merges automatically (GitHub auto-merge, rebase, enabled by the agent App with `scripts/dev/as-agent gh pr merge --auto --rebase`) when all are green:
  - the `test` check (unit and policy tests) and `gitleaks`;
  - for a WP PR, the WP's e2e acceptance test, with its output and run IDs in the PR description;
  - Workflow A, dogfooded on this repo, giving the `ai-review: merge` verdict, exposed as a required check (see Maintainer setup).
  Docs-only and test-only PRs follow the same rule (no e2e for them).
- **Exceptions, still reviewed by the maintainer** (detected by option (a), CODEOWNERS):
  - workflow `permissions:` and any workflow file: `.github/workflows/`, `.github/actions/`;
  - secrets handling and the Rule-of-Two and sandbox boundaries of [ADR-0037](0037-command-running-agents-sandbox-scrub-and-trusted-gate.md): the files implementing them (listed in CODEOWNERS when the follow-up PR writes it, e.g. the sandbox and scrub scripts);
  - guard hooks and identity scripts: `scripts/dev/guard-bash`, `scripts/dev/as-*`, `.claude/settings.json`;
  - policy tests: `tests/test_workflow_policy.py`;
  - the spec and acceptance tests: `docs/spec.md`, `tests/e2e/test_wp*.py` (this is gate (1) and (2), and also catches any assertion or Done-when change after approval);
  - CODEOWNERS itself: `.github/CODEOWNERS`.
  The ruleset is changed only by the maintainer (the App has no administration permission).
- **Batching.** Whatever still needs the maintainer (gates, exception PRs, new ADRs) is collected and asked for at most once or twice a day, in one list. The maintainer may pre-approve an exception PR; GitHub then merges it when the checks pass, as long as no new commit is pushed (stale approvals are dismissed).
- **Sessions.** Parallel sessions: `aiwf-orch` (orchestrator), `aiwf-review` (phase 1, Workflow A in use), `aiwf-issues` (phase 2, Workflow B), `aiwf-checkpoint` (checkpoint reviews).
- **Checkpoints.** Every 3-4 merged WPs, a whole-codebase review (architecture, duplication, drift from the spec, refactor candidates) is written up for the maintainer. New WP work stops until the maintainer agrees on the refactor list.
- [ADR-0031](0031-agents-act-as-their-own-github-app-main-protected-by-a-ruleset.md) still holds except: "the maintainer approves and merges" becomes "the App enables auto-merge; GitHub merges when the ruleset is satisfied", and the ruleset changes as in Maintainer setup. Agents still never call a direct merge (`gh pr merge` without `--auto`) and never approve.

Why: the maintainer's attention goes to what to build and how it is proven, where a human adds most; routine PRs stop waiting; GitHub, not instructions, still decides what merges.

## Maintainer setup

Takes effect only after this ADR is accepted and the follow-up PRs below have merged. In order:

1. Merge the follow-up PRs: CODEOWNERS, the Workflow A caller and verdict check on this repo, the `guard-bash` change.
2. Repo Settings, General, Pull Requests: tick "Allow auto-merge". Keep only "Allow rebase merging".
3. Ruleset `main` (Settings, Rules, Rulesets): in "Require a pull request before merging", set required approvals to 0, tick "Require review from Code Owners", keep "Dismiss stale pull request approvals when new commits are pushed" and "Require approval of the most recent reviewable push". Bypass list stays empty.
4. Same ruleset, "Require status checks to pass": keep `test`, add `gitleaks` and the verdict check (name set by the follow-up PR, e.g. `AI workflows / verdict`), source GitHub Actions.
5. Check: an App PR touching only `docs/` with green checks merges by itself; an App PR touching `scripts/dev/guard-bash` waits for your approval; your approval on it lets it merge.

The App needs no new permission: enabling auto-merge needs pull requests write and contents write, which it has ([ADR-0031](0031-agents-act-as-their-own-github-app-main-protected-by-a-ruleset.md)). Verify step 3 on the repo: GitHub documents code-owner review as required when owned files change; that it still applies with 0 general approvals is to be confirmed by step 5.

## Follow-ups (own PRs, not this one)

- `.github/CODEOWNERS` with the exception paths, owner `@esciara`.
- Workflow A on this repo: a caller workflow here (like `templates/caller.yml`, review jobs only) plus a `verdict` job in the same workflow that `needs` the review and fails unless the verdict is `ai-review: merge`. It must live in the same run: labels added with `GITHUB_TOKEN` do not trigger new workflow runs, so a separate `on: labeled` check would never fire. This PR touches `.github/workflows/`, so it is itself an exception PR.
- `scripts/dev/guard-bash`: allow `gh pr merge --auto --rebase` through `as-agent`, keep blocking direct merges and approvals (exception PR).

## Consequences

- Routine PRs merge without the maintainer; the maintainer reviews specs, acceptance tests, exception PRs and checkpoint reports, batched once or twice a day.
- Decided (maintainer, 2026-11-12): every edit to `tests/e2e/test_wp*.py` after approval goes to the maintainer through CODEOWNERS, including plumbing-only edits (waits, run selection, fixture data); path rules cannot tell them apart. These edits are batched, and pre-approval is possible.
- Risk: AI reviews AI code. Mitigations: the tests that prove a WP are human-approved before build; Workflow A's verdict is a required check; security-relevant paths always need the maintainer; checkpoints catch drift and duplication that per-PR review misses.
- Risk: the e2e result is reported by the agent in the PR description, not a GitHub check (e2e runs on this machine against the playground). Workflow A reads the description; a WP PR without e2e output and run IDs should not get `ai-review: merge`. Accepted for now; an e2e check in CI is a possible later change.
- Risk: e2e helpers (`tests/e2e/conftest.py`, `tests/e2e/playground.py`) are not owned, so a change there could weaken a test without review. Accepted; checkpoints review them. Add them to CODEOWNERS if this bites.
- Workflow A becomes a merge gate on its own codebase: a regression in Workflow A can block or wrongly pass PRs here. A blocked PR falls back to the maintainer, who can approve and merge or fix Workflow A.
- Until the setup steps are done, the current rule (maintainer approves and merges) stays in force.
