# PR Review & Bug-Fix Agent Workflows — Spec

Exported Oct 30, 2026 from the online doc: https://claude.ai/artifact/3rnF9qwMUZ1YhTc7MU31og

Two GitHub workflows, runnable on their own: **A** reviews every pull request and labels it with a merge verdict; **B** triages new issues, reproduces and diagnoses bugs, and — only after the maintainer says yes — fixes them through at most three implement/review rounds, then hands the PR to A. No agent ever merges or closes anything.

## Scope and source

| **TL;DR** — Both workflows reuse the reference spec's Review, Triage and Security features; their behaviour, labels and commands are new here. Feature and question issues, auto-merge and deployment are out of scope for now. |
| --- |

Both workflows are cut from the [AI Software Factory reference spec](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW). That spec names features but does not describe their behaviour, so the steps, labels and commands below are specified here for the first time; the stack stays agnostic, as in the source.

| Workflow | Features reused from the reference spec | New in this spec |
| --- | --- | --- |
| A — PR review | [REV-01](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965) AI review · [REV-02](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965) security review · [REV-04](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965) risk-tiered gate · [REV-08](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965) resolution reasons · [VER-01](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965) deterministic gates · [VER-02](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965) anti-slop lint · [VER-04](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965) repro suite per PR · [VER-06](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965) evidence packet · [MRG-07](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965) human-held merge | Verdict labels, one self-updating review comment, verdict rubric |
| B — Bug issue to fix PR | [INT-06](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965) untrusted input · [INT-08](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965) in-thread clarification · [TRI-01](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965) classification · [TRI-02](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965) dedup · [TRI-07](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965) already-fixed check · [TRI-08](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965) repro-first · [TRI-06](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965) readiness gate · [EXE-02](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965) sandbox per task · [EXE-06](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965) capped retries · [REV-03](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965) review-fix loop (≤ 3 rounds) | Ask-the-reporter loop, root-cause report, maintainer approval command, adversarial inner reviewer |
| Both | [SEC-01](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.6626) Rule of Two · [SEC-03](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.6626) reader/writer split · [SEC-05](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.6626) credentials at proxy · [CTL-03](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.6626) session record · [CTL-08](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.6626) kill switch · [CST-01](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.6626) time and turn limits | Shared label set and slash commands |

Out of scope for now: issues classified as features or questions (labelled, nothing more), auto-merge, and deployment.

## Workflow A — PR review and merge verdict

| **TL;DR** — Every non-draft PR gets parallel AI review passes, one self-updating comment and exactly one verdict label: `ai-review: merge`, `changes-requested` or `human-review`. A human always presses Merge. |
| --- |

[Diagram in the online doc: Workflow A · PR to verdict label, 4 parallel passes, rerun on push]

Four passes review the PR at once; only findings that survive the refute step count toward the verdict, and the review comes back on every new push.

**Trigger.** `pull_request` opened, reopened, synchronize (new push) or ready\_for\_review; drafts are skipped. A maintainer can force a run with a `/review` comment.

**Inputs.** The diff and PR description; the linked issue and its acceptance criteria; CI check results; repo review rules (`REVIEW.md`, `CODEOWNERS`, risk-path config); for PRs from Workflow B, the stored reproduction test.

**Steps at a glance**

| # | Step | Produces |
| --- | --- | --- |
| 1 | Mark in progress | `ai-review: pending` label |
| 2 | Gather context | Diff, touched files, callers, linked issue |
| 3 | Deterministic gates | CI status; red = blocking |
| 4 | Risk tier | `low`, `medium` or `high` |
| 5 | Review passes (4, in parallel) | Findings: correctness, security, anti-slop, tests |
| 6 | Verify findings | Confirmed findings by severity |
| 7 | Decide verdict | One verdict from the rubric |
| 8 | Publish | Review comment, inline notes, verdict label |
| 9 | Rerun on push | Findings marked resolved or still open |

**Steps**

