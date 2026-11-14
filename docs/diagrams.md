# Diagrams

Snapshot of 2026-11-14, hand-maintained: nothing generates it. Where things stand is the Status column of `docs/plan.md`, which wins over any box colour here. Only work merged on `main` has a flow diagram; a new diagram goes in a PR description when useful.

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
  - very pale box with dotted border = not started or paused (WP6 says paused in its box)
- Parent boxes (WP2, WP11, WP12) are the whole package; the split boxes (WP2a, WP2b, WP11a, WP11b, WP11b1, WP12a, WP12b) are its PRs.

The box statuses are those of the snapshot's date. Click a box to open that WP's definition in `docs/plan.md`; if clicking doesn't work in your viewer, use the table below.

```mermaid
flowchart TD
  %% Hand-maintained. Classes: <lane> not started or paused, <lane>Wip in progress, <lane>Done done; set from the plan's Status column.
  WP0["WP0 Bootstrap<br/>config + caller"]
  WP1["WP1 Shared runtime<br/>agent runner, labels, commands"]
  WP2["WP2 A core review<br/>(whole: 2a + 2b)"]
  WP2a["WP2a A context, CI wait<br/>one pass, label"]
  WP2b["WP2b A 4 passes, verify<br/>severity, step 9"]
  WP3["WP3 A formal review<br/>inline comments"]
  WP4["WP4 A fork PRs<br/>/review on command"]
  WP5["WP5 B classify<br/>dedup, already fixed?"]
  WP6["WP6 B reproduce<br/>paused"]
  WP7["WP7 B reporter silence<br/>ping, stale, close"]
  WP8["WP8 B analyse<br/>root cause, /fix"]
  WP9["WP9 B fix loop<br/>implement + review"]
  WP10["WP10 B opens PR<br/>reviewed by A"]
  WP11["WP11 Notifications<br/>(whole: 11a + 11b)"]
  WP11a["WP11a Notification senders<br/>Slack, Telegram"]
  WP11b["WP11b Notification events<br/>the 5 events"]
  WP11b1["WP11b1 Issue triaged alert<br/>first event"]
  WP12["WP12 Guardrails<br/>(whole: 12a + 12b)"]
  WP12a["WP12a Guardrails<br/>ai: off, ai: error"]
  WP12b["WP12b Guardrails<br/>injection, budgets"]
  WP13["WP13 Contributor mode<br/>fork guide, plugin"]
  WP14["WP14 Onboarding kit<br/>install guide, templates"]
  WP15["WP15 A usage metrics<br/>one line per run"]
  WP16["WP16 Three e2e slots<br/>ADR-0056"]
  WP17["WP17 Pre-push review loop<br/>dev process"]
  WP18["WP18 A closes fixed threads"]
  WP19["WP19 B: A's findings back<br/>into the fix loop"]

  WP0 --> WP1
  WP1 --> WP2
  WP1 --> WP2a
  WP2a --> WP2b
  WP2 --> WP3
  WP2 --> WP4
  WP1 --> WP5
  WP5 --> WP6
  WP6 --> WP7
  WP6 --> WP8
  WP8 --> WP9
  WP9 --> WP10
  WP3 --> WP10
  WP1 --> WP11
  WP1 --> WP11a
  WP11a --> WP11b
  WP9 --> WP11b
  WP12 --> WP11b
  WP11a --> WP11b1
  WP5 --> WP11b1
  WP1 --> WP12
  WP1 --> WP12a
  WP1 --> WP12b
  WP3 --> WP13
  WP8 --> WP13
  WP3 --> WP14
  WP15 --> WP14
  WP2 --> WP15
  WP1 --> WP16
  WP2b --> WP17
  WP2b --> WP18
  WP3 --> WP18
  WP10 --> WP19
  WP18 --> WP19

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

  click WP0 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L34" "Open WP0 in docs/plan.md" _blank
  click WP1 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L35" "Open WP1 in docs/plan.md" _blank
  click WP2 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L36" "Open WP2 in docs/plan.md" _blank
  click WP2a "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L37" "Open WP2a in docs/plan.md" _blank
  click WP2b "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L38" "Open WP2b in docs/plan.md" _blank
  click WP3 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L39" "Open WP3 in docs/plan.md" _blank
  click WP4 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L40" "Open WP4 in docs/plan.md" _blank
  click WP5 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L41" "Open WP5 in docs/plan.md" _blank
  click WP6 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L42" "Open WP6 in docs/plan.md" _blank
  click WP7 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L43" "Open WP7 in docs/plan.md" _blank
  click WP8 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L44" "Open WP8 in docs/plan.md" _blank
  click WP9 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L45" "Open WP9 in docs/plan.md" _blank
  click WP10 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L46" "Open WP10 in docs/plan.md" _blank
  click WP11 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L47" "Open WP11 in docs/plan.md" _blank
  click WP11a "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L48" "Open WP11a in docs/plan.md" _blank
  click WP11b "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L49" "Open WP11b in docs/plan.md" _blank
  click WP11b1 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L50" "Open WP11b1 in docs/plan.md" _blank
  click WP12 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L51" "Open WP12 in docs/plan.md" _blank
  click WP12a "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L52" "Open WP12a in docs/plan.md" _blank
  click WP12b "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L53" "Open WP12b in docs/plan.md" _blank
  click WP13 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L54" "Open WP13 in docs/plan.md" _blank
  click WP14 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L55" "Open WP14 in docs/plan.md" _blank
  click WP15 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L56" "Open WP15 in docs/plan.md" _blank
  click WP16 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L57" "Open WP16 in docs/plan.md" _blank
  click WP17 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L58" "Open WP17 in docs/plan.md" _blank
  click WP18 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L59" "Open WP18 in docs/plan.md" _blank
  click WP19 "https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L60" "Open WP19 in docs/plan.md" _blank

  class WP0 baseDone
  class WP1 baseDone
  class WP2 aDone
  class WP2a aDone
  class WP2b aDone
  class WP3 aDone
  class WP4 aDone
  class WP5 bDone
  class WP6 b
  class WP7 b
  class WP8 b
  class WP9 b
  class WP10 b
  class WP11 xWip
  class WP11a xDone
  class WP11b x
  class WP11b1 xWip
  class WP12 xDone
  class WP12a xDone
  class WP12b xDone
  class WP13 x
  class WP14 xDone
  class WP15 aDone
  class WP16 baseDone
  class WP17 a
  class WP18 a
  class WP19 b
```

