# AI Workflows — Implementation Plan

Exported Oct 30, 2026 from the online doc: https://claude.ai/artifact/RC4m7kMMMNhMpo5cLaRXAV

## Approach

| **TL;DR** — Build the PR Review & Bug-Fix spec (`docs/spec.md`) in a central `ai-workflows` repo, in vertical slices: each slice takes one feature all the way to in use on a real repo (`esciara/pyteleinfo`) before the next slice starts. Slice 0 cleans up; then Workflow A in use, then Workflow B stage by stage (triage, reproduce and analyse, fix), then contributor mode. Inside a slice, work stays one work package per PR, each proven on the test repo. |
| --- |

- **Where the code lives.** A central repo, `ai-workflows`, holds the reusable workflows, the agent prompts, the orchestrator scripts and the config schema. Each target repo carries only a short caller workflow and `.github/ai-workflows.yml`.
- **Who builds it.** A Claude Code session on your machine, opened in `ai-workflows`, with the spec and this plan in `docs/`. The session works slice by slice, one work package at a time.
- **The loop per work package.** Branch → build → run its check on the test repo → open a PR on `ai-workflows` with the check's evidence → you review and merge → next package. In practice (CLAUDE.md, How to work): the check is unit tests plus 1–2 happy-path e2e scenarios on the test repo, and outside the stop-WPs the session continues without waiting while you review and merge PRs in batches.
- **Source of truth.** The spec says *what*; this plan says *in which order* and *how we know it works*. A conflict between the two is a question for you, not a guess.
- **What you do by hand.** Creating repos, adding secrets, branch protection and chat webhooks. Tokens never pass through the agent.

## Dependency graph

