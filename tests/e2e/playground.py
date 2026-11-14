"""Helpers for end-to-end acceptance tests against the playground repo (network, real GitHub)."""

from __future__ import annotations

import base64
import calendar
import contextlib
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar

import pytest

from aiwf import e2eslot

ROOT = Path(__file__).resolve().parents[2]
REPO = os.environ.get("AIWF_E2E_REPO", "esciara/ai-workflows-playground")
FORK = os.environ.get("AIWF_E2E_FORK", "opinionated-digital-center/ai-workflows-playground")  # outsider fork (WP4)
WORKFLOW = "AI workflows"  # name of the caller workflow in the target repo
BOT = "github-actions[bot]"
FIXTURE_LABEL = "test-fixture"
RUN_TIMEOUT = int(os.environ.get("AIWF_E2E_TIMEOUT", "600"))
POLL_INTERVAL = int(os.environ.get("AIWF_E2E_POLL", "5"))

T = TypeVar("T")


def held_slot() -> int:
    """The e2e slot this run holds (ADR-0056); fails the test without one."""
    try:
        return e2eslot.held()[0]
    except e2eslot.NoSlot as e:
        pytest.fail(str(e), pytrace=False)


def __getattr__(name: str) -> str:
    """Names of the held slot, read when used (the controller takes the slot after this module is imported):
    E2E_WORKFLOW (its caller-e2e-<n>.yml), E2E_NOTIFY_WORKFLOW (its notify-e2e-<n>.yml), E2E_LABEL (`e2e-target-<n>`,
    routes an item to that caller). Without a slot, placeholders that match no workflow or label."""
    names = {"E2E_WORKFLOW": e2eslot.workflow_name, "E2E_NOTIFY_WORKFLOW": e2eslot.notify_workflow_name,
             "E2E_LABEL": e2eslot.label}
    if name not in names:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    try:
        return names[name](e2eslot.held()[0])
    except e2eslot.NoSlot:
        return f"{name} (no e2e slot held)"


def gh(args: list[str], as_tester: bool = False, as_agent: bool = False, as_maintainer: bool = False,
       tester_repo: str | None = None) -> str:
    """Run gh: reads with the local gh login; writes as the agent App (ADR-0031), the tester App, or the maintainer
    through scripts/dev/as-maintainer (comments, reviews, dispatch on the playground only). API failures fail the test.
    `tester_repo` picks the tester App installation (default: the playground's; FORK for writes to the fork)."""
    wrapper = "as-tester" if as_tester else "as-maintainer" if as_maintainer else "as-agent" if as_agent else None
    cmd = [str(ROOT / "scripts" / "dev" / wrapper), *args] if wrapper else ["gh", *args]
    if wrapper == "as-agent":
        cmd.insert(1, "gh")
    env = {**os.environ, "AI_WORKFLOWS_TESTER_REPO": tester_repo} if as_tester and tester_repo else None
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        pytest.fail(f"GitHub call failed (not a pass): {' '.join(args[:3])}: {proc.stderr.strip()[:300]}", pytrace=False)
    return proc.stdout


def api(path: str, *fields: str, method: str = "GET", as_tester: bool = False, as_maintainer: bool = False,
        tester_repo: str | None = None) -> Any:
    """GETs read with the local gh login; other methods run as the tester, the maintainer, or else the agent App."""
    args = ["api", "-X", method, path]
    for f in fields:
        args += ["-f", f]
    out = gh(args, as_tester=as_tester, as_maintainer=as_maintainer, as_agent=method != "GET", tester_repo=tester_repo)
    return json.loads(out) if out.strip() else None


def poll(check: Callable[[], T | None], what: str, timeout: int = RUN_TIMEOUT) -> T:
    """Call `check` until it returns something other than None; time out as a failure, never a pass."""
    deadline = time.monotonic() + timeout
    while True:
        value = check()
        if value is not None:
            return value
        if time.monotonic() > deadline:
            pytest.fail(f"timed out after {timeout}s waiting for {what} (not a pass)", pytrace=False)
        time.sleep(POLL_INTERVAL)


def comment(number: int, body: str, as_tester: bool = False) -> dict[str, Any]:
    """Post a comment as the maintainer (or the tester); returns its id, created_at and author."""
    c = api(f"repos/{REPO}/issues/{number}/comments", f"body={body}", method="POST", as_tester=as_tester,
            as_maintainer=not as_tester)
    return {"id": c["id"], "created_at": c["created_at"], "user": c["user"]["login"]}