| WP | Status | Definition |
| --- | --- | --- |
| WP0 | done | [docs/plan.md, line 34](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L34) |
| WP1 | done | [docs/plan.md, line 35](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L35) |
| WP2 | done | [docs/plan.md, line 36](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L36) |
| WP2a | done | [docs/plan.md, line 37](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L37) |
| WP2b | done | [docs/plan.md, line 38](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L38) |
| WP3 | done | [docs/plan.md, line 39](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L39) |
| WP4 | done | [docs/plan.md, line 40](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L40) |
| WP5 | done | [docs/plan.md, line 41](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L41) |
| WP6 | paused | [docs/plan.md, line 42](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L42) |
| WP7 | todo | [docs/plan.md, line 43](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L43) |
| WP8 | todo | [docs/plan.md, line 44](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L44) |
| WP9 | todo | [docs/plan.md, line 45](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L45) |
| WP10 | todo | [docs/plan.md, line 46](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L46) |
| WP11 | in progress | [docs/plan.md, line 47](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L47) |
| WP11a | done | [docs/plan.md, line 48](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L48) |
| WP11b | todo | [docs/plan.md, line 49](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L49) |
| WP11b1 | in progress | [docs/plan.md, line 50](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L50) |
| WP12 | done | [docs/plan.md, line 51](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L51) |
| WP12a | done | [docs/plan.md, line 52](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L52) |
| WP12b | done | [docs/plan.md, line 53](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L53) |
| WP13 | todo | [docs/plan.md, line 54](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L54) |
| WP14 | done | [docs/plan.md, line 55](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L55) |
| WP15 | done | [docs/plan.md, line 56](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L56) |
| WP16 | done | [docs/plan.md, line 57](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L57) |
| WP17 | todo | [docs/plan.md, line 58](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L58) |
| WP18 | todo | [docs/plan.md, line 59](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L59) |
| WP19 | todo | [docs/plan.md, line 60](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L60) |

