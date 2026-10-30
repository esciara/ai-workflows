# AI Workflows — Implementation Plan

Exported Oct 30, 2026 from the online doc: https://claude.ai/artifact/RC4m7kMMMNhMpo5cLaRXAV

## Approach

| **TL;DR** — Build the PR Review & Bug-Fix spec (`docs/spec.md`) in a central `ai-workflows` repo, one work package per PR, each proven on a test repo before the next starts. Workflow A ships first and is useful on its own; Workflow B follows in four steps. |
| --- |

- **Where the code lives.** A central repo, `ai-workflows`, holds the reusable workflows, the agent prompts, the orchestrator scripts and the config schema. Each target repo carries only a short caller workflow and `.github/ai-workflows.yml`.
- **Who builds it.** A Claude Code session on your machine, opened in `ai-workflows`, with the spec and this plan in `docs/`. The session works one work package at a time.
- **The loop per work package.** Branch → build → run its check on the test repo → open a PR on `ai-workflows` with the check's evidence → you review and merge → next package.
- **Source of truth.** The spec says *what*; this plan says *in which order* and *how we know it works*. A conflict between the two is a question for you, not a guess.
- **What you do by hand.** Creating repos, adding secrets, branch protection and chat webhooks. Tokens never pass through the agent.

## Dependency graph

| **TL;DR** — WP0 and WP1 unlock everything. After that, Workflow A and Workflow B can be built in parallel; they meet only at WP10 (B's PR is reviewed by A) and WP13. |
| --- |

[Diagram in the online doc: dependency graph · 15 work packages, 3 milestones]

The longest chain runs through Workflow B: WP0 → WP1 → WP5 → WP6 → WP8 → WP9 → WP10. Notifications and guardrails hang off WP1 and can be slotted in whenever convenient.

## Work packages

| **TL;DR** — 15 packages. Each has a check you can run on the test repo; a package is done only when its check passes and the evidence (run links, screenshots of labels and comments) is in its PR. |
| --- |

| ID | Package | Depends on | Delivers | Done when |
| --- | --- | --- | --- | --- |
| WP0 | Repo bootstrap | — | Repo layout, `CLAUDE.md`, config schema + validator, caller template | Caller in the test repo loads and validates `.github/ai-workflows.yml` in a green run |
| WP1 | Shared runtime | WP0 | Reusable job running Claude Code on `CLAUDE_CODE_OAUTH_TOKEN`; orchestrator that applies agents' JSON outputs via `gh api`; label bootstrap; command parser with permission check | `/ping` from a maintainer gets a reply; from a non-maintainer is ignored; all labels exist |
| WP2 | A · core review | WP1 | Steps 1–7 and 9: context, CI wait, risk tier, 4 passes, verify, rubric, summary comment with hidden marker, verdict label | Dummy PR gets one comment + one label; a new push updates the same comment |
| WP3 | A · placement + formal review | WP2 | Inline vs general rule, `suggestion` blocks, one GitHub review, never Approve | Seeded-bug PR gets an inline comment and Request changes; a nit on a low-risk path stays in the summary |
| WP4 | A · fork PRs | WP2 | `fork_prs: on-command` handling | Fork PR is not reviewed until a maintainer comments `/review` |
| WP5 | B1 · classify | WP1 | Classifier agent, dedup, already-fixed check | 3 test issues get `type: bug`, `feature`, `question`; a duplicate gets `triage: duplicate` |
| WP6 | B2 · reproduce | WP5 | Sandboxed reproducer, repro test stored, needs-info comment, reply restarts B2 | Clear bug → `triage: reproduced` + test; vague bug → `triage: needs-info`; the reporter's reply reruns it |
| WP7 | B2 · reporter silence | WP6 | Day-4 ping job, `actions/stale` workflow, `keep-open` | With days shortened in config, ping, stale and close happen in order; a reply resets them |
| WP8 | B3–B4 · analyse + ask | WP6 | Root-cause report, `/fix`, `/fix <guidance>`, `/no-fix` | Reproduced bug gets an analysis comment; each command does what the spec says |
| WP9 | B5 · fix loop | WP8 | Implementer + adversarial reviewer, 3-round cap, `ai-fix/*` branch, escalation | Seeded bug fixed in ≤ 3 rounds; a forced failure gives a draft PR, `fix: needs-maintainer`, assignment and review request |
| WP10 | B6 · PR into A | WP9, WP3 | PR body, `ai-fix` label, A runs on it | One issue goes from opened to a verdict label with no manual step except `/fix` |
| WP11 | Notifications | WP1 | Slack and Telegram senders, the 5 events | Each event sends one message with a working link, on both channels |
| WP12 | Guardrails | WP1 | `ai: off`, budgets, `ai: error`, injection reporting | `ai: off` stops a run; a forced crash gives `ai: error` + comment; an injected instruction is reported, not obeyed |
| WP13 | Contributor mode | WP3, WP8 | Fork caller guide (level 1); local Claude Code plugin with review and analyse skills (level 0) | Review runs on a branch locally and in a fork, with nothing posted upstream |
| WP14 | Onboarding kit | WP3 | Install guide, rights checklist, caller + config templates | A second repo is set up from the guide alone in under 30 minutes |

Metrics logging from the spec is left out of this plan; it is worth adding once both workflows have run for a few weeks.

## Milestones and test setup

| **TL;DR** — Three milestones: A usable on your repos (M1), bugs triaged and analysed (M2), bugs fixed end to end (M3). Everything is tested on a throwaway repo with seeded bugs, plus a second GitHub account for fork and permission tests. |
| --- |

| Milestone | Packages | What you can do from then on |
| --- | --- | --- |
| M1 · Review | WP0–WP4, WP14 | Install Workflow A on any repo you own |
| M2 · Triage | WP5–WP8, WP11 | New bug issues are reproduced, analysed and put to you, with chat alerts |
| M3 · Fix | WP9, WP10, WP12, WP13 | Approved bugs come back as reviewed PRs; contributor mode works |

**Test setup** (you create these before WP0):

- **Test repo** `ai-workflows-playground`, public, with a small app and a real test suite. The session seeds bugs into it on purpose, one per WP check.
- **Second GitHub account** (a free one is enough) to open issues as an outside reporter, send fork PRs and try commands without rights. WP1, WP4, WP6 and WP7 need it.
- **Your first real repo** gets Workflow A only after M1, then B after M3.
- **Secrets** on the test repo: `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`), then `SLACK_WEBHOOK_URL` or `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` by WP11.

