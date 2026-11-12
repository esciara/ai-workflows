"""WP14 acceptance test. Done when: a second repo is set up from the guide alone in under 30 minutes.

What is automated (AIWF_E2E=1, no e2e slot: these tests check the released code, not the branch under test):

- the caller template pins every reusable workflow of esciara/ai-workflows to one release, `@<40-hex SHA> # vX.Y.Z`,
  never `@main`; the tag exists and points at that SHA, which is on `main`; the policy no longer exempts own refs
  (ADR-0040);
- the install guide `docs/install.md` covers the rights checklist and never tells a repo to use `@main`;
- the playground, set up from the guide as a second install, reviews a normal (non-`e2e/`) PR with the release:
  one summary comment, exactly one verdict label, reviewed by the release SHA, and its run records one metrics line.

Manual checklist (not automated; no writes to esciara/pyteleinfo from tests):

1. Before running the playground test, the maintainer updates the playground's normal caller
   (`.github/workflows/ai-workflows.yml`) from `templates/caller.yml` at the release, following `docs/install.md`,
   keeping only its e2e routing `if:` on the `config` job (ADR-0028).
2. On esciara/pyteleinfo, the maintainer follows `docs/install.md` alone, with a timer: start at reading the guide,
   stop when a test PR there gets its verdict label. Pass: under 30 minutes, no help from outside the guide. Record
   the time and any gap in the guide in the WP14 PR.
3. On esciara/pyteleinfo, "Allow GitHub Actions to create and approve pull requests" is off and the run used the
   pinned release (the summary comment's state block names the release SHA).
4. First usage numbers: the metrics lines of the first reviewed PRs on esciara/pyteleinfo (at least 3) are
   summarised (turns, duration, tokens per agent and per PR) under "Usage limits" in `docs/plan.md`, which settles
   that open point or says what to change in the time and turn limits.
"""

from __future__ import annotations

import base64
import os
import re

import playground as pg
from aiwf import policy
from test_wp2 import check_review, head_sha

AIWF_REPO = os.environ.get("AIWF_REPO", "esciara/ai-workflows")
TEMPLATE = pg.ROOT / "templates" / "caller.yml"
GUIDE = pg.ROOT / "docs" / "install.md"
OWN_USES_RE = re.compile(r"^\s*uses:\s*esciara/ai-workflows/(\.github/workflows/[\w.-]+\.yml)@(\S+)[ \t]*(#.*)?$", re.M)
SHA_RE = re.compile(r"[0-9a-f]{40}")
TAG_RE = re.compile(r"#\s*(v\d+\.\d+\.\d+)\s*$")
APPROVE_SETTING = "Allow GitHub Actions to create and approve pull requests"
GUIDE_MUST_NAME = {  # rights checklist: what a second repo needs, each named in the guide
    "the model token secret": "CLAUDE_CODE_OAUTH_TOKEN",
    "how to get the model token": "claude setup-token",
    "the caller template": "templates/caller.yml",
    "where the caller goes": ".github/workflows/ai-workflows.yml",
    "the config template": "templates/ai-workflows.example.yml",
    "where the config goes": ".github/ai-workflows.yml",
    "the setting that stays off": APPROVE_SETTING,
}
VERDICTS = {"ai-review: merge", "ai-review: changes-requested", "ai-review: human-review"}
REVIEW_TIMEOUT = 1800  # CI wait + 4 passes + verify, on a cold runner


def release_pin(text: str) -> tuple[str, str, set[str]]:
    """(SHA, tag, called workflow paths) of a caller whose own reusable refs all pin one release; fails otherwise."""
    uses = OWN_USES_RE.findall(text)
    assert uses, "no `uses: esciara/ai-workflows/...` line found"
    pins = set()
    for path, ref, comment in uses:
        assert SHA_RE.fullmatch(ref), f"{path} is pinned to {ref!r}, not a full commit SHA"
        tag = TAG_RE.search(comment or "")
        assert tag, f"{path}@{ref[:7]} has no `# vX.Y.Z` version comment"
        pins.add((ref, tag.group(1)))
    assert len(pins) == 1, f"the caller mixes releases: {sorted(pins)}"
    (sha, tag), = pins
    return sha, tag, {path for path, _, _ in uses}


def tag_commit(tag: str) -> str:
    obj = pg.api(f"repos/{AIWF_REPO}/git/ref/tags/{tag}")["object"]
    if obj["type"] == "tag":  # annotated tag: dereference to its commit
        obj = pg.api(f"repos/{AIWF_REPO}/git/tags/{obj['sha']}")["object"]
    return obj["sha"]


