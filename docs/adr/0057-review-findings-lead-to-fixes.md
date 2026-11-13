# ADR-0057 · Review findings lead to fixes

- Status: Proposed
- Date: 2026-11-13
- Deciders: maintainer
- Alias: `D57`
- Amends: [ADR-0032](0032-workflow-b-runs-workflow-a-on-its-own-fix-prs.md) (what B does with Workflow A's review of its fix PR), [ADR-0053](0053-merge-gate-needs-the-maintainer-only-when-there-is-a-reason.md) (one more dev-process `human-review` reason next to point 5)

## Context

Review findings do not reliably lead to fixes, on this repo's own PRs or on PRs Workflow A reviews:

- Dev PRs on this repo are opened without an independent review first. Workflow A is the first reviewer, so its findings arrive after push, and each round costs a full A run. B5 already has the pattern we want (implementer, fresh-context adversarial reviewer, 3-round cap, draft on failure), but the dev sessions do not use it.
- `ai-review: merge` allows open `should-fix` and `nit` findings (spec, verdict rubric). PR #85 auto-merged with an open A thread. The ruleset on `main` now has "Require conversation resolution" on (`required_review_thread_resolution: true`, checked 2026-11-13 with `gh api repos/esciara/ai-workflows/rulesets`); PR #80 was blocked by unresolved threads. So on this repo an open thread already blocks the merge; nothing yet closes the loop.
- Spec step 9 marks the last run's findings resolved or still open in the summary comment, but never touches the inline threads. A fixed finding keeps its thread open until someone resolves it by hand, so with conversation resolution on, every A thread needs a human or agent click even after the fix.
- CLAUDE.md (Review threads) already asks dev agents to reply to and resolve every thread. That is a "must remember" rule with no check.
- B6 hands B's fix PR to Workflow A (ADR-0032), but A's findings go nowhere: the maintainer gets the PR with A's threads open, even when B still had rounds left to fix them.
- Third-party PRs (human or fork) get A's findings and `suggestion` blocks; whether an agent should also fix them is not decided.

## Options considered

Dev PRs on this repo, pre-push review (part 1):

- CLAUDE.md line only: one line; forgotten silently, nothing checks it.
- `guard-bash` blocks `as-agent gh pr create` and `gh pr ready` unless a local record of a review of HEAD exists: deterministic, local; but agent sessions only, the record is forgeable, it adds state and a CODEOWNERS change, and it duplicates a server check.
- Workflow A dev-mode check: a PR whose description has no `## Pre-push review` block gets `ai-review: human-review` ("no pre-push review"), only where `linked_issue: issue-or-plan-ref` (chosen): deterministic, server side, ~15 lines next to ADR-0053 point 5 (`wp_no_run_ids`), target repos unaffected; the block is forgeable (a deliberate lie, not forgetting), and a missing block sends the PR to the maintainer rather than blocking it outright.
- Same, but the block's reviewed SHA must equal the head SHA: stricter; every thread-fix push needs a full new review loop, churn for little gain.
- `/code-review` skill instead of a dedicated loop: exists today; generic bug finder, not aware of the plan's Done when, the spec or the hard rules, and `--fix` runs in the session's own context, so the review is not independent. Kept as an optional extra in round 1, not the loop.

Workflow A threads (part 2):

- Rely on the ruleset's conversation resolution alone: already on here, native, deterministic; but every fixed A thread still needs a manual resolve, so A's own findings become merge friction.
- A replies to and resolves its own inline threads when step 9 finds the finding fixed, and the summary shows "N threads open" (chosen): deterministic once step 9 has judged, same `pull-requests: write` the publish job already has; A only touches threads it opened; needs the GraphQL `resolveReviewThread` mutation to work with `GITHUB_TOKEN` (to verify on the playground).
- Maintainer's idea, the `verdict` check text shows "N unresolved threads" until 0: makes the open count visible in the merge box. As a gate it would go stale: resolving a thread starts no workflow run that we know of (whether `pull_request_review_thread` can trigger Actions is to verify), so `verdict` would stay red after the last thread is resolved until the next push or review. Chosen as information only (see Decision 3); the ruleset stays the gate.
- New label `ai-review: threads-open`: visible; but duplicates the ruleset and the summary count, and a new label means spec and label-set churn.

Workflow B fix PRs (part 3):

- Keep ADR-0032 as is: A's findings go to the maintainer; simple; but B hands over PRs with fixable blocking findings while rounds remain.
- A's findings feed back into B5 inside the same 3-round cap (chosen): when the nested A run gives `changes-requested` and B5 has rounds left, the implementer gets one more round on A's schema-validated findings JSON, B pushes and reruns A; cap reached → B5's existing escalation. No new Rule-of-Two leg: the implementer already reads untrusted issue text and holds the model token under ADR-0037; A's findings add no secret and no write path.
- Separate cap for A-driven rounds: more fixes; but more model spend and a longer run per issue, and the maintainer reasons about one cap more. Rejected.

Third-party PRs (part 4):

- Auto-fix on fork PRs: untrusted code plus the model token plus a push right is all three Rule-of-Two legs; `GITHUB_TOKEN` cannot push to a fork; the spec reads fork code as text only. Rejected.
- Auto-fix on same-repo human branches: an agent takes over someone else's branch (the spec's own logic: a maintainer push to `ai-fix/*` makes the branch theirs). Rejected.
- No auto-fix; authors get A's findings and one-click `suggestion` blocks (WP3) (chosen). A maintainer-only `/fix-review` that opens a separate `ai-fix/pr-<n>` PR onto the author's branch, under ADR-0037, may be proposed after slice 4 as its own ADR.

## Decision

