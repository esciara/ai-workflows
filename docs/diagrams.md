# Diagrams

One overview of all work packages, then one small diagram per WP, added when that WP starts.

## Overview — work packages and dependencies

Colours: grey = shared foundation, blue = Workflow A (PR review), green = Workflow B (issue triage and fix), orange = cross-cutting. Thick black border = done.

```mermaid
flowchart TD
  WP0["WP0 Bootstrap<br/>config + caller"]:::done --> WP1["WP1 Shared runtime<br/>agent runner, labels, commands"]:::base

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

  classDef done fill:#374151,stroke:#000000,stroke-width:4px,color:#ffffff
  classDef base fill:#4b5563,stroke:#1f2937,color:#ffffff
  classDef a fill:#1d4ed8,stroke:#1e3a8a,color:#ffffff
  classDef b fill:#15803d,stroke:#14532d,color:#ffffff
  classDef x fill:#c2410c,stroke:#7c2d12,color:#ffffff
```

Milestones: **M1** review usable = WP0–4, WP14 · **M2** bugs triaged and analysed = WP5–8, WP11 · **M3** bugs fixed end to end = WP9, 10, 12, 13.

## WP1 — Shared runtime

What happens when someone types `/ping` on an issue or PR in a target repo.

```mermaid
flowchart TD
  C["Comment '/ping'<br/>on target repo"] --> P{"Command parser<br/>in maintainers list<br/>AND write access?"}
  P -- no --> I["Ignored<br/>no reply"]
  P -- yes --> AG["Agent job<br/>Claude Code, read-only<br/>no GitHub token"]
  AG -- JSON --> V{"Orchestrator<br/>JSON matches schema?"}
  V -- no --> E["Label 'ai: error'"]
  V -- yes --> R["Orchestrator posts reply<br/>via gh api"]
  L["Label bootstrap<br/>creates all labels"] -.-> R
```

Check on the playground: maintainer `/ping` → reply; tester App `/ping` → nothing; all labels exist.
