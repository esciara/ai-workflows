# Diagrams

One overview of all work packages, then one small diagram per WP, added when that WP starts. Each diagram's source is `docs/diagrams/<name>.mmd`; edit the `.mmd`, add a matching `generated:<name>` block here for a new one, then run `scripts/dev/render-diagrams`.

## Overview — work packages and dependencies

Key:

- Colours:
  - grey = shared foundation
  - blue = Workflow A (PR review)
  - green = Workflow B (issue triage and fix)
  - orange = cross-cutting
- Boxes:
  - solid dark box = done
  - very pale box with dotted border = not done yet

Click a box to open that WP's definition in `docs/plan.md`; if clicking doesn't work in your viewer, use the table below.

<!-- BEGIN generated:overview (from docs/diagrams/overview.mmd by scripts/dev/render-diagrams; edit the .mmd, not this block) -->
```mermaid
flowchart TD
  WP0["WP0 Bootstrap<br/>config + caller"]:::done --> WP1["WP1 Shared runtime<br/>agent runner, labels, commands"]:::done

  WP1 --> WP2["WP2 A core review<br/>4 passes, verdict label"]:::a
  WP2 --> WP3["WP3 A formal review<br/>inline comments"]:::a
  WP2 --> WP4["WP4 A fork PRs<br/>/review on command"]:::a

  WP1 --> WP5["WP5 B classify<br/>dedup, already fixed?"]:::b
  WP5 --> WP6["WP6 B reproduce<br/>repro test, needs info"]:::b
  WP6 --> WP7["WP7 B reporter silence<br/>ping, stale, close"]:::b
  WP6 --> WP8["WP8 B analyse<br/>root cause, /fix"]:::b
  WP8 --> WP9["WP9 B fix loop<br/>implement + review, max 3"]:::b
  WP9 --> WP10["WP10 B opens PR<br/>reviewed by A"]:::b
  WP3 --> WP10

  WP1 --> WP11["WP11 Notifications<br/>Slack / Telegram"]:::x
  WP1 --> WP12["WP12 Guardrails<br/>ai: off, budgets, errors"]:::x
  WP3 --> WP13["WP13 Contributor mode<br/>fork guide, local plugin"]:::x
  WP8 --> WP13
  WP3 --> WP14["WP14 Onboarding kit<br/>install guide, templates"]:::x

  click WP0 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L32" "Open WP0 in docs/plan.md" _blank
  click WP1 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L33" "Open WP1 in docs/plan.md" _blank
  click WP2 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L34" "Open WP2 in docs/plan.md" _blank
  click WP3 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L35" "Open WP3 in docs/plan.md" _blank
  click WP4 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L36" "Open WP4 in docs/plan.md" _blank
  click WP5 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L37" "Open WP5 in docs/plan.md" _blank
  click WP6 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L38" "Open WP6 in docs/plan.md" _blank
  click WP7 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L39" "Open WP7 in docs/plan.md" _blank
  click WP8 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L40" "Open WP8 in docs/plan.md" _blank
  click WP9 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L41" "Open WP9 in docs/plan.md" _blank
  click WP10 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L42" "Open WP10 in docs/plan.md" _blank
  click WP11 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L43" "Open WP11 in docs/plan.md" _blank
  click WP12 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L44" "Open WP12 in docs/plan.md" _blank
  click WP13 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L45" "Open WP13 in docs/plan.md" _blank
  click WP14 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L46" "Open WP14 in docs/plan.md" _blank

  classDef done fill:#374151,stroke:#111827,color:#ffffff
  classDef base fill:#f3f4f6,stroke:#9ca3af,stroke-dasharray:5 4,color:#6b7280
  classDef a fill:#eff6ff,stroke:#60a5fa,stroke-dasharray:5 4,color:#6b7280
  classDef b fill:#f0fdf4,stroke:#4ade80,stroke-dasharray:5 4,color:#6b7280
  classDef x fill:#fff7ed,stroke:#fb923c,stroke-dasharray:5 4,color:#6b7280
  classDef aDone fill:#1d4ed8,stroke:#1e3a8a,color:#ffffff
  classDef bDone fill:#15803d,stroke:#14532d,color:#ffffff
  classDef xDone fill:#c2410c,stroke:#7c2d12,color:#ffffff
```
<!-- END generated:overview -->

| WP | Definition |
| --- | --- |
| WP0 | [docs/plan.md, line 32](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L32) |
| WP1 | [docs/plan.md, line 33](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L33) |
| WP2 | [docs/plan.md, line 34](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L34) |
| WP3 | [docs/plan.md, line 35](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L35) |
| WP4 | [docs/plan.md, line 36](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L36) |
| WP5 | [docs/plan.md, line 37](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L37) |
| WP6 | [docs/plan.md, line 38](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L38) |
| WP7 | [docs/plan.md, line 39](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L39) |
| WP8 | [docs/plan.md, line 40](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L40) |
| WP9 | [docs/plan.md, line 41](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L41) |
| WP10 | [docs/plan.md, line 42](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L42) |
| WP11 | [docs/plan.md, line 43](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L43) |
| WP12 | [docs/plan.md, line 44](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L44) |
| WP13 | [docs/plan.md, line 45](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L45) |
| WP14 | [docs/plan.md, line 46](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L46) |

Milestones: **M1** review usable = WP0–4, WP14 · **M2** bugs triaged and analysed = WP5–8, WP11 · **M3** bugs fixed end to end = WP9, 10, 12, 13.

## WP1 — Shared runtime

What happens when someone types `/ping` on an issue or PR in a target repo. `/ping` is a health check: it does nothing except confirm the whole chain works, from comment to reply.

<!-- BEGIN generated:wp1 (from docs/diagrams/wp1.mmd by scripts/dev/render-diagrams; edit the .mmd, not this block) -->
```mermaid
flowchart TD
  C["Comment '/ping'<br/>on target repo"] --> P{"Command parser<br/>in maintainers list<br/>AND write access?"}
  P -- no --> I["Ignored<br/>no reply"]
  P -- yes --> AG["Agent job<br/>Claude Code, read-only<br/>no GitHub token"]
  AG -- JSON --> V{"Orchestrator<br/>does Claude's JSON answer<br/>match the ping answer schema?"}
  V -- no --> E["Label 'ai: error'"]
  V -- yes --> R["Orchestrator posts reply<br/>via gh api"]
  L["Label bootstrap<br/>creates all labels"] -.-> R
```
<!-- END generated:wp1 -->

Check on the playground:

- maintainer `/ping` → reply
- tester App `/ping` → nothing
- all labels exist