def run_for(cmt: dict[str, Any], title: str, workflow: str = WORKFLOW) -> int:
    """ID of the issue_comment run of the caller `workflow` created at or after the comment, for this item."""

    def find() -> int | None:
        runs = api(f"repos/{REPO}/actions/runs?event=issue_comment&created=%3E%3D{cmt['created_at']}&per_page=50")
        hits = [
            r for r in runs["workflow_runs"]
            if r["name"] == workflow and r["display_title"] == title and r["created_at"] >= cmt["created_at"]
        ]
        return min(hits, key=lambda r: (r["created_at"], r["id"]))["id"] if hits else None

    return poll(find, f"the issue_comment run for comment {cmt['id']}")


def dispatch(ref: str = "main") -> int:
    """Start the caller workflow by workflow_dispatch on `ref`; returns the new run's ID."""
    wf = next(w for w in api(f"repos/{REPO}/actions/workflows")["workflows"] if w["name"] == WORKFLOW)
    out = gh(["api", "-X", "POST", f"repos/{REPO}/actions/workflows/{wf['id']}/dispatches",
              "-f", f"ref={ref}", "-F", "return_run_details=true"], as_maintainer=True)  # the App has no actions write
    return json.loads(out)["workflow_run_id"]


def completed(run_id: int) -> dict[str, Any]:
    """The finished run. GitHub can mark a run completed while a job's conclusion is still null, so wait for those too."""

    def done() -> dict[str, Any] | None:
        run = api(f"repos/{REPO}/actions/runs/{run_id}")
        if run["status"] != "completed" or None in jobs(run_id).values():
            return None
        return run

    return poll(done, f"run {run_id} to complete")


def jobs(run_id: int) -> dict[str, str]:
    """Job name -> conclusion, e.g. {'review / gate': 'skipped'}."""
    data = api(f"repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100")
    return {j["name"]: j["conclusion"] for j in data["jobs"]}


def ensure_label(name: str | None = None, color: str = "5319e7", description: str | None = None) -> None:
    """Create the label if missing; default: the held slot's `e2e-target-<n>`."""
    if name is None:
        n = held_slot()
        name, description = e2eslot.label(n), f"e2e: runs ai-workflows@e2e-target-{n}"
    description = description or ""
    if not any(lb["name"] == name for lb in api(f"repos/{REPO}/labels?per_page=100")):
        api(f"repos/{REPO}/labels", f"name={name}", f"color={color}", f"description={description}", method="POST")


def _labels(e2e: bool, n: int | None = None) -> list[str]:
    """`test-fixture`, plus slot `n`'s label (default: the held slot) when e2e."""
    if not e2e:
        return [FIXTURE_LABEL]
    n = n or held_slot()
    ensure_label(e2eslot.label(n), description=f"e2e: runs ai-workflows@e2e-target-{n}")
    return [FIXTURE_LABEL, e2eslot.label(n)]


def open_issue(title: str, body: str, *, e2e: bool, as_tester: bool = False) -> dict[str, Any]:
    """New issue, labels set at creation (so the `opened` event already carries `e2e-target-<n>` when `e2e`)."""
    want = _labels(e2e)
    issue = api(f"repos/{REPO}/issues", f"title={title}", f"body={body}", *[f"labels[]={lb}" for lb in want],
                method="POST", as_tester=as_tester)
    got = {lb["name"] for lb in issue["labels"]}
    if not set(want) <= got:  # GitHub silently drops labels an author may not set
        pytest.fail(f"issue #{issue['number']} created without labels {sorted(set(want) - got)} (not a pass)", pytrace=False)
    return {"number": issue["number"], "title": issue["title"]}


def reusable_issue(title: str, body: str, *, e2e: bool) -> dict[str, Any]:
    """The open test-fixture issue titled `<title> (slot <n>)` when `e2e` (the slot number keeps per-slot titles unique,
    so triage dedup does not label them duplicates; old issues without it are left open and ignored) with the held
    slot's `e2e-target-<n>` label, so its comments reach that slot's caller; created once per slot and reused (never
    deleted)."""
    if e2e:
        title = f"{title} (slot {held_slot()})"
        body = f"{body}\n\n(fixture for e2e slot {held_slot()})"  # distinct body too: dedup compares bodies, not only titles
    found = api(f"repos/{REPO}/issues?labels={FIXTURE_LABEL}&state=open&per_page=100")
    for issue in found:
        has_slot = not e2e or e2eslot.label(held_slot()) in {lb["name"] for lb in issue["labels"]}
        if issue["title"] == title and "pull_request" not in issue and has_slot:
            return {"number": issue["number"], "title": issue["title"]}
    return open_issue(title, body, e2e=e2e)