## Starter pack

| **TL;DR** — Unzip `ai-workflows-starter.zip` as the first commit of the new repo, do the manual steps in `SETUP.md`, then open Claude Code in the repo and paste the prompt from `KICKOFF.md`. |
| --- |

| File | What it is |
| --- | --- |
| `README.md` | What the repo is and how it is laid out |
| `CLAUDE.md` | Standing rules for every Claude Code session in this repo: source of truth, one package per PR, security rules |
| `KICKOFF.md` | The prompt for the first session |
| `SETUP.md` | Your manual checklist: repos, token, secrets, second account, Actions access |
| `docs/spec.md` | The spec, exported from the doc |
| `docs/plan.md` | This plan, exported from the doc |
| `docs/progress.md` | Status of each work package, kept up to date by the session |
| `templates/ai-workflows.example.yml` | Per-repo config example |
| `templates/caller.example.yml` | Draft of the short workflow a target repo adds; WP0 finalises it |

When the spec or this plan changes, export the doc again as Markdown and replace the file in `docs/`, so the session always reads the current version.

## Open points

| **TL;DR** — Three things only the build can settle; the session raises each one when it reaches the package concerned. |
| --- |

- [ ] **Sandbox for B2 and B5 (WP6).** The Actions runner is a VM per job; whether that is isolation enough, or whether repro code runs in a container with no network, is decided when WP6 starts.
- [ ] **Where run state lives (WP1).** The hidden marker comment carries per-item state; whether a separate store is needed for the session record is decided in WP1.
- [ ] **Usage limits (WP2).** The real usage per reviewed PR on your subscription is measured in WP2, and the per-run budgets in the config are set from it.
