# Progress

Updated by the Claude Code session at the end of every work package. Status: `todo` · `in progress` · `in review` · `done`.

| WP | Package | Depends on | Status | PR | Notes |
| --- | --- | --- | --- | --- | --- |
| WP0 | Repo bootstrap | — | done | [#2](https://github.com/esciara/ai-workflows/pull/2) | Python 3.12; config read from default branch |
| WP1 | Shared runtime | WP0 | in review | [#7](https://github.com/esciara/ai-workflows/pull/7), [#8](https://github.com/esciara/ai-workflows/pull/8) | Agents on base-action (ADR-0012); publish gets `pull-requests: write` (ADR-0013) |
| WP2 | A · core review | WP1 | todo | | |
| WP3 | A · placement + formal review | WP2 | todo | | |
| WP4 | A · fork PRs | WP2 | todo | | |
| WP5 | B1 · classify | WP1 | todo | | |
| WP6 | B2 · reproduce | WP5 | todo | | |
| WP7 | B2 · reporter silence | WP6 | todo | | |
| WP8 | B3–B4 · analyse + ask | WP6 | todo | | |
| WP9 | B5 · fix loop | WP8 | todo | | |
| WP10 | B6 · PR into A | WP9, WP3 | todo | | |
| WP11 | Notifications | WP1 | todo | | |
| WP12 | Guardrails | WP1 | todo | | |
| WP13 | Contributor mode | WP3, WP8 | todo | | |
| WP14 | Onboarding kit | WP3 | todo | | |

## Metrics

Baseline for a later comparison of build loops. One row per finished WP, updated at the end of the WP.

| WP | maintainer interventions | verifier fails | rework PRs | coordination issues | notes |
| --- | --- | --- | --- | --- | --- |
| WP0 | n/a (pre-loop) | n/a (pre-loop) | 0 | 0 | Built before [D11](adr/0011-factory-loop-and-independent-verifier.md): plan "go" + one review; kept as one PR over ~600 lines at the maintainer's call. Verifier run afterwards on #2: pass |
| WP1 | 2 decisions (base-action, PR-write scope) + 2 playground merges (#4, #7) | 1 | 0 | 0 | Split into 2 stacked PRs (#7, #8) for size; 3 agent/publish fixes found by the playground check; verifier fail: tester-ignored evidence cut by log truncation |

## Milestones

- **M1 · Review** — WP0–WP4, WP14: install Workflow A on any repo you own.
- **M2 · Triage** — WP5–WP8, WP11: bugs reproduced, analysed and put to you, with chat alerts.
- **M3 · Fix** — WP9, WP10, WP12, WP13: approved bugs come back as reviewed PRs; contributor mode works.

## Log

<!-- One line per finished WP: date · WP · PR link · one-line outcome -->

- 2026-10-30 · WP0 · [#2](https://github.com/esciara/ai-workflows/pull/2) · Caller on playground validates config: green run 41087000415, invalid config red run 41087013620.
- 2026-10-30 · WP1 · [#7](https://github.com/esciara/ai-workflows/pull/7), [#8](https://github.com/esciara/ai-workflows/pull/8) · `/ping`: maintainer reply on issue (run 41136897904) and PR (run 41138098292); tester ignored (run 41137072587); 20 labels synced.
