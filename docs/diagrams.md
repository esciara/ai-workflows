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
  - pale box with thick solid border = in progress (or in review)
  - very pale box with dotted border = not started

Box status comes from the beads board (`docs/board.jsonl`) and the links from the WP table of `docs/plan.md`, both set by `scripts/dev/render-diagrams` (ADR-0046); `overview.mmd` declares only each WP's lane. Click a box to open that WP's definition in `docs/plan.md`; if clicking doesn't work in your viewer, use the table below.

<!-- BEGIN generated:overview (from docs/diagrams/overview.mmd by scripts/dev/render-diagrams; edit the .mmd, not this block) -->
```mermaid
flowchart TD
  %% Status is not typed here: render-diagrams sets each WP's class from its bead in docs/board.jsonl (ADR-0046).
  %% Lanes: <lane> not started, <lane>Wip in progress, <lane>Done done.
  %% lane base: WP0 WP1
  %% lane a: WP2 WP3 WP4
  %% lane b: WP5 WP6 WP7 WP8 WP9 WP10
  %% lane x: WP11 WP12 WP13 WP14

  WP0["WP0 Bootstrap<br/>config + caller"] --> WP1["WP1 Shared runtime<br/>agent runner, labels, commands"]

  WP1 --> WP2["WP2 A core review<br/>4 passes, verdict label"]
  WP2 --> WP3["WP3 A formal review<br/>inline comments"]
  WP2 --> WP4["WP4 A fork PRs<br/>/review on command"]

  WP1 --> WP5["WP5 B classify<br/>dedup, already fixed?"]
  WP5 --> WP6["WP6 B reproduce<br/>repro test, needs info"]
  WP6 --> WP7["WP7 B reporter silence<br/>ping, stale, close"]
  WP6 --> WP8["WP8 B analyse<br/>root cause, /fix"]
  WP8 --> WP9["WP9 B fix loop<br/>implement + review, max 3"]
  WP9 --> WP10["WP10 B opens PR<br/>reviewed by A"]
  WP3 --> WP10

  WP1 --> WP11["WP11 Notifications<br/>Slack / Telegram"]
  WP1 --> WP12["WP12 Guardrails<br/>ai: off, budgets, errors"]
  WP3 --> WP13["WP13 Contributor mode<br/>fork guide, local plugin"]
  WP8 --> WP13
  WP3 --> WP14["WP14 Onboarding kit<br/>install guide, templates"]

  classDef base fill:#f3f4f6,stroke:#9ca3af,stroke-dasharray:5 4,color:#6b7280
  classDef a fill:#eff6ff,stroke:#60a5fa,stroke-dasharray:5 4,color:#6b7280
  classDef b fill:#f0fdf4,stroke:#4ade80,stroke-dasharray:5 4,color:#6b7280
  classDef x fill:#fff7ed,stroke:#fb923c,stroke-dasharray:5 4,color:#6b7280
  classDef baseWip fill:#f3f4f6,stroke:#4b5563,stroke-width:3px,color:#111827
  classDef aWip fill:#eff6ff,stroke:#1d4ed8,stroke-width:3px,color:#111827
  classDef bWip fill:#f0fdf4,stroke:#15803d,stroke-width:3px,color:#111827
  classDef xWip fill:#fff7ed,stroke:#c2410c,stroke-width:3px,color:#111827
  classDef baseDone fill:#374151,stroke:#111827,color:#ffffff
  classDef aDone fill:#1d4ed8,stroke:#1e3a8a,color:#ffffff
  classDef bDone fill:#15803d,stroke:#14532d,color:#ffffff
  classDef xDone fill:#c2410c,stroke:#7c2d12,color:#ffffff

  click WP0 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L32" "Open WP0 in docs/plan.md" _blank
  click WP1 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L33" "Open WP1 in docs/plan.md" _blank
  click WP2 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L34" "Open WP2 in docs/plan.md" _blank
  click WP3 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L37" "Open WP3 in docs/plan.md" _blank
  click WP4 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L38" "Open WP4 in docs/plan.md" _blank
  click WP5 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L39" "Open WP5 in docs/plan.md" _blank
  click WP6 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L40" "Open WP6 in docs/plan.md" _blank
  click WP7 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L41" "Open WP7 in docs/plan.md" _blank
  click WP8 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L42" "Open WP8 in docs/plan.md" _blank
  click WP9 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L43" "Open WP9 in docs/plan.md" _blank
  click WP10 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L44" "Open WP10 in docs/plan.md" _blank
  click WP11 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L45" "Open WP11 in docs/plan.md" _blank
  click WP12 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L48" "Open WP12 in docs/plan.md" _blank
  click WP13 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L51" "Open WP13 in docs/plan.md" _blank
  click WP14 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L52" "Open WP14 in docs/plan.md" _blank

  class WP0 baseDone
  class WP1 baseDone
  class WP2 aDone
  class WP3 aDone
  class WP4 aWip
  class WP5 bDone
  class WP6 b
  class WP7 b
  class WP8 b
  class WP9 b
  class WP10 b
  class WP11 xWip
  class WP12 xWip
  class WP13 x
  class WP14 x
```
<!-- END generated:overview -->