def pr_branch(*, e2e: bool, wp: str = "", slug: str = "", slot: int | None = None) -> str:
    """Unique head branch for a test PR. e2e PRs use `e2e/<n>/<wp>-<slug>-<ns>` for slot `n` (default: the held
    slot): the playground routes PRs whose head ref starts with `e2e/<n>/` to caller-e2e-<n>.yml from the first
    `opened` event on (labels cannot be set at creation)."""
    if not e2e:
        return f"test-pr-{time.time_ns()}"  # never `e2e/`: the normal caller handles it
    if not re.fullmatch(r"wp\d+", wp) or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
        raise ValueError(f"e2e PR branch needs wp like 'wp2' and a lowercase slug, got {wp!r}, {slug!r}")
    return f"{e2eslot.branch_prefix(slot or held_slot())}{wp}-{slug}-{time.time_ns()}"


@contextlib.contextmanager
def throwaway_pr(title: str, *, e2e: bool, wp: str = "", slug: str = "", base: str | None = None,
                 draft: bool = False, slot: int | None = None) -> Iterator[dict[str, Any]]:
    """A test-fixture PR on its own branch from `base` (default branch if None); branch deleted, PR closed on exit.

    e2e PRs come from an `e2e/<n>/<wp>-<slug>-…` branch (slot `n`: `slot`, default the held one), so every PR event
    routes to slot n's caller, `opened` included. Labels (`test-fixture`, plus `e2e-target-<n>` when e2e) are added right after creation, since the pulls API cannot
    set them; comment events on the PR carry no head ref and route by that label. A `draft` PR's events start no
    review (only a maintainer's `/review` does).
    """
    branch = pr_branch(e2e=e2e, wp=wp, slug=slug, slot=slot)
    base = base or api(f"repos/{REPO}")["default_branch"]
    sha = api(f"repos/{REPO}/git/ref/heads/{base}")["object"]["sha"]
    api(f"repos/{REPO}/git/refs", f"ref=refs/heads/{branch}", f"sha={sha}", method="POST")
    pr = None
    try:
        api(f"repos/{REPO}/contents/e2e/{branch.replace('/', '-')}.md", f"message=test: e2e throwaway {branch}",
            "content=dGhyb3dhd2F5Cg==", f"branch={branch}", method="PUT")  # "throwaway\n"
        title = f"{title} ({branch})"
        pr = json.loads(gh(["api", "-X", "POST", f"repos/{REPO}/pulls", "-f", f"title={title}", "-f", f"head={branch}",
                            "-f", f"base={base}", "-f",
                            "body=Throwaway e2e PR from esciara/ai-workflows tests; closed by its teardown.",
                            "-F", f"draft={str(draft).lower()}"], as_agent=True))
        api(f"repos/{REPO}/issues/{pr['number']}/labels", *[f"labels[]={lb}" for lb in _labels(e2e, slot)],
            method="POST")
        yield {"number": pr["number"], "title": title, "branch": branch}
    finally:
        api(f"repos/{REPO}/git/refs/heads/{branch}", method="DELETE")
        if pr and api(f"repos/{REPO}/pulls/{pr['number']}")["state"] == "open":
            api(f"repos/{REPO}/pulls/{pr['number']}", "state=closed", method="PATCH")


