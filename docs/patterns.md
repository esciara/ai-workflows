# Workflow patterns

How-to notes for code that follows from the ADRs; the ADRs hold the decisions and win over this page.

## Target code into an agent job (works on private repos)

Why: an agent job has `permissions: {}` and no `GITHUB_TOKEN` ([ADR-0039](adr/0039-agent-jobs-consolidated.md)), so it cannot clone a private target repo, and `actions/checkout` must not run there (its `token` input defaults to `github.token`). Target content reaches an agent only from a non-agent job, as a same-run artifact. For a whole source tree (reproducer in WP6, later the analyst and implementer) that artifact is a tarball. Reference: `repro-context` and `reproduce` in `.github/workflows/triage.yml`.

- **Context job (no agent):** `permissions: contents: read` (plus only what it needs to read the item). `actions/checkout` of the default branch into `target/` with `persist-credentials: false`, so no token is written to `target/.git/config` and none ends up in the tarball. Then `tar -czf target.tgz -C target .`; plain `tar` stores symlinks as links and does not follow them.
- **Upload:** `actions/upload-artifact`, one artifact name per role (`repro-input`), with the prompt input next to it, `retention-days: 7`. Anyone who can read the repo's Actions runs can download it: the same people who can read the code.
- **Agent job:** `actions/download-artifact` with no `github-token` (a same-run artifact needs none), `mkdir work && tar -xzf target.tgz -C work && rm target.tgz`, then the agent runs in it through `CLAUDE_WORKING_DIR` (job env) and `./.ai-workflows/.github/actions/aiwf-agent`. If the agent runs commands, it passes `sandbox-settings` and the job follows [ADR-0037](adr/0037-command-running-agents-sandbox-scrub-and-trusted-gate.md) (bubblewrap, env scrub, token check); the policy test checks this.
- **Results out:** the agent returns JSON only; the orchestrator validates it against the schema before any write. No file from `work/` goes back to a job that holds a token.
- **Symlinks (follow-up):** the tree is attacker-shaped (a PR or the default branch of a repo that takes outside contributions). Any orchestrator code that reads files from it must skip symlinks and paths that resolve outside the tree. PR #134 adds that guard (`readable()` in `scripts/aiwf/review.py`) for the review context; once it is merged, reuse it for every reader of an unpacked tarball. WP6's context job reads no files from the tree today (it only tars it), so nothing calls the guard yet.