<!-- BEGIN generated:overview-links (from docs/plan.md by scripts/dev/render-diagrams; edit the plan, not this block) -->
| WP | Definition |
| --- | --- |
| WP0 | [docs/plan.md, line 32](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L32) |
| WP1 | [docs/plan.md, line 33](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L33) |
| WP2 | [docs/plan.md, line 34](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L34) |
| WP3 | [docs/plan.md, line 37](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L37) |
| WP4 | [docs/plan.md, line 38](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L38) |
| WP5 | [docs/plan.md, line 39](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L39) |
| WP6 | [docs/plan.md, line 40](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L40) |
| WP7 | [docs/plan.md, line 41](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L41) |
| WP8 | [docs/plan.md, line 42](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L42) |
| WP9 | [docs/plan.md, line 43](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L43) |
| WP10 | [docs/plan.md, line 44](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L44) |
| WP11 | [docs/plan.md, line 45](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L45) |
| WP12 | [docs/plan.md, line 48](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L48) |
| WP13 | [docs/plan.md, line 51](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L51) |
| WP14 | [docs/plan.md, line 52](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L52) |
<!-- END generated:overview-links -->

Milestones: see [docs/plan.md](plan.md#milestones-and-test-setup).

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

## WP5 — B1 classify

What happens when an issue is opened, or a maintainer types `/retriage` on one: two-pass classification (extract, then classify against candidate issues and the version's fix range).

<!-- BEGIN generated:wp5 (from docs/diagrams/wp5.mmd by scripts/dev/render-diagrams; edit the .mmd, not this block) -->
```mermaid
flowchart TD
  O["Issue opened<br/>or maintainer '/retriage'"] --> G{"Gate<br/>new issue, or accepted<br/>/retriage on an issue?"}
  G -- no --> X["Nothing"]
  G -- yes --> C["Context job, read-only token<br/>the issue"]
  C -- artifact --> P1["Extractor agent job (pass 1)<br/>no GitHub token, no file tools<br/>version, search phrases, file paths"]
  P1 -- JSON --> K["Candidates job, read-only token<br/>checks pass-1 schema; issue search over all issues;<br/>commits and merged PRs since the version's tag<br/>(fallback: latest release, low confidence)"]
  K -- artifact --> A["Classifier agent job (pass 2)<br/>no GitHub token, no file tools<br/>JSON only"]
  K -- invalid pass 1 --> E
  A -- JSON --> V{"Orchestrator<br/>matches the classifier schema?"}
  V -- no --> E["Label 'ai: error'"]
  V -- yes --> R{"References exist?<br/>duplicate issue; commit on / PR merged into<br/>the default branch"}
  R -- duplicate, high or medium --> D["type label + 'triage: duplicate'<br/>link; never closed"]
  R -- possible fix --> F["'possibly fixed by' link in the comment<br/>B2 reproduction confirms"]
  R -- none --> L{"Confidence low?"}
  D & F --> L
  L -- yes --> H["type label + 'triage: needs-human'"]
  L -- no --> T["type label<br/>bug goes on to B2 (WP6)"]
  H & T --> S["One triage comment<br/>updated in place"]
```
<!-- END generated:wp5 -->