@contextlib.contextmanager
def fork_pr(title: str, files: list[tuple[str, str]], *, wp: str, slug: str) -> Iterator[dict[str, Any]]:
    """A test-fixture PR from FORK into REPO, opened by the tester App (an outsider, never a maintainer); fork branch
    deleted and PR closed on exit. `files` are (path, text) pairs, one commit each, pushed before the PR is opened.

    The branch starts from the fork's default branch and is not named `e2e/`: fork PRs never route by prefix, so the
    `opened` event goes to the normal caller; the held slot's `e2e-target-<n>` is labelled right after creation (as the
    agent App), and later events on the PR route to caller-e2e-<n>.yml. The fork needs the tester App installed with contents write.
    """
    base = api(f"repos/{REPO}")["default_branch"]
    fork_base = api(f"repos/{FORK}")["default_branch"]
    branch = f"{wp}-{slug}-{time.time_ns()}"
    sha = api(f"repos/{FORK}/git/ref/heads/{fork_base}")["object"]["sha"]
    api(f"repos/{FORK}/git/refs", f"ref=refs/heads/{branch}", f"sha={sha}", method="POST", as_tester=True,
        tester_repo=FORK)
    pr = None
    try:
        for path, text in files:
            fork_put(path, branch, text, f"test: e2e fork PR seed {path}")
        title = f"{title} ({branch})"
        # maintainer_can_modify=false: the tester App may not grant fork collaboration (422 `fork_collab`).
        pr = json.loads(gh(["api", "-X", "POST", f"repos/{REPO}/pulls", "-f", f"title={title}",
                            "-f", f"head={FORK.split('/')[0]}:{branch}", "-f", f"base={base}", "-f",
                            "body=Throwaway e2e fork PR from esciara/ai-workflows tests; closed by its teardown.",
                            "-F", "maintainer_can_modify=false"], as_tester=True))
        api(f"repos/{REPO}/issues/{pr['number']}/labels", *[f"labels[]={lb}" for lb in _labels(True)], method="POST")
        yield {"number": pr["number"], "title": title, "branch": branch}
    finally:
        api(f"repos/{FORK}/git/refs/heads/{branch}", method="DELETE", as_tester=True, tester_repo=FORK)
        if pr and api(f"repos/{REPO}/pulls/{pr['number']}")["state"] == "open":
            api(f"repos/{REPO}/pulls/{pr['number']}", "state=closed", method="PATCH")


def fork_put(path: str, branch: str, text: str, message: str) -> str:
    """Commit `text` to `path` on the fork's `branch` as the tester App (create or update); returns the commit SHA."""
    fields = [f"message={message}", f"branch={branch}", f"content={base64.b64encode(text.encode()).decode()}"]
    found = subprocess.run(["gh", "api", f"repos/{FORK}/contents/{path}?ref={branch}", "--jq", ".sha"],
                           capture_output=True, text=True)  # 404: a new file
    if found.returncode == 0 and found.stdout.strip():
        fields.append(f"sha={found.stdout.strip()}")
    return api(f"repos/{FORK}/contents/{path}", *fields, method="PUT", as_tester=True, tester_repo=FORK)["commit"]["sha"]


METRICS_ARTIFACT = "ai-workflows-metrics"  # spec: Usage per run; artifact and file per ADR-0052
METRICS_FILE = "metrics.jsonl"


def metrics_lines(run_id: int, tmp: Path) -> list[str]:
    """The non-empty lines of the run's metrics file, from its METRICS_ARTIFACT artifact (exactly one artifact)."""
    arts = [a for a in api(f"repos/{REPO}/actions/runs/{run_id}/artifacts?per_page=100")["artifacts"]
            if a["name"] == METRICS_ARTIFACT]
    assert len(arts) == 1, f"run {run_id}: expected one `{METRICS_ARTIFACT}` artifact, got {len(arts)}"
    gh(["run", "download", str(run_id), "-R", REPO, "-n", METRICS_ARTIFACT, "-D", str(tmp)])
    files = list(tmp.rglob("*"))
    assert [f.name for f in files if f.is_file()] == [METRICS_FILE], f"artifact holds {[f.name for f in files]}"
    return [line for line in (tmp / METRICS_FILE).read_text().splitlines() if line.strip()]


METRICS_AGENTS = {"correctness", "security", "maintainability", "tests", "verify"}  # the 4 passes + verify
METRICS_AGENT_INTS = ("duration_ms", "num_turns", "input_tokens", "output_tokens", "cache_read_input_tokens",
                      "cache_creation_input_tokens")
METRICS_MAX_TURNS = 3  # every Workflow A agent step runs with --max-turns 3 (ADR-0050)


def _ts(stamp: str) -> float:
    return calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))


