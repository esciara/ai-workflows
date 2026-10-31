# ADR-0034 · Workflow A agent inputs and CI gate

- Status: Accepted
- Date: 2026-10-31
- Deciders: maintainer
- Alias: `D34`

## Context

Workflow A's review passes need the PR's code: the diff, touched files in full and callers of changed functions (`docs/spec.md`, Workflow A step 2). Agent jobs have `permissions: {}` (ADR-0018), so a non-agent job must collect the code and hand it over. The agent job also holds `CLAUDE_CODE_OAUTH_TOKEN` (ADR-0012), and every string it returns is published on the PR, which is a channel out to the public. Step 3 waits for CI, and the failure-mode table says "CI never completes: A waits up to its budget, then posts with verdict `human-review`", but there is no budget config until WP12 (guardrails). ADR-0007 says the gate waits on "all check runs on the head SHA except our own", but not how to tell which are ours: listing workflow runs needs `actions: read`, which the caller does not grant the review job (`templates/caller.yml`).

## Options considered

How agents see the code:

- Inline in the prompt, size-capped, no file tools: a `context` job with a read-only token builds one text file (PR description, linked issues, diff, touched files, `git grep` callers), capped at 120,000 characters, passed as a same-run artifact; the agent runs with `--tools StructuredOutput` only. No file access at all in the job that holds the token; but large PRs get a truncated view, and the agent cannot explore beyond what the context job picked.
- Read/Grep/Glob over a downloaded checkout: the agent explores the repo as it likes; but the Read tool can open any file on the runner, including `/proc/<pid>/environ` of the Claude process, which holds `CLAUDE_CODE_OAUTH_TOKEN`. Text in the PR or code could steer the agent (prompt injection) to read it and put it in a finding, which the orchestrator then posts on the PR. This is the same class of risk as the known issue "Bash-capable product agents share a job with `CLAUDE_CODE_OAUTH_TOKEN`" (`docs/known-issues.md`, bead `aiwf-3nh`), extended to read-only tools.
- Read limited to the workspace by Claude Code permission rules (e.g. `Read(./head/**)`): exploration without `/proc`; but it relies on path-rule matching in the CLI being exhaustive (symlinks in the PR, path tricks), unverified.

CI wait budget:

- Hard-coded 20 minutes, then `human-review`: matches the spec's failure mode now; not tunable per repo until WP12.
- A new config key now: tunable; but it pre-empts WP12's budget design.

Recognising our own check runs:

- Match our run ID in the check run's URL (`html_url` / `details_url` contain `/actions/runs/<GITHUB_RUN_ID>/`): needs only `checks: read`, which the caller grants.
- List workflow runs for the head SHA and drop those of our caller workflow: also catches older runs of our own caller; but needs `actions: read`, a caller change on every target repo.
- Match by check name (`review / …`): no API call; but names depend on the caller's job id, which the target repo picks.

The checkout-with-tools options were rejected because a token read is one injected instruction away, or rests on unverified path rules. The config key waits for WP12. Listing runs was rejected for the extra permission, name matching for depending on the caller's job ids.

## Decision

- Agents get the PR's code inline in the prompt and no file tools: the `context` job (`contents`, `pull-requests`, `issues` read, `checks: read`) builds the context file, capped at 120,000 characters with a visible truncation note, and uploads it as a same-run artifact; the agent job downloads it without a token and runs base-action with `--tools StructuredOutput`. The PR head is checked out in the `context` job only to be read as text (`git grep`); nothing from it is executed.
- The CI gate waits up to 20 minutes (a constant in `scripts/aiwf/review.py`), then the run continues with CI "still running (timed out)" and the verdict `human-review`. With no check run at all, it waits 90 seconds for CI to register before reporting "no checks".
- Our own check runs are those whose URL contains `/actions/runs/<GITHUB_RUN_ID>/`; all others on the head SHA count (narrowed by `required_checks`, ADR-0007).

Why: no file reads in the job that holds the Claude token, no new permission for target repos, and the spec's CI failure mode works now.

## Consequences

- Very large PRs are reviewed from a truncated context; the summary says so. The human-review rule for > 400 changed lines already covers most of them.
- Callers are found by a name-based `git grep`, so dynamic calls are missed.
- WP12 can turn the 20-minute constant into a budget key.
- Runs of our own caller for an earlier event on the same SHA are not excluded; they are complete by then (the caller's concurrency group runs them in order), so they only count as finished checks.
- WP6 and WP9 (Bash-capable agents) still need their own decision under bead `aiwf-3nh`; this ADR covers only the review passes.