1. **Pre-push review loop on this repo's dev PRs.** A repo-only skill `.claude/skills/review-loop/SKILL.md` runs before a PR is opened or marked ready:
   - Up to 3 rounds. Each round: implement (round 1) or address findings (rounds 2–3), each finding with a disposition (`fixed <sha>`, `won't fix: <reason>`, `already covered: <where>`); `pytest` green (a policy-test failure is a stop, not a round); then a review by a new subagent each round (never a fork, never the previous reviewer), opus model.
   - The reviewer gets only: `git diff <base>...HEAD`, the plan row's Done when, the spec sections touched, CLAUDE.md's hard rules, the B5 checklist (symptom vs cause, edge cases, regressions, weakened or deleted test, scope creep) and a repo checklist (permissions, secrets, Rule of Two, CODEOWNERS paths); rounds 2–3 also get the previous findings and their dispositions, never the session's reasoning. It returns `{verdict: approve|reject, findings: [{severity: blocking|should-fix|nit, file, line, claim, evidence}]}`; the skill checks the shape and re-asks once on bad JSON.
   - Exit: `approve` with tests green → push, open the PR ready for review. Round 3 still `reject` → push, open as draft (no `verdict`, cannot merge, ADR-0055), list the open findings, add the PR to the maintainer's batch.
   - The skill writes a `## Pre-push review` block for the PR description: `Rounds: N · Result: approve|escalated · Reviewed head: <sha>`, plus one line per round (finding counts by severity, dispositions).
   - The reviewer's prompt lives in `prompts/adversarial-reviewer.md`, so WP9's B5 reviewer reuses it.
   - After push, the same skill waits for Workflow A's run and applies CLAUDE.md's thread rule; a new blocking finding from A gets one fix and one fresh review of that change, outside the pre-push cap.
   - Enforcement: Workflow A gives `ai-review: human-review` with the reason "no pre-push review" to a PR whose description holds no `## Pre-push review` heading. Deterministic, in `scripts/aiwf/review.py`, only where `linked_issue` is `issue-or-plan-ref` (this repo), any PR kind (docs-only PRs too: one cheap round, no exemption logic). Presence of the block only, not its SHA.
   - CODEOWNERS adds `/.claude/skills/`, so a weakened skill does not auto-merge; `tests/test_codeowners.py` follows. `scripts/aiwf/review.py` stays unowned, as for ADR-0053 point 5.
2. **Workflow A closes its own fixed threads.** In step 9, for each finding of the last run that the verify pass marks resolved and that has an inline thread opened by A, the orchestrator replies in that thread (`resolved in <short sha>: <reason>`) and resolves it. Still-open findings keep their thread open, with no reply. A never replies to or resolves a thread it did not open. The summary comment's "Since last run" line also says "N threads open" (A's and others' unresolved threads on the PR at review time). The install guide recommends turning on "Require conversation resolution" on target repos.
3. **Open threads in the `verdict` text, not as its gate.** The `verdict` job adds "N unresolved threads at <short sha>" to its step summary and to the description of the (non-gating) `verdict` commit status of ADR-0055. It does not change the job's result: the ruleset's conversation resolution is the gate, and it is always current, while the count is only as fresh as the last `verdict` run.
4. **Workflow A's findings feed Workflow B's fix loop.** On an `ai-fix/*` PR, when the nested A run (ADR-0032) gives `ai-review: changes-requested` and B5 has rounds left (`fix_rounds`, shared with B5's own reviewer), the implementer runs one more round with A's findings as validated JSON from A's output (never thread or comment text), B pushes, and reruns A. When the cap is reached with A still at `changes-requested`, B5's escalation applies (draft PR, `fix: needs-maintainer`, assignment, review request). A `human-review` verdict (e.g. no CI on B's PR, ADR-0032) is not fed back; it goes to the maintainer as today.
5. **No auto-fix on third-party PRs.** Neither workflow pushes to a PR branch it did not create. Fork and human-authored PRs get findings and `suggestion` blocks only.

Why: findings become fixes before push on our own PRs (cheaper than A rounds), A's fixed findings stop costing manual resolves, B uses A's independent review instead of handing fixable work to the maintainer, and no part adds a write path, a secret or a reader of untrusted text that was not already there.

## Consequences

- Dev PRs gain a deterministic `human-review` reason. A PR opened without the block waits for the maintainer; adding the block (edit of the description) and a new A run (`/review` or a push) clear it.
- The block is forgeable by a session that lies; accepted, the check targets forgetting, and the maintainer reads the block on exception PRs.
- The maintainer's own PRs on this repo also need the block (or go to `human-review`); see open question in the PR.
- Pre-push review costs one to three opus subagent runs per PR; A runs fewer rounds in exchange.
- A's thread replies and resolves add GraphQL calls to the publish job; the policy tests need no new permission if `pull-requests: write` covers `resolveReviewThread` (to verify on the playground in the WP's e2e).
- B's run per issue grows by up to the remaining rounds of A runs; the per-run time budget (ADR-0050) must cover it.
- Spec edits: A step 9, "How it is sent", the review template's "Since last run" line, B5 and B6 (see the ADR's PR). On acceptance, ADR-0032 and ADR-0053 get an `Amended by: ADR-0057` line.

## Follow-ups (own PRs, after acceptance)

- WP17 (plan): review-loop skill, `prompts/adversarial-reviewer.md`, A dev-mode check, CLAUDE.md line, CODEOWNERS `/.claude/skills/` (exception PR).
- WP18 (plan): A replies to and resolves its own fixed threads; "N threads open" in the summary and the `verdict` text; install guide recommendation.
- WP19 (plan, slice 4, after WP10): A's findings back into B5.