def check_metrics(line: str, run: dict[str, Any], pr: int, sha: str, aiwf_sha: str, verdict: str) -> dict[str, Any]:
    """One metrics line (spec: Usage per run) describes this run, this PR and commit, and every agent's usage."""
    m = json.loads(line)
    assert isinstance(m, dict), f"metrics line is not a JSON object: {line[:200]}"
    assert m.get("v") == 1 and m.get("workflow") == "review", m
    assert m.get("repo") == REPO, m
    assert m.get("run_id") == run["id"] and m.get("run_attempt") == run["run_attempt"], m
    assert m.get("pr") == pr and m.get("head_sha") == sha and m.get("aiwf_sha") == aiwf_sha, m
    assert m.get("verdict") == verdict, f"metrics verdict {m.get('verdict')!r}, label {verdict!r}"
    wall = _ts(run["updated_at"]) - _ts(run["run_started_at"])
    assert isinstance(m.get("duration_s"), (int, float)) and 0 < m["duration_s"] <= wall + 60, (m.get("duration_s"), wall)
    agents = m.get("agents")
    assert isinstance(agents, list), m
    names = [a.get("agent") for a in agents]
    assert sorted(names) == sorted(METRICS_AGENTS), f"agents {names}, expected one entry each for {sorted(METRICS_AGENTS)}"
    for a in agents:
        for field in METRICS_AGENT_INTS:
            value = a.get(field)
            assert isinstance(value, int) and not isinstance(value, bool) and value >= 0, (a["agent"], field, value)
        assert 1 <= a["num_turns"] <= METRICS_MAX_TURNS, a
        assert a["duration_ms"] > 0 and a["output_tokens"] > 0, a
        assert a["input_tokens"] + a["cache_read_input_tokens"] + a["cache_creation_input_tokens"] > 0, a
        assert isinstance(a.get("cost_usd"), (int, float)) and not isinstance(a["cost_usd"], bool), a  # notional
    print(f"metrics for run {run['id']}: {line}")
    return m


# Issues opened by the outside reporter (tester App) and their triage runs (WP5, WP11b).


def close_issue(number: int) -> None:
    """Close as "not planned" (never deleted), so later runs and dedup corpora do not see it as an open duplicate."""
    api(f"repos/{REPO}/issues/{number}", "state=closed", "state_reason=not_planned", method="PATCH")


def close_left_over(prefix: str, keep: str) -> None:
    """Close open test-fixture issues whose title starts with `prefix` but lacks this run's tag `keep` (crashed runs)."""
    for issue in api(f"repos/{REPO}/issues?labels={FIXTURE_LABEL}&state=open&per_page=100"):
        if issue["title"].startswith(prefix) and keep not in issue["title"] and "pull_request" not in issue:
            close_issue(issue["number"])


def open_as_reporter(title: str, body: str) -> dict[str, Any]:
    """Open an issue as the tester App (the outside reporter), routed to the held slot's caller from its `opened`
    event; adds created_at and html_url."""
    if not os.environ.get("AI_WORKFLOWS_TESTER_APP_ID"):
        pytest.fail("AI_WORKFLOWS_TESTER_APP_ID is not set; cannot open issues as the tester App (not a pass)",
                    pytrace=False)
    issue = open_issue(title, body, e2e=True, as_tester=True)
    full = api(f"repos/{REPO}/issues/{issue['number']}")
    author = full["user"]["login"]
    assert author.endswith("[bot]") and author != BOT, f"#{issue['number']} not opened by the tester App: {author}"
    return {**issue, "created_at": full["created_at"], "html_url": full["html_url"]}


def issues_run(issue: dict[str, Any], workflow: str) -> dict[str, Any]:
    """The completed `issues` run of the caller `workflow` for this issue (opened at or after its creation)."""

    def find() -> int | None:
        runs = api(f"repos/{REPO}/actions/runs?event=issues&created=%3E%3D{issue['created_at']}&per_page=50")
        hits = [
            r for r in runs["workflow_runs"]
            if r["name"] == workflow and r["display_title"] == issue["title"] and r["created_at"] >= issue["created_at"]
        ]
        return min(hits, key=lambda r: (r["created_at"], r["id"]))["id"] if hits else None

    run = completed(poll(find, f"the {workflow} issues run for #{issue['number']}"))
    print(f"#{issue['number']} {issue['html_url']}: run {run['id']} {run['html_url']} -> {run['conclusion']}, "
          f"jobs {jobs(run['id'])}")
    return run


# Chat notifications (WP11a, WP11b): the notify step prints one `AIWF_NOTIFY_RESULT {json}` line per message sent.

NOTIFY_RESULT_PREFIX = "AIWF_NOTIFY_RESULT "


def job_log(job_id: int) -> str:
    return gh(["api", "--allow-escape-sequences", f"repos/{REPO}/actions/jobs/{job_id}/logs"])


def notify_results(log: str) -> list[dict[str, Any]]:
    out = []
    for line in log.splitlines():
        at = line.find(NOTIFY_RESULT_PREFIX)
        if at >= 0:
            out.append(json.loads(line[at + len(NOTIFY_RESULT_PREFIX):]))
    return out


def http_status(url: str) -> int:
    """Anonymous GET, as someone clicking the link in the chat would do (public playground)."""
    req = urllib.request.Request(url, headers={"User-Agent": "ai-workflows-e2e"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