| **TL;DR** — WP0 and WP1 unlock everything; the technical dependencies below still hold, but the work order is by slice (see Slices), not by the longest chain. A and B meet only at WP10 (B's PR is reviewed by A) and WP13. |
| --- |

[Diagram in the online doc: dependency graph · 15 work packages; predates the slices]

The longest chain runs through Workflow B: WP0 → WP1 → WP5 → WP6 → WP8 → WP9 → WP10. Guardrails hang off WP1; notification events are wired by each slice for its own events.

## Work packages

Checkpoint items CP8-CP15 are tracked in beads (`bd`) with label `checkpoint`.

| **TL;DR** — 17 packages, kept with their IDs for history; the Slice column says which slice each belongs to. Each has a check you can run on the test repo; a package is done only when its check passes and the evidence (run links, screenshots of labels and comments) is in its PR. |
| --- |

| ID | Slice | Package | Depends on | Delivers | Done when | Status |
| --- | --- | --- | --- | --- | --- | --- |
| WP0 | base | Repo bootstrap | — | Repo layout, `CLAUDE.md`, config schema + validator, caller template | Caller in the test repo loads and validates `.github/ai-workflows.yml` in a green run | done |
| WP1 | base | Shared runtime | WP0 | Reusable job running Claude Code on `CLAUDE_CODE_OAUTH_TOKEN`; orchestrator that applies agents' JSON outputs via `gh api`; label bootstrap; command parser with permission check | A command from a maintainer is accepted, from a non-maintainer is refused; all labels exist | done |
| WP2 | 1 | A · core review | WP1 | Steps 1–7 and 9: context, CI wait, risk tier, 4 passes, verify, rubric, summary comment with hidden marker, verdict label | Dummy PR gets one comment + one label; a new push updates the same comment | done |
| WP2a | 1 | A · context, CI wait, one pass, summary + label | WP1 | Context job, CI wait + risk tier, pending label, one pass, rubric, summary comment by marker, verdict label swap; usage measured | Dummy PR gets one comment + one label; a new push updates the same comment (`tests/e2e/test_wp2.py`) | done |
| WP2b | 1 | A · 4 passes, verify, severity, step 9 | WP2a | 4 passes as a matrix, verify (refute) pass, severity tags, resolved / still-open matching (step 9); real 5-agent usage | WP2a's Done when still holds with 4 passes and verify (`tests/e2e/test_wp2.py` still passes) | done |
| WP3 | 1 | A · placement + formal review | WP2 | Inline vs general rule, `suggestion` blocks, one GitHub review, never Approve | Seeded-bug PR gets an inline comment and Request changes; a nit on a low-risk path stays in the summary | done |
| WP4 | 1 | A · fork PRs | WP2 | `fork_prs: on-command` handling | Fork PR is not reviewed until a maintainer comments `/review` | done |
| WP5 | 2 | B1 · classify | WP1 | Classifier agent, dedup, already-fixed check | 3 test issues get `type: bug`, `feature`, `question`; a duplicate gets `triage: duplicate` | done |
| WP6 | 3 | B2 · reproduce | WP5 | Sandboxed reproducer, repro test stored, needs-info comment, reply restarts B2 | Clear bug → `triage: reproduced` + test; vague bug → `triage: needs-info`; after `/reproduce`, the reporter's reply reruns it | done |
| WP7 | 3 | B2 · reporter silence | WP6 | Day-4 ping job, `actions/stale` workflow, `keep-open`; one reusable workflow called from the caller's daily schedule (spec: Reporter silence); playground slot callers get a `workflow_dispatch` that runs it and the e2e config shortens `reporter_silence_days` to minutes (maintainer-merged playground PR) | With days shortened in config, ping, stale and close happen in order; a reply resets them; `keep-open` exempts (`tests/e2e/test_wp7.py`) | done |
| WP8 | 3 | B3–B4 · analyse + ask | WP6 | Analyst after a reproducing B2 (no commands, no file tools, code put into its prompt); one analysis comment by marker with links and risk tier built by the orchestrator; `triage: awaiting-maintainer`; `/fix`, `/fix <guidance>`, `/no-fix` (status line, `fix: declined`). `/fix` starting B5 lands with WP9 | Reproduced bug gets one analysis comment and `triage: awaiting-maintainer`; `/fix <guidance>` and `/no-fix` do what the spec says; a non-maintainer's `/fix` changes nothing (`tests/e2e/test_wp8.py`) | in progress |
| WP9 | 4 | B5 · fix loop | WP8 | Implementer + adversarial reviewer, 3-round cap, `ai-fix/*` branch, escalation | Seeded bug fixed in ≤ 3 rounds; a forced failure gives a draft PR, `fix: needs-maintainer`, assignment and review request | todo |
| WP10 | 4 | B6 · PR into A | WP9, WP3 | PR body, `ai-fix` label, A runs on it | One issue goes from opened to a verdict label with no manual step except `/fix` | todo |
| WP11 | 2–4 | Notifications | WP1 | Slack and Telegram senders, the 5 events | Each event sends one message with a working link, on both channels | in progress |
| WP11a | base | Notification senders | WP1 | Slack and Telegram senders + a notify step (ADR-0024) | A `workflow_dispatch` test event sends one message with a working link, on both channels | done |
| WP11b | 2–4 | Notification events | WP11a, WP9, WP12 | Wiring of the 5 events (ADR-0024); split across slices 2–4, each slice wires its own events | Each event sends one message with a working link, on both channels | todo |
| WP11b1 | 2 | Notification: issue triaged | WP11a, WP5 | The spec's "New issue triaged" alert wired into triage (B1), sent to the config's `notify` channels; the notify result line also carries the text sent; playground e2e config sets `notify: slack,telegram` (maintainer-merged playground PR) | A new issue triaged on the playground sends one message naming the issue and its type, with a working link to the issue, on both channels (`tests/e2e/test_wp11b.py`) | done |
| WP12 | base | Guardrails | WP1 | `ai: off`, budgets, `ai: error`, injection reporting | `ai: off` stops a run; a forced crash gives `ai: error` + comment; an injected instruction is reported, not obeyed | done |
| WP12a | base | Guardrails: `ai: off`, `ai: error` | WP1 | `ai: off`, `ai: error` | `ai: off` stops a run; a forced crash gives `ai: error` + comment | done |
| WP12b | base | Guardrails: injection, budgets | WP1 | Budgets, injection reporting | An injected instruction is reported, not obeyed | done |
| WP13 | 5 | Contributor mode | WP3, WP8 | Fork caller guide (level 1); local Claude Code plugin with review and analyse skills (level 0) | Review runs on a branch locally and in a fork, with nothing posted upstream | todo |
| WP14 | 1 | Onboarding kit | WP3, WP15 | Install guide (`docs/install.md`), rights checklist, caller + config templates; first release tag, callers pinned to it (ADR-0040) | A second repo is set up from the guide alone in under 30 minutes (`tests/e2e/test_wp14.py`, plus its manual checklist) | done |
| WP15 | 1 | Per-run usage metrics | WP2 | One JSON line of usage metrics per Workflow A run (spec: Usage per run) | A reviewed PR's run records exactly one metrics line with the run, the PR and each agent's turns, duration and tokens (`tests/e2e/test_wp15.py`) | done |
| WP16 | base | Three e2e slots | WP1 | Per ADR-0056: slots 1–3, each with ref and label `e2e-target-<n>`, caller `caller-e2e-<n>.yml`, branch prefix `e2e/<n>/`; `AIWF_E2E_SLOT=1\|2\|3\|any`; one `flock` per slot (`aiwf-e2e-<n>.lock`); drift guard over the three callers; playground callers and labels in a maintainer-merged playground PR | Three e2e runs execute in parallel on slots 1–3 and the drift test covers the three callers (`tests/e2e/test_wp16.py`, `tests/e2e/test_callers_match.py`) | done |
| WP17 | 1 | Pre-push review loop (dev process) | WP2b | Per ADR-0057 point 1: `review-loop` skill (3 rounds, fresh-context adversarial reviewer, draft on round-3 reject, thread handling after push); `prompts/adversarial-reviewer.md`; A dev-mode check (`linked_issue: issue-or-plan-ref` only): no `## Pre-push review` block → `human-review`; CLAUDE.md line; CODEOWNERS `/.claude/skills/` | Unit tests: a description without the block gives `human-review` with reason "no pre-push review", with it does not, and the check is off with `linked_issue: issue`. On this repo, the next WP PR carries the block and merges without the maintainer when nothing else needs them | todo |
| WP18 | 1 | A · closes its own fixed threads | WP2b, WP3 | Per ADR-0057 points 2–3: step 9 replies to and resolves A's own inline thread for each finding it marks resolved, leaves the others open; "N threads open" in the summary and in the `verdict` text (information only); install guide recommends "Require conversation resolution" | Seeded-bug PR: a fixing push gets A's reply and the thread resolved, the summary says 0 threads open; a non-fixing push leaves the thread open (`tests/e2e/test_wp18.py`) | todo |
| WP19 | 4 | B6 · A's findings back into B5 | WP10, WP18 | Per ADR-0057 point 4: when the nested A run gives `changes-requested` on an `ai-fix` PR and rounds remain (`fix_rounds`, shared with B5), one more implementer round on A's validated findings JSON, push, rerun A; cap reached → B5 escalation | Seeded bug the inner reviewer approves but A blocks: B fixes it in a later round, the final head is not `changes-requested` and A's thread is resolved; with `fix_rounds: 1` the same case gives a draft PR and `fix: needs-maintainer` (`tests/e2e/test_wp19.py`) | todo |

Slice `base` marks shared runtime built before the slices. Rows with a letter (WP2a, WP2b, …) split the WP above them into PRs; the WP's own row keeps the full Done when, and each split's Done when is what its PR proves. Status is one of done, in progress, todo or paused; it is hand-edited, by each WP's own PR.

Open items (hand-edited like the Status column):

- WP14: setup timing of the second repo `esciara/pyteleinfo` (2026-11-13, UTC, from GitHub timestamps): first commit of caller PR #15 at 21:58; #15 merged 22:14 (16 min to a merged caller and config); first working review on test PR #17 about 22:40-22:47 (about 42-49 min after the first commit, includes a pre-existing lint failure fixed by #16, merged 22:44); the GitHub App install and secret steps happened before 21:58 and were not timestamped. Not a clean timed run, so the "under 30 minutes from the guide alone" Done-when is still unproven: it needs a timed run or the maintainer's explicit acceptance. Maintainer accepted "under 30 minutes" as met, 2026-11-14 (install and secret steps untimed). Status `done`.
- CP7b: triage caps for outside authors per ADR-0058 (config keys, check in triage `context`, capped publish, spec and install guide); built in PR #126, unit-tested, no e2e (none in the plan): done when merged.
- WP7: done; gate #147, build #149 and #152, playground #203 merged; e2e passed 2/2 on main cbc3a19, unit 907 passed; live from release v0.2.0.
- WP8: gate PR open (spec B3–B4 text, `tests/e2e/test_wp8.py`). No playground PR needed: the slot callers already pass every issue comment to `triage.yml`. WP9 updates `tests/e2e/test_wp8.py` (its `/fix` then starts B5).
- WP16: single e2e slot (known issue, P1) → three slots per ADR-0056; gate (#105), build (#107) and playground PRs (#127, #130) merged; the maintainer deletes the old `e2e-target` ref after.

**WP11 maintainer setup (chat alerts).** Before WP11 can pass, the maintainer sets these repository secrets on the test repo (and later on each target repo that wants alerts): Slack, create an Incoming Webhook for a channel and store it as `SLACK_WEBHOOK_URL`; Telegram, create a bot with @BotFather, get your chat ID, and store them as `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

## Slices and test setup

| **TL;DR** — Six vertical slices, in order; a slice is done only when its feature is in use on the real repo `esciara/pyteleinfo` (slice 0: merged and e2e green). Everything is tested on a throwaway repo with seeded bugs, plus a fork in my organization and a small tester GitHub App standing in for outsiders, so no second account is needed. |
| --- |

| Slice | Contents | Done when |
| --- | --- | --- |
| 0 · Cleanup | Process simplification (#61, done). Workflow simplification (#62): test hooks out of the product, budgets → time/turn limits (ADR-0050), shared setup action. MED batch: one command parse and drop `/ping`; config settings not used yet marked "not used yet, WPx" in `templates/ai-workflows.example.yml`; one shared `gh` helper module; diagrams in the PR description instead of required per-WP diagrams, and drop the docs-consistency ceremony (`tests/test_docs_consistency.py` and `docs/diagrams.md` remain by choice: it checks ADR links, and the diagrams are hand-maintained, see the file header); B2 for trusted authors only, plus `/reproduce` for outsiders, written into the spec as v1. LOW batch: dev tools moved out of the shipped `scripts/aiwf` package (not done: `devguard.py`, `e2eslot.py` and `acceptance_review.py` still live there); guard-bash false positive on `git worktree add` fixed | Merged, e2e green |
| 1 · Review in use | WP15 per-run metrics (one JSON line per run, moved from slice 0), then WP14 onboarding kit (install guide, rights checklist, templates; callers pinned to a release tag or SHA, not `@main`; first release tag); metrics used to settle the "Usage limits" open point | Workflow A runs on `esciara/pyteleinfo`, set up from the guide alone in under 30 minutes, and the first usage numbers are recorded |
| 2 · Triage in use | B1 (WP5, built) enabled on `esciara/pyteleinfo`, plus its "new issue triaged" notification (part of WP11b) | New issues there get classified and the maintainer gets a chat alert |
| 3 · Bugs reproduced and analysed | Starts when checkpoint items CP8 (aiwf-vpq, shared `aiwf-agent` action) and CP9 (aiwf-5it, rebase #79/WP6, private-repo tarball pattern) are done. WP6 (done), WP7, WP8, plus their notifications (WP11b) | A real bug on `esciara/pyteleinfo` is reproduced, analysed, and the maintainer is asked `/fix` |
| 4 · Bugs fixed | WP9, WP10, plus the remaining notifications (WP11b) | `/fix` gives a reviewed PR with no other manual step |
| 5 · Contributor mode | WP13 | WP13's Done when |

**Test setup** (you create these before WP0):

- **Test repo** `ai-workflows-playground`, public, with a small app and a real test suite. The session seeds bugs into it on purpose, one per WP check.
- **Outsider stand-ins, no second account.** A fork of the playground in `opinionated-digital-center` sends real fork PRs (WP4). A tester GitHub App opens issues, replies as the reporter and tries commands without maintainer status (WP1, WP6, WP7).
- **Your first real repo** `esciara/pyteleinfo` gets Workflow A in slice 1, then Workflow B progressively from slice 2 (triage), one stage per slice.
- **Secrets** on the test repo: `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`), then `SLACK_WEBHOOK_URL` or `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` by WP11.

## Open points

| **TL;DR** — Three things only the build can settle; the session raises each one when it reaches the package concerned. |
| --- |

- [ ] **Sandbox for B2 and B5 (WP6).** The Actions runner is a VM per job; whether that is isolation enough, or whether repro code runs in a container with no network, is decided when WP6 starts.
- [x] **Where run state lives (WP1).** The hidden marker comment carries per-item state; whether a separate store is needed for the session record is decided in WP1. Decided in ADR-0021: no separate store; labels plus the marker comment, with bulky material in artifacts.
- [x] **Usage limits (WP2).** The real usage per reviewed PR on your subscription is measured in WP2, and the per-run budgets in the config are set from it. Slice 1: measured with WP15's metrics lines from the first reviewed PRs on `esciara/pyteleinfo`; the numbers are recorded here. Measured 2026-11-14 on `esciara/pyteleinfo` (aiwf-metrics line, summed over the 5 agents; the `ai-workflows-metrics` artifact matches the log): #17 (no linked issue) verdict human-review, wall 109 s, cost $0.0138 (cache warm, about 318 cache-creation tokens); #19 (no linked issue) human-review, wall 113 s, $0.0841, 1542 output tokens, 16219 cache-read, 16203 cache-creation; #20 (Fixes #18) merge, wall 133 s, $0.0802, 1164 output tokens, 16219 cache-read, 16161 cache-creation. Cost varies about 6x with prompt-cache warmth, not PR size; a review run takes about 2 minutes.