def test_caller_template_pins_every_own_workflow_to_a_release_on_main():
    text = TEMPLATE.read_text()
    assert "@main" not in text, "templates/caller.yml still mentions @main"
    sha, tag, paths = release_pin(text)
    assert tag_commit(tag) == sha, f"tag {tag} does not point at the pinned SHA {sha[:7]}"
    status = pg.api(f"repos/{AIWF_REPO}/compare/{sha}...main")["status"]
    assert status in ("ahead", "identical"), f"release {tag} ({sha[:7]}) is not on main (compare: {status})"
    for path in paths:
        pg.api(f"repos/{AIWF_REPO}/contents/{path}?ref={sha}")  # 404 fails the test: the release lacks the workflow
    assert not policy.is_exempt("esciara/ai-workflows/.github/workflows/review.yml@main"), \
        "the workflow policy still exempts own reusable refs (ADR-0040: dropped in WP14)"


def test_install_guide_covers_the_rights_checklist_and_pins_releases():
    assert GUIDE.is_file(), "docs/install.md is missing"
    guide = GUIDE.read_text()
    missing = [what for what, text in GUIDE_MUST_NAME.items() if text not in guide]
    assert not missing, f"docs/install.md does not name: {missing}"
    setting_lines = [line for line in guide.splitlines() if APPROVE_SETTING in line]
    assert any(re.search(r"\b(off|unticked|unchecked|disabled)\b", line, re.I) for line in setting_lines), \
        f"docs/install.md does not say {APPROVE_SETTING!r} stays off"
    assert re.search(r"run (the|this) workflow|workflow_dispatch", guide, re.I), \
        "docs/install.md does not say to run the workflow once by hand (labels, ADR-0023)"
    assert "@main" not in guide, "docs/install.md tells a repo to use @main"
    assert re.search(r"\b(tag|release)\b", guide, re.I) and re.search(r"\bSHA\b", guide), \
        "docs/install.md does not explain pinning to a release SHA"


def release_review_run(sha: str) -> dict:
    """The completed pull_request run of the playground's normal caller for head `sha` (a new branch: any run is ours)."""

    def find() -> int | None:
        runs = pg.api(f"repos/{pg.REPO}/actions/runs?event=pull_request&head_sha={sha}&per_page=50")["workflow_runs"]
        hits = [r for r in runs if r["name"] == pg.WORKFLOW]
        return min(hits, key=lambda r: (r["created_at"], r["id"]))["id"] if hits else None

    run_id = pg.poll(find, f"the {pg.WORKFLOW} pull_request run for {sha[:7]}", timeout=REVIEW_TIMEOUT)

    def done() -> dict | None:
        run = pg.api(f"repos/{pg.REPO}/actions/runs/{run_id}")
        return run if run["status"] == "completed" else None

    run = pg.poll(done, f"run {run_id} to complete", timeout=REVIEW_TIMEOUT)
    jobs = pg.jobs(run_id)
    print(f"review of {sha[:7]}: run {run_id} {run['html_url']} -> {run['conclusion']}, jobs {jobs}")
    assert run["conclusion"] == "success", jobs
    assert jobs.get("review / publish") == "success", jobs
    return run


def test_playground_set_up_from_the_guide_reviews_a_pr_with_the_release(tmp_path):
    sha, tag, paths = release_pin(TEMPLATE.read_text())

    # The second install, as the guide sets it up (manual checklist step 1).
    perms = pg.api(f"repos/{pg.REPO}/actions/permissions/workflow")
    assert perms["can_approve_pull_request_reviews"] is False, f"{APPROVE_SETTING!r} is on in {pg.REPO}"
    secrets = {s["name"] for s in pg.api(f"repos/{pg.REPO}/actions/secrets?per_page=100")["secrets"]}
    assert "CLAUDE_CODE_OAUTH_TOKEN" in secrets, f"{pg.REPO} lacks the CLAUDE_CODE_OAUTH_TOKEN secret"
    caller = pg.api(f"repos/{pg.REPO}/contents/.github/workflows/ai-workflows.yml")
    caller_sha, caller_tag, caller_paths = release_pin(base64.b64decode(caller["content"]).decode())
    assert (caller_sha, caller_tag) == (sha, tag), f"playground caller pins {caller_tag}, the template {tag}"
    assert paths <= caller_paths, f"playground caller does not call {sorted(paths - caller_paths)}"
    have = {lb["name"] for lb in pg.api(f"repos/{pg.REPO}/labels?per_page=100")}
    assert VERDICTS | {"ai-review: pending"} <= have, f"labels missing: {sorted(VERDICTS - have)}"

    # A normal PR (not `e2e/`): the normal caller reviews it with the release.
    with pg.throwaway_pr("[e2e] WP14 install from the guide", e2e=False) as pr:
        number = pr["number"]
        head = head_sha(number)
        run = release_review_run(head)
        review = check_review(number, head, sha)  # one summary comment, one verdict label, state names the release

        lines = pg.metrics_lines(run["id"], tmp_path)
        assert len(lines) == 1, f"run {run['id']}: expected exactly one metrics line, got {len(lines)}"
        pg.check_metrics(lines[0], run, number, head, sha, review["verdict"])
