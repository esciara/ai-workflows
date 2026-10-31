# Diagrams

One overview of all work packages, then one small diagram per WP, added in the WP's PR, required by the definition of done. Each diagram's source is `docs/diagrams/<name>.mmd`. A per-WP diagram is `docs/diagrams/wp<N>.mmd` (`wp<N><x>.mmd` for a split such as WP2a); `scripts/dev/render-diagrams` generates its section below, with the heading and Done when from its row in `docs/plan.md`, in plan order, so no marker is placed by hand (ADR-0048). Another diagram needs a matching `generated:<name>` block here.

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

<!-- BEGIN generated:per-wp (from docs/diagrams/wp<N>[x].mmd and docs/plan.md by scripts/dev/render-diagrams; edit the .mmd or the plan, not this block) -->
## WP1 — Shared runtime

Done when ([docs/plan.md, line 33](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L33)): `/ping` from a maintainer gets a reply; from a non-maintainer is ignored; all labels exist

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

## WP2a — A · context, CI wait, one pass, summary + label

Done when ([docs/plan.md, line 35](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L35)): Dummy PR gets one comment + one label; a new push updates the same comment (`tests/e2e/test_wp2.py`)

```mermaid
flowchart TD
  O["PR opened or new push<br/>(not a draft)"] --> S["Start job<br/>drop old verdict, label 'ai-review: pending'"]
  S --> C["Context job, read-only token<br/>diff, touched files, callers, linked issue"]
  C --> W{"CI wait (20 min budget)<br/>+ risk tier from risk paths"}
  W --> P["Review pass agent job<br/>no GitHub token, code inline<br/>JSON only"]
  P -- JSON --> V{"Orchestrator<br/>matches the review schema?"}
  V -- no --> E["Label 'ai: error'"]
  V -- yes --> R["Rubric: blocking finding or red CI,<br/>high tier, no linked issue, big diff, CI timeout"]
  R --> M["Summary comment, found by its hidden marker<br/>created once, updated on each push"]
  M --> L["Verdict label replaces 'ai-review: pending'<br/>merge / changes-requested / human-review"]
```

## WP2b — A · 4 passes, verify, severity, step 9

Done when ([docs/plan.md, line 36](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L36)): WP2a's Done when still holds with 4 passes and verify (`tests/e2e/test_wp2.py` still passes)

```mermaid
flowchart TD
  C["Context job, read-only token<br/>facts, context, last run's open findings<br/>(state block of the summary comment)"] --> P["4 pass agent jobs (matrix)<br/>correctness, security, maintainability, tests<br/>no GitHub token, JSON only"]
  P -- 4 artifacts --> VP["Verify (refute) agent job<br/>no GitHub token<br/>each candidate: confirmed / refuted / duplicate"]
  C -. previous findings .-> VP
  VP -- JSON --> V{"Orchestrator<br/>all 5 answers match their schemas?"}
  V -- no --> E["Label 'ai: error'"]
  V -- yes --> F["Keep confirmed findings<br/>severity: blocking / should-fix / nit"]
  F --> H["Step 9: last run's findings<br/>marked resolved or still open"]
  H --> R["Rubric → verdict"]
  R --> M["Summary comment updated in place<br/>findings, history, usage of the 5 agents"]
  M --> L["Verdict label"]
```

## WP3 — A · placement + formal review

Done when ([docs/plan.md, line 37](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L37)): Seeded-bug PR gets an inline comment and Request changes; a nit on a low-risk path stays in the summary

```mermaid
flowchart TD
  F["Confirmed findings<br/>(after verify, WP2b)"] --> PL{"Placement rule, per finding<br/>first matching row wins"}
  PL -- "no line, or spread wide" --> G["General: summary table only"]
  PL -- "nit, one place, low/medium-risk path" --> N["Collapsed nits section<br/>of the summary"]
  PL -- "line inside a diff hunk" --> I["Inline comment<br/>+ suggestion block when the fix is a few lines<br/>on a low/medium-risk path"]
  PL -- "line GitHub cannot comment on" --> G
  I --> RV{"At most one GitHub review per run<br/>never Approve"}
  RV -- changes-requested --> RC["Request changes"]
  RV -- otherwise --> CM["Comment<br/>earlier Request changes dismissed"]
  RC & CM --> S["Summary comment links<br/>each inline thread"]
  G & N --> S
  S --> L["Verdict label"]
```

## WP5 — B1 · classify

Done when ([docs/plan.md, line 39](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L39)): 3 test issues get `type: bug`, `feature`, `question`; a duplicate gets `triage: duplicate`

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
<!-- END generated:per-wp -->