Milestones: see [docs/plan.md](plan.md#slices-and-test-setup).

Not started, so no flow diagram yet: WP7, WP8, WP9, WP10, WP11b (other events), WP13, WP17, WP18, WP19. WP6 is paused.

## WP1 — Shared runtime

Done when ([docs/plan.md, line 35](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L35)): A command from a maintainer is accepted, from a non-maintainer is refused; all labels exist

```mermaid
flowchart TD
  C["Comment on target repo"] --> P{"config.yml parses it once<br/>known command, author in maintainers<br/>AND write access?"}
  P -- no --> I["command = ''<br/>review and triage jobs skip"]
  P -- yes --> O["command = review / retriage / fix / no-fix<br/>in config output"]
  O --> RV["review.yml gate<br/>runs on 'review'"]
  O --> TR["triage.yml<br/>runs B1 on 'retriage'"]
  D["workflow_dispatch on the caller<br/>(once after install)"] --> L["labels.yml<br/>creates all labels"]
```

## WP2a — A · context, CI wait, one pass, summary + label

Done when ([docs/plan.md, line 37](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L37)): Dummy PR gets one comment + one label; a new push updates the same comment (`tests/e2e/test_wp2.py`)

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

Done when ([docs/plan.md, line 38](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L38)): WP2a's Done when still holds with 4 passes and verify (`tests/e2e/test_wp2.py` still passes)

```mermaid
flowchart TD
  C["Context job, read-only token<br/>facts, context, last run's open findings<br/>(state block of the summary comment)"] --> P["4 pass agent jobs (matrix)<br/>correctness, security, maintainability, tests<br/>no GitHub token, JSON only"]
  P -- 4 artifacts --> VP["Verify (refute) agent job<br/>no GitHub token<br/>each candidate: confirmed / refuted / duplicate"]
  C -. previous findings .-> VP
  VP -- JSON --> PU["Publish job, the only writer<br/>checks all 5 answers against their schemas"]
  PU -- invalid --> E["Label 'ai: error'"]
  PU -- valid --> F["Keep confirmed findings<br/>severity: blocking / should-fix / nit"]
  F --> H["Step 9: last run's findings<br/>marked resolved or still open"]
  H --> R["Rubric, verdict"]
  R --> M["Summary comment updated in place<br/>findings, history"]
  M --> L["Verdict label"]
  P -. usage numbers only .-> MT["Metrics job (WP15)<br/>one JSON line per run, artifact ai-workflows-metrics"]
```

## WP3 — A · placement + formal review

Done when ([docs/plan.md, line 39](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L39)): Seeded-bug PR gets an inline comment and Request changes; a nit on a low-risk path stays in the summary

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

## WP4 — A · fork PRs

Done when ([docs/plan.md, line 40](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L40)): Fork PR is not reviewed until a maintainer comments `/review`

```mermaid
flowchart TD
  FP["Fork PR event<br/>opened / synchronize<br/>read-only token, no secrets"] --> G{"review / gate<br/>reads the event payload"}
  SP["Same-repo PR event"] --> G
  DB["Dependabot PR event"] --> G
  CM["Comment '/review' on a PR<br/>(config.yml accepted it)"] --> G
  G -- "fork PR event" --> SK["All review jobs skipped<br/>nothing posted"]
  G -- "comment: not a maintainer<br/>or no write access" --> SK
  G -- "comment on a fork PR and fork_prs: off" --> SK
  G -- "Dependabot PR event<br/>(no secrets)" --> DH["dependabot job, no model<br/>label ai-review: human-review"]
  G -- "same-repo non-draft PR<br/>or maintainer /review" --> ST["start: ai-review: pending"]
  ST --> CX["context: checkout refs/pull/N/head<br/>no credentials, HEAD must equal the gated SHA<br/>read as text, never executed"]
  CX --> PA["4 passes + verify<br/>no token, StructuredOutput only"]
  PA --> PU["publish: summary + verdict label<br/>Commit reviewed = gated SHA"]
  NP["Fork push after a review<br/>pull_request_target, synchronize"] --> RF["review-fork-push<br/>API only: no checkout, no secrets<br/>pull-requests: write"]
  RF --> RM["Verdict label removed + one note<br/>maintainer may /review again"]
  RM -.-> CM
```

## WP5 — B1 · classify

Done when ([docs/plan.md, line 41](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L41)): 3 test issues get `type: bug`, `feature`, `question`; a duplicate gets `triage: duplicate`

The daily caps for outside authors (CP7b) sit in the context job; see their own diagram below.

```mermaid
flowchart TD
  O["Issue opened<br/>or maintainer '/retriage'"] --> G{"Gate<br/>new issue, or accepted<br/>/retriage on an issue?"}
  G -- no --> X["Nothing"]
  G -- yes --> C["Context job, read-only token<br/>the issue + daily cap check (CP7b)"]
  C -- artifact --> P1["Extractor agent job (pass 1)<br/>no GitHub token, no file tools<br/>version, search phrases, file paths"]
  P1 -- JSON --> K["Candidates job, read-only token<br/>checks pass-1 schema; issue search over all issues;<br/>commits and merged PRs since the version's tag<br/>(fallback: latest release, low confidence)"]
  K -- artifact --> A["Classifier agent job (pass 2)<br/>no GitHub token, no file tools<br/>JSON only"]
  K -- invalid pass 1 --> E
  A -- JSON --> V{"Publish job, the only writer<br/>matches the classifier schema?"}
  V -- no --> E["Label 'ai: error'"]
  V -- yes --> R{"References exist?<br/>duplicate issue; commit on / PR merged into<br/>the default branch"}
  R -- duplicate, high or medium --> D["type label + 'triage: duplicate'<br/>link; never closed"]
  R -- possible fix --> F["'possibly fixed by' link in the comment<br/>B2 reproduction would confirm (WP6, paused)"]
  R -- none --> L{"Confidence low?"}
  D & F --> L
  L -- yes --> H["type label + 'triage: needs-human'"]
  L -- no --> T["type label<br/>a bug waits for B2 (WP6, paused)"]
  H & T --> S["One triage comment<br/>updated in place"]
  S -. new issue only .-> AL["Chat alert (WP11b1)"]
```

## CP7b — B1 · triage caps for outside authors (ADR-0058)

Built and merged (PR #126), no WP row and no e2e; see Open items in `docs/plan.md`. Config keys: `limits.triage_per_author_per_day` (default 3) and `limits.triage_per_day` (default 20), both 0 or more.

```mermaid
flowchart TD
  E["issues.opened or /retriage"] --> CK{"context job: aiwf triage-cap<br/>read-only token, before any agent"}
  CK -- "/retriage (any event but issues)" --> OK["Not capped<br/>the maintainer chose to spend it"]
  CK -- "author in maintainers" --> OK
  CK --> LS["REST issue list, last 24 h, state=all<br/>pull requests dropped, authors not in maintainers<br/>only issues numbered at or below this one"]
  LS --> CT{"count above triage_per_day<br/>or author's count above triage_per_author_per_day?"}
  CT -- no --> OK
  CT -- yes --> CP["capped = true<br/>extract, candidates, classify skipped: no agent runs"]
  OK --> B1["B1 as usual (WP5)"]
  CP --> PB["publish: aiwf triage-capped<br/>label 'triage: needs-human'<br/>one sticky comment, fixed text<br/>(skipped when the item has 'ai: off')"]
  PB --> MN["Maintainer runs /retriage when wanted<br/>no automatic retry, no chat alert"]
```

## WP11a — Notification senders

Done when ([docs/plan.md, line 48](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L48)): A `workflow_dispatch` test event sends one message with a working link, on both channels

```mermaid
flowchart TD
  D["workflow_dispatch on the caller<br/>(test event)"] --> J["notify.yml job send<br/>permissions: {}"]
  E["WP11b: an event's text + link<br/>(WP11b1 built, others not started)"] -.-> J
  J --> S["aiwf notify --channels<br/>secrets via env only"]
  S --> SL["Slack incoming webhook<br/>expects 200 ok"]
  S --> TG["Telegram sendMessage<br/>expects ok + message_id"]
  SL --> R["AIWF_NOTIFY_RESULT line per message<br/>no secret, no request URL"]
  TG --> R
  R --> M["Maintainer clicks link back to GitHub"]
```

## WP11b1 — Notification: issue triaged

Status in the plan: in progress (code merged; the plan row flips when its e2e is accepted). Done when ([docs/plan.md, line 50](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L50)): A new issue triaged on the playground sends one message naming the issue and its type, with a working link to the issue, on both channels (`tests/e2e/test_wp11b.py`)

```mermaid
flowchart TD
  P["triage publish job<br/>classifier result accepted and published"] --> AT["alert text from checked fields only<br/>'[repo] #n triaged as type'<br/>+ 'duplicate of #k' / 'needs a person'<br/>output alert_text, alert_url"]
  CAP["Capped issue (CP7b)<br/>no classifier result"] -. no alert .-> X["No chat message"]
  AT --> G{"notify job runs only if<br/>event is issues.opened (never /retriage)<br/>and config notify is not 'none'?"}
  G -- no --> X
  G -- yes --> N["notify job: permissions {}<br/>the only job given the chat secrets<br/>aiwf notify --channels"]
  N --> SL["Slack"]
  N --> TG["Telegram"]
  SL & TG --> R["Message with link to the issue<br/>result line shows the text sent, no secret"]
```

## WP12a — Guardrails: `ai: off`, `ai: error`

Done when ([docs/plan.md, line 52](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L52)): `ai: off` stops a run; a forced crash gives `ai: error` + comment

```mermaid
flowchart TD
  E["Any event<br/>PR, issue, comment"] --> G{"config.yml: aiwf config<br/>item has 'ai: off'?"}
  G -- yes --> S["enabled = false<br/>every workflow job skipped"]
  G -- no --> J["Review / triage / command jobs<br/>agents hold no token"]
  J --> W{"Before each write<br/>live labels have 'ai: off'?"}
  W -- yes --> N["Write nothing<br/>(a label added after the gate still stops writes)"]
  W -- no --> P["Orchestrator publishes<br/>via gh api"]
  J -- "a job fails<br/>(agent error, turn or time limit)" --> F["'failed' job"]
  F --> R["Label 'ai: error'<br/>+ one sticky error comment with run link<br/>no retry"]
```

## WP12b — Guardrails: injection, budgets

Done when ([docs/plan.md, line 53](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L53)): An injected instruction is reported, not obeyed

```mermaid
flowchart TD
  T["Issue or PR event<br/>text is untrusted data"] --> A["Agents: extract, classify<br/>or 4 review passes + verify<br/>no tools, no secrets"]
  A -- "each agent" --> B["--max-turns + fixed step timeout-minutes<br/>(ADR-0050)"]
  B -- "limit hit: the job fails" --> F["'failed' job: 'ai: error'<br/>+ one sticky error comment, no retry"]
  A --> J["JSON with suspicious_instructions<br/>schema-checked"]
  J --> P["Normal publish"]
  P --> I["Comment line 'Possible prompt injection (ignored)'<br/>quotes cleaned; never followed"]
```

## WP16 — Three e2e slots (ADR-0056)

Done when ([docs/plan.md, line 57](https://github.com/esciara/ai-workflows/blob/main/docs/plan.md?plain=1#L57)): Three e2e runs execute in parallel on slots 1–3 and the drift test covers the three callers (`tests/e2e/test_wp16.py`, `tests/e2e/test_callers_match.py`)

Slots live on the maintainer's Mac and the playground; nothing here runs on target repos.

```mermaid
flowchart TD
  T["pytest with AIWF_E2E_SLOT = 1 | 2 | 3 | any"] --> PK{"scripts/aiwf/e2eslot.py<br/>which slot n?"}
  PK -- "1, 2 or 3" --> WT["wait for flock aiwf-e2e-n.lock<br/>in the git common directory"]
  PK -- "any" --> FR["first free slot<br/>waits when all three are busy"]
  FR --> WT
  WT --> RF["push HEAD to ref e2e-target-n as the agent App<br/>--force-with-lease on that ref"]
  RF --> CL["playground caller-e2e-n.yml runs this repo at e2e-target-n"]
  PR["Item routed to slot n<br/>PR branch e2e/n/... or label e2e-target-n"] --> CL
  CL --> RUN["Tests drive the playground<br/>label, branch prefix, workflow names derive from n"]
  RUN --> REL["Process exit: kernel drops the lock<br/>no cleanup after a crash"]
  DR["tests/e2e/test_callers_match.py<br/>read-only, no slot"] -. "3 callers match the template,<br/>normal caller gate = negation of the 3 slot gates" .-> CL
```

## Verdict check and stale-run rerun (ADR-0053, 0055, 0059)

On this repo's own PRs only: `verdict` is a job of `.github/workflows/ai-review.yml` and a required check of the ruleset on `main`. After-merge check still open (ADR-0059): confirm on the next real `human-review` PR that the rerun clears the block.

```mermaid
flowchart TD
  PE["pull_request run<br/>review job, then verdict job"] --> V1{"verdict, pull_request run<br/>owner approval of head,<br/>or label ai-review: merge?"}
  V1 -- "merge label" --> G1["green"]
  V1 -- "human-review, no AI review (Dependabot), no label yet" --> R1["red + explained ::error<br/>'waiting for maintainer approval'<br/>pending status posted for the text"]
  V1 -- "changes-requested or review failed" --> R2["red + explained ::error"]
  DR["draft PR"] -.-> SK["verdict skipped<br/>ready_for_review runs it"]
  RV["pull_request_review run<br/>(own concurrency group per run)"] --> ST{"review state?"}
  ST -- commented --> G2["green, no new status<br/>other runs keep their answers"]
  ST -- "approved or dismissed" --> AP{"owner approval of the head SHA?"}
  AP -- no --> RS["restore the AI verdict from the<br/>newest non-approval verdict status<br/>else waiting"]
  AP -- yes --> G3["green, status 'approved on sha'"]
  G3 --> RR{"attempt 1, same-repo PR,<br/>head still the PR head?"}
  RR -- yes --> LR["rerun the verdict job of every earlier run<br/>on that head whose last attempt failed<br/>(actions: write, this job only)"]
  RR -- "no (fork, Dependabot, moved head)" --> MN["stale red runs: maintainer reruns by hand"]
  LR --> RE["each rerun re-evaluates with the same rule<br/>green only on that same owner approval"]
  RE --> AM["required check green: GitHub auto-merge can fire (ADR-0051)"]
  R1 -. "approval later" .-> RV
```