1. **Mark in progress.** Set `ai-review: pending`, remove any previous verdict label.
2. **Gather context** with a read-only token: diff, touched files in full, callers of changed functions, linked issue.
3. **Deterministic gates (**[VER-01](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965)**).** Wait for required CI checks; a red check is a blocking finding by itself.
4. **Risk tier (**[REV-04](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965)**).** Match touched paths against the risk-path config: `low`, `medium` or `high` (auth, payments, migrations, infra, secrets, CI config).
5. **Review passes, in parallel**, each in a fresh context:
   - Correctness against the linked issue and acceptance criteria ([REV-01](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965)).
   - Security: injection, authz, secrets, unsafe deps ([REV-02](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965)).
   - Maintainability and anti-slop: duplication, dead code, needless verbosity, erosion ([VER-02](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965)).
   - Tests: new behaviour is covered; for a bug fix the repro test fails on the base branch and passes on the head ([VER-04](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965)).
6. **Verify findings.** A separate pass tries to refute each finding against the code; only confirmed ones are kept, each tagged `blocking`, `should-fix` or `nit`.
7. **Decide the verdict** with the rubric below.
8. **Publish**: create or update the single review comment (found by a hidden marker), submit one GitHub review (Request changes for changes-requested, otherwise Comment, never Approve) carrying the inline comments placed by the rule below, swap `ai-review: pending` for the verdict label.
9. **On every new push**, rerun; findings from the last run are marked resolved or still open, with the reason ([REV-08](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965)). For each finding the verify pass marks resolved that has an inline thread opened by A (a thread whose first comment's id A recorded in its state marker; never matched by author login, since every `GITHUB_TOKEN` workflow comments as `github-actions[bot]`), the orchestrator replies in that thread (`resolved in <short sha>: <reason>`, where `<reason>` is the schema-validated `reason` field of the verify output, not new free text) and then resolves it. A still-open finding keeps its thread open, with no reply. A never replies to or resolves a thread it did not open.

**Verdict rubric** (first matching row wins)

| Label | When | What the maintainer does |
| --- | --- | --- |
| `ai-review: changes-requested` | Any blocking finding, or a required CI check is red | Waits for the author to push |
| `ai-review: human-review` | Risk tier `high`, or the reviewer lacks context to judge (no linked issue (a repo may also accept a plan reference, config `linked_issue`), generated code, > 400 changed lines) | Reads the flagged files, decides |
| `ai-review: merge` | No blocking findings, CI green, tier `low` or `medium` | Skims the comment and merges |

**Review comment template**

```markdown
<!-- ai-review:summary v1 -->
## AI review — ✅ Merge  |  ❌ Changes requested  |  👀 Human review needed
**Risk tier:** medium · **CI:** green · **Commit reviewed:** abc1234

**Summary** — two or three sentences: what the PR does and whether it meets the issue.

| # | Severity | Where | Finding | Suggested fix |
|---|---|---|---|---|
| 1 | blocking | src/x.ts:42 | … | … |

**Tests:** repro test fails on base, passes on head.
**Not reviewed:** generated files, lockfiles.
**Since last run:** 2 resolved, 1 still open · 1 thread open.
```

**Where review comments go.** Each confirmed finding is placed by these rules; every finding also appears in the summary table, linked to its inline thread when it has one.

| Finding | Low- and medium-risk paths | High-risk paths |
| --- | --- | --- |
| One line or hunk, blocking or should-fix | Inline, with a GitHub `suggestion` block when the fix is a few lines | Inline |
| One line or hunk, nit | Summary only, collapsed | Inline |
| Same pattern in up to 5 places | Inline on the first, the others listed in that thread | Inline on the first, the others listed in that thread |
| Spread wide (more than 5 places or 3 files), or architecture | General | General |
| Something absent (missing test, migration, linked issue) | General | General |
| The PR itself (size, scope creep, description, CI red) | General | General |

**How it is sent.** The summary lives in the single self-updating review comment. Each run's verdict and new inline comments go out together as one GitHub review, at most one per run and only when there are new inline comments or the verdict changes: Request changes when the verdict is `changes-requested`, Comment otherwise, never Approve. When the verdict stops being `changes-requested`, the orchestrator dismisses its own earlier Request changes review (ADR-0016). A human approval therefore stays required, and branch protection can block the merge; a maintainer clears a false positive by dismissing the review.

**Open threads.** The summary's "Since last run" line ends with "N threads open": the unresolved review threads on the PR after this run's replies and resolves, A's and others'. The `verdict` job shows "N unresolved threads at <short sha>" in its step summary and in the description of the non-gating `verdict` commit status, as information only; it does not change the job's result. The gate is the repo ruleset's "Require conversation resolution", which is always current, while the count is only as fresh as the last `verdict` run.

## Workflow B — Bug issue to fix PR

| **TL;DR** — Only bugs go further. Each bug is reproduced (or the reporter is asked for details), its root cause is found, and nothing is coded until the maintainer replies `/fix`. The fix then gets at most 3 implement/review rounds before it becomes a PR for Workflow A. |
| --- |

[Diagram in the online doc: Workflow B · issue to fix PR, 2 human waits, 3-round cap]

The two highlighted steps are the only places the flow waits on a person, apart from an outsider's bug, which waits for the maintainer's `/reproduce` before B2; every other exit stops with a label rather than guessing.

**Steps at a glance**

| Step | What it does | Exit when it can't go on | Waits on |
| --- | --- | --- | --- |
| B1 Classify | Labels bug, feature or question; spots duplicates | Not a bug: label, stop | — |
| B2 Reproduce | Turns the report into a failing test in a sandbox | No repro: ask the reporter; ping, stale and close after `reporter_silence_days` (defaults 4/14/21) | Reporter (an outsider's bug: first the maintainer's `/reproduce`) |
| B3 Analyse | Root cause, blast radius, fix plan, risk and size | — | — |
| B4 Ask the maintainer | Posts the analysis, waits for a command | `/no-fix`: `fix: declined`, stop | Maintainer |
| B5 Fix loop | Implementer, then adversarial reviewer, up to 3 rounds | Round 3 rejected: draft PR, `fix: needs-maintainer` | — |
| B6 Open the PR | `Fixes #n` PR, handed to Workflow A | — | Maintainer merges |

**B1 — Classify (**[TRI-01](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965)**, **[TRI-02](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965)**, **[TRI-07](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965)**).** Trigger: `issues.opened`, or `/retriage` from a maintainer. The issue text is untrusted input ([INT-06](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965)): the classifier can read it and set labels, nothing else.

- Output one of `type: bug`, `type: feature`, `type: question`, with a one-line reason in a comment.
- Feature or question: stop. Low confidence: `triage: needs-human`, stop.
- Duplicate: comment with the link, label `triage: duplicate`, stop. Possible fix on the default branch: comment with a "possibly fixed by X" link, no label; B2's reproduction confirms or rejects it. Never close.

**B2 — Reproduce (**[TRI-08](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965)**, **[EXE-02](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965)**).** In a fresh sandbox on the default branch HEAD, with no secrets (except the model token, under the sandbox, scrub and gate of ADR-0037) and no push rights:

1. Extract steps, expected vs actual behaviour, versions and environment from the issue.
2. Turn them into an automated failing test (preferred) or, in a repo with no test harness, a script whose captured output shows the failure (enough to pass B2).
3. **Reproduced:** store the test and its output on the session record, label `triage: reproduced`, go to B3.
4. **Not reproduced:** comment to the reporter (`@author`) with what was tried, the environment used, what happened, and two to four specific questions; label `triage: needs-info`. A reply from the reporter restarts B2. After 2 unsuccessful requests (answers that still give no repro), label `triage: needs-human` and stop.

**Who starts B2 (v1, ADR-0037).** B2 runs code, so it starts on its own only when the issue's author is trusted: in `maintainers`, with write or admin permission, which covers the maintainer and any collaborator listed there. On anyone else's bug, B1 stops with `triage: needs-human` and a note until a maintainer comments `/reproduce`, which starts or restarts B2; after that, a reply from the reporter while the issue has `triage: needs-info` restarts B2 as above.

**Reporter silence.** Counted from the agent's last `triage: needs-info` comment. Any reply from the reporter stops the clock, removes `triage: no-response` and `stale`, and restarts B2. A maintainer can exempt an issue with `keep-open`: no ping, no `stale`, no close; `ai: off` and `ai: error` (a B2 rerun that failed, so a person looks first) exempt it the same way. The days come from `reporter_silence_days` (defaults 4, 14, 21, shown in the table below); they may be decimals, so a test config can shorten them to minutes. `actions/stale` reads `close − stale` as whole days, rounded down: under one day (test configs only) it closes the issue in the same run that labels it `stale`, after the stale comment. The stale and close days count from the issue's last update by anyone, so a maintainer's comment also pushes them back.

| Day (default) | What happens | Done by |
| --- | --- | --- |
| `ping` (4) | Comment mentioning each of `maintainers`: no reply from the reporter, decide whether the bug is worth pursuing without them; label `triage: no-response` | Orchestrator's daily scheduled job |
| `stale` (14) | Label `stale`, comment: closes in `close − stale` days (7) unless the requested details arrive | GitHub `actions/stale` |
| `close` (21) | Close as *not planned*, comment saying how to get it reopened | GitHub `actions/stale` |

**Where it runs.** No agent and no model token: the caller's daily schedule (and a manual run) calls a reusable workflow of this repo, whose two jobs hold only `issues: write` (no `actions: write`, so `actions/stale` keeps no state between runs) and run in this order in the same run. It runs only when `workflows.triage` is on and nothing stops runs (repo-level switch); each run has its own concurrency group, so runs never cancel each other:

1. **Ping** (orchestrator script). For each open issue with `triage: needs-info` and none of `triage: no-response`, `keep-open`, `ai: off`, `ai: error`: take the agent's latest needs-info comment (by its hidden marker; no such comment, e.g. a label set by hand: skip); if the issue's author has not commented since and it is at least `ping` days old, post one comment starting with the hidden marker `<!-- ai-workflows:no-response -->` that mentions each of `maintainers`: no reply from the reporter, decide whether the bug is worth pursuing without them; then label `triage: no-response`. It reads only labels, comment authors, dates and the markers, never issue text.
2. **Stale** ([`actions/stale`](https://github.com/actions/stale), pinned to a full commit SHA). It handles only issues already pinged (`triage: no-response`), so the order is always ping, stale, close, and a reply (whose B2 rerun removes `triage: no-response`) takes the issue out of its reach. It counts days since the issue's last update, and the ping is an update, so it runs after the ping with `stale − ping` days to the stale label and `close − stale` days to the close:

```yaml
- uses: actions/stale@<sha> # latest major at build time
  with:
    only-issue-labels: 'triage: needs-info,triage: no-response'   # plus the caller's extra scope labels, if any
    exempt-issue-labels: 'keep-open,ai: off,ai: error'
    days-before-issue-stale: <stale - ping>       # 10 with the defaults: day 14
    days-before-issue-close: <close - stale>      # 7 with the defaults: day 21
    stale-issue-label: 'stale'
    remove-stale-when-updated: true
    close-issue-reason: 'not_planned'
    stale-issue-message: >-
      No reply for <stale> days. This issue will close in <close - stale> days
      unless the details requested above are added.
    close-issue-message: >-
      Closed for lack of a reply. Add the requested details
      in a comment and a maintainer will reopen it.
    days-before-pr-stale: -1   # issues only
    days-before-pr-close: -1
```

The reusable workflow takes an optional list of extra labels an issue must also carry to be handled (empty in the caller template); the e2e slot callers use it to touch only their own test issues. The "Reporter silent" chat alert is wired with the slice's notifications (WP11b), not here.

**B3 — Analyse.** Runs in the same run as a B2 that reproduced, and again after every later B2 that reproduces. The analyst reads the stored reproduction (test, output, commands run) and the code at the commit B2 ran on. It runs no commands and has no file tools: a job with no agent puts the code into its prompt (the source files the test imports or that appear in the output, and their callers, capped in size as for A's passes, ADR-0034), so ADR-0037's exception does not extend to it. Those paths come from B2's output, which is untrusted: the job reads a path only when it is relative, resolves inside the checked-out tree and is a regular file (no symlink), and the step that reads them holds no token. Like B1 and B2, the analyst also reports any instructions it finds in what it reads (Guardrails). It returns:

- **Root cause:** the faulty code (file and line), and why it produces the observed behaviour.
- **Blast radius:** other callers or features affected.
- **Proposed fix:** approach, files to change, the regression test to keep, alternatives rejected.
- **Confidence** (high, medium, low) and **size** (S, M, L).

The orchestrator computes the **risk tier** from the files to change with A's path rules, and builds the file and line links itself, at the analysed commit, from the paths and lines the analyst returns: it links only a path that passes the same check as above and a whole-number line, with the link text escaped; any other path gets no link. The analyst's text is posted cleaned, as B2's is: no mentions, HTML, markers, links or images. Every B2 run that ends reproduced or not reproduced removes `triage: awaiting-maintainer` and `fix: declined` (a failed run, `ai: error`, changes neither). When it reproduces, B3 updates the analysis comment, its status back to waiting (an earlier decision line, with its guidance, stays under it as "previously"), and B4 labels `triage: awaiting-maintainer` again; when it does not, B2 sets that comment's status to "superseded by <run link>; `/reproduce` to analyse again".

**B4 — Ask the maintainer.** Post the analysis as one issue comment (template below, found by its hidden marker and updated in place by a later B3) that mentions each of `maintainers`, label `triage: awaiting-maintainer`, and wait. Only commands accepted per Commands (ADR-0005: in `maintainers` and with write or admin permission) count, and only while the issue has `triage: awaiting-maintainer`, read live from the API by the run that handles the command; a command at any other time changes nothing:

- `/fix` — go ahead as proposed.
- `/fix <guidance>` — go ahead, with the guidance added to the implementer's brief.
- `/no-fix <reason>` — label `fix: declined`, stop.

On either command the orchestrator first removes `triage: awaiting-maintainer`, then sets the comment's status line to who decided, with a link to their comment and, for `/fix <guidance>`, the guidance (cleaned like the analyst's text), where a later B5 finds it, reading it only from that bot-authored comment, found by its marker; `triage: reproduced` stays. `/fix` then starts B5. The "B4 analysis posted" chat alert is wired with the slice's notifications (WP11b), not here.

```markdown
<!-- ai-workflows:analysis -->
## Bug analysis
@esciara: reply `/fix`, `/fix <guidance>` or `/no-fix <reason>`.
**Risk tier:** low · **Confidence:** high · **Size:** S · **Run:** <run link>

**Root cause** — [src/x.py#L42](<link at the analysed commit>): why it produces the observed behaviour.
**Blast radius** — other callers or features affected.
**Proposed fix** — approach; files to change; the regression test to keep; alternatives rejected.

**Status:** waiting for `/fix` or `/no-fix`.  |  fix approved by @esciara ([comment](…)); guidance: …  |  fix declined by @esciara ([comment](…)).
```

**B5 — Fix loop, at most 3 rounds (**[REV-03](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965)**, **[EXE-06](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965)**).** Each round runs in a sandbox on branch `ai-fix/issue-<n>`:

1. **Implementer** writes the fix (round 1) or addresses the reviewer's findings (rounds 2–3). Exit condition: the repro test passes and the full test suite is green.
2. **Adversarial reviewer**, in a fresh context that never sees the implementer's reasoning, tries to break the fix: symptom patched instead of cause, missed edge cases, regressions, a weakened or deleted test, scope creep. It returns `approve` or `reject` with findings.
3. `approve` → B6. `reject` and fewer than 3 rounds → next round. `reject` after round 3 → escalate: comment on the issue with each round's findings, label `fix: needs-maintainer`, open the work as a **draft** PR so nothing is lost. To make sure the maintainer hears about it, the orchestrator assigns them the issue and the draft PR, requests their review on the PR, and mentions them in the comment; each of those sends a GitHub notification.

**B6 — Open the PR.** Body: `Fixes #<n>`, root cause, what changed, the repro test, and a round-by-round log. Label `ai-fix`. Opening it triggers **Workflow A**, whose reviewer is independent from the inner loop's; its verdict label decides what the maintainer does next.

## Shared components

| **TL;DR** — Each agent gets only the permissions its step uses; only the orchestrator writes to GitHub. Labels show people where an item stands, and four maintainer commands drive the flow. |
| --- |

**Roles and permissions** ([SEC-01](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.6626) Rule of Two, [SEC-03](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.6626) reader/writer split)

| Role | Reads untrusted text | Can write | Secrets | Used in |
| --- | --- | --- | --- | --- |
| Orchestrator | No (passes structured outputs only) | Labels, comments, branches, PRs via the workflow's GITHUB\_TOKEN, permissions scoped per job | CLAUDE\_CODE\_OAUTH\_TOKEN for the model; GITHUB\_TOKEN never handed to agent steps ([SEC-05](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.6626)) | A, B |
| Classifier | Yes | Nothing; returns JSON | None | B1 |
| Reproducer | Yes | Its own sandbox only | None; egress allowlist ([SEC-06](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.6626)) | B2 |
| Analyst | Repro output, code | Nothing; returns the report | None | B3 |
| Implementer | Brief, findings, code | Sandbox; pushes to `ai-fix/*` only, via the orchestrator | None | B5 |
| Adversarial reviewer | Diff, issue, repro | Nothing; returns verdict JSON | None | B5 |
| PR reviewer passes | Diff, PR text | Nothing; returns findings JSON | None | A |

**Labels**

| Label | Set by | Meaning |
| --- | --- | --- |
| `type: bug` / `feature` / `question` | B1 | Issue class |
| `triage: needs-info` | B2 | Waiting on the reporter; `maintainers` pinged at `ping` days (triage: no-response), stale at `stale`, closed at `close` (defaults 4/14/21) |
| `triage: reproduced` | B2 | Repro test stored |
| `triage: awaiting-maintainer` | B4 | Analysis posted, waiting for `/fix` |
| `triage: needs-human` / `duplicate` | B1, B2 | Agent stopped; a person takes over |
| `fix: declined` / `fix: needs-maintainer` | B4, B5 | Maintainer said no / 3 rounds failed; draft PR waiting for the maintainer |
| `ai-fix` | B6 | PR written by Workflow B |
| `ai-review: pending` / `merge` / `changes-requested` / `human-review` | A | Review running / verdict |
| `ai: off` | A maintainer | Kill switch on that issue or PR ([CTL-08](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.6626)) |

**Commands** — accepted only from users with write or admin permission: `/review` (A), `/retriage`, `/reproduce`, `/fix [guidance]`, `/no-fix <reason>` (B).

**Runtime.** Every AI step runs Claude Code inside GitHub Actions through [`anthropics/claude-code-action`](https://github.com/anthropics/claude-code-action), authenticated with the maintainer's Claude subscription, not an API key: run `claude setup-token` once on your machine and store the token as the repo secret `CLAUDE_CODE_OAUTH_TOKEN`. Each role above is a separate Claude Code run with its own allowed-tools list. Runs draw on the subscription's usage limits, shared with your own use, so the per-agent time and turn limits in Guardrails matter.

**Chat notifications.** GitHub stays where decisions are made (commands are typed there); chat only alerts the maintainer, with a link back. Slack, Telegram or both; a repo sets one or both and each alert goes to every channel set:

| Channel | Setup | Secrets |
| --- | --- | --- |
| Slack | Incoming webhook on a channel of your choice | `SLACK_WEBHOOK_URL` |
| Telegram | Bot from @BotFather, message sent with the Bot API `sendMessage` | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |

| Event | Message sent |
| --- | --- |
| New issue triaged (B1) | #n triaged as bug, feature or question, plus duplicate of #k or needs a person when so; links to the issue |
| B4 analysis posted | Bug #n analysed: root cause in one line; reply `/fix` or `/no-fix` on GitHub |
| Reporter silent `ping` days (B2) | #n: no reply from the reporter; worth pursuing? |
| `fix: needs-maintainer` (B5) | #n: fix failed after 3 rounds; draft PR #m |
| Verdict on a PR (A) | PR #m: merge, changes requested or human review needed |
| `ai: error` | Run failed on #n, with the run link |

**Per-repo configuration.** Everything that differs between repos lives in one file, so the workflows stay generic. Values below are examples; the agents read nothing repo-specific from anywhere else.

```yaml
# .github/ai-workflows.yml
maintainers: [esciara]          # B4 questions, assignments, pings, allowed command authors
default_branch: main
setup: npm ci                   # how an agent installs the project in its sandbox
test: npm test                  # B2 repro and B5 exit condition
risk_paths:
  high: ["src/auth/**", "migrations/**", ".github/**", "infra/**"]
limits:
  human_review_lines: 400
  fix_rounds: 3
  info_requests: 2
  triage_per_author_per_day: 3  # B1 runs per outside author (not in maintainers) per 24 hours; 0 = never
  triage_per_day: 20            # B1 runs for all outside authors per 24 hours; 0 = never
reporter_silence_days: {ping: 4, stale: 14, close: 21}
notify: slack                   # slack, telegram, or both: slack,telegram
fork_prs: on-command            # public repos: review fork PRs only after /review
```

**Deployment modes.** Where the workflows can run depends on your rights on the repo.

| Mode | Your role | What runs | Fork PRs |
| --- | --- | --- | --- |
| Maintainer | Owner or admin | Both workflows, installed in the repo | Private repo: none. Public repo: reviewed only after a maintainer's `/review`, using the base repo's secrets, with the fork's code read as text and never executed |
| Contributor | Write, triage or none | Installed in your fork, plus local runs; upstream use set by the ladder below | Not applicable |

Rights needed to install in maintainer mode: write access to add the workflow files and labels; admin (owner, on a personal repo) to add the secrets `CLAUDE_CODE_OAUTH_TOKEN` and the chat secrets, and to set the branch protection that lets Request changes block merges.

**Installing.** A target repo is set up from the install guide (`docs/install.md`) alone: copy the caller template (`templates/caller.yml`) to `.github/workflows/ai-workflows.yml` and the example config (`templates/ai-workflows.example.yml`) to `.github/ai-workflows.yml`, add the `CLAUDE_CODE_OAUTH_TOKEN` secret, run the workflow once by hand to create the labels. The caller pins every reusable workflow of this repo to a release: a full commit SHA with its version tag in a comment (`@<sha> # v0.x.y`), never a branch such as `@main`; upgrading means bumping that SHA. The guide recommends turning on "Require conversation resolution" (branch protection or ruleset) on the target repo, so threads A has not closed block the merge. For Workflow A, the repo setting "Allow GitHub Actions to create and approve pull requests" stays off: Workflow A only comments, requests changes and labels.

**Contributor ladder.** Before using it on someone else's repo, read its contribution guide and any AI policy, then go no higher than the policy allows.

| Level | What the AI does | Needs |
| --- | --- | --- |
| 0 · Local | Reviews your branch and analyses issues; results go to you only | Nothing from the repo |
| 1 · Your fork | Both workflows run on PRs inside your fork, before you open the PR upstream | Your fork |
| 2 · You post | AI drafts review replies and issue comments; you post them as yourself | Policy tolerates AI-assisted contributions |
| 3 · AI posts, labelled | AI comments upstream, clearly marked as AI | Policy explicitly allows AI comments |
| 4 · Installed upstream | Maintainers adopt the workflows (maintainer mode) | Maintainers agree |

## Guardrails, failure modes and metrics

| **TL;DR** — Limits are enforced in code: no agent merges or closes, every loop has a cap, and a kill switch stops everything. Success is measured by how often the maintainer agrees with the agents. |
| --- |

**Hard limits**

- Agents never merge, close, delete branches or edit CI config; the workflow token is never granted those permissions. The only automatic close is GitHub's stale action on silent needs-info issues (B2).
- Caps: 3 fix rounds, 2 info requests per issue, and a fixed time limit and turn limit per agent ([CST-01](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.6626)); hitting a fix or info cap escalates, and an agent that hits its time or turn limit fails the run, which gets `ai: error` like any failure. Triage caps for issues from authors not in `maintainers` (ADR-0058): `limits.triage_per_author_per_day` (default 3) and `limits.triage_per_day` (default 20), counted over a rolling 24 hours from the REST issue list (every issue opened counts, ordered by issue number); a capped issue runs no agent, gets `triage: needs-human` and one fixed comment, and is not retried automatically. Maintainers' issues and `/retriage` are never capped; 0 means outsiders are never triaged automatically.
- One summary comment per PR or issue, updated in place, so reruns never spam the thread.
- Text in issues, PRs and comments is data. Instructions found there are ignored and reported in the comment as a possible injection.
- `ai: off` on an item, or a repo-level switch, stops every run immediately ([CTL-08](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.6626)).

**Failure modes**

| Failure | Behaviour |
| --- | --- |
| Agent or sandbox crash | Label `ai: error`, comment with the run link, no retry loop |
| CI never completes | A waits up to its budget, then posts with verdict `human-review` |
| Reporter edits the issue mid-run | Run finishes, then B restarts from B1 on the new text |
| Maintainer pushes to `ai-fix/*` during B5 | Loop stops; the branch is the maintainer's |
| Fix makes repro pass but breaks other tests | Not an exit; counts as a failed round |

**Metrics** (logged per run on the session record)

| Metric | Tells you |
| --- | --- |
| Verdict agreement: share of `ai-review: merge` PRs merged unchanged; share of `changes-requested` the human also blocks | Whether the label can be trusted |
| Finding precision: share of findings resolved as valid ([REV-08](https://claude.ai/artifact/Xmwee4XtZwsKPWUStFADhW#mzxc5xwx2hg.2965)) | Review noise |
| Classification accuracy: labels kept vs changed by a human | B1 quality |
| Repro rate, and info requests per issue | B2 quality and issue quality |
| `/fix` rate after analysis | Whether root causes convince |
| Rounds per fix; escalation rate | Loop effectiveness |
| Time and cost per reviewed PR and per fixed bug | Whether it is worth running |

**Usage per run.** Every Workflow A run records exactly one JSON line of usage metrics on its session record: the run id, PR number, reviewed commit, verdict and wall time, and for each agent (each review pass and the verify pass) its duration, number of turns and token usage as reported by `claude-code-action`. It feeds the "Time and cost per reviewed PR" row and sets the per-agent time and turn limits from real numbers.

## Open questions

| **TL;DR** — All four earlier questions are decided: Claude Code in GitHub Actions on your subscription, a formal review that never approves, Slack or Telegram alerts, and repro scripts accepted where there is no test harness. |
| --- |

- [x] Runtime: GitHub Actions running a coding-agent action, or a GitHub App dispatching to a hosted agent runner? Decided: GitHub Actions with Claude Code, on your Claude subscription (see Runtime).
- [x] Should Workflow A also submit a formal GitHub review (Approve / Request changes), or only label and comment? Decided: a formal review that never approves, with inline vs general placement as in Workflow A.
- [x] Where do the maintainer's B4 requests reach you: the GitHub mention only, or also Slack or email? Decided: Slack or Telegram (see Chat notifications).
- [x] Repos with no test harness: is a reproduction script with captured output enough to pass B2? Decided: yes (see B2 step 2).
