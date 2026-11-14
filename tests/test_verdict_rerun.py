"""`verdict` reruns earlier failed `verdict` jobs on the head SHA after an owner approval (ADR-0059). Fake gh, no network."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from aiwf import policy

ROOT = Path(__file__).resolve().parents[1]
HEAD = "new4567890"
ME = 300

pytestmark = pytest.mark.skipif(not shutil.which("jq"), reason="jq missing")


def _run(tmp_path, runs, jobs, state="approved", reviews=None, head_repo="o/r", pr_head=HEAD, attempt="1",
         event="pull_request_review", rerun_rc=0, threads=None, labels=(), review="skipped", statuses=()):
    """Runs the verdict step. `runs`: completed runs of the workflow on HEAD; `jobs`: {run id: [(name, conclusion)]};
    `threads`: isResolved of each review thread (None: the GraphQL query fails)."""
    step = policy.load_workflow((ROOT / ".github/workflows/ai-review.yml").read_text())["jobs"]["verdict"]["steps"][0]
    reviews = [{"state": "APPROVED", "commit_id": HEAD, "user": {"login": "m"}, "author_association": "OWNER",
                "body": ""}] if reviews is None else reviews
    data = {
        "reviews": reviews,
        "statuses": list(statuses),
        "labels": [{"name": n} for n in labels],
        "threads": {"data": {"repository": {"pullRequest": {"reviewThreads": {
            "nodes": [{"isResolved": r} for r in threads or []]}}}}},
        "pull": {"head": {"sha": pr_head}},
        "run": {"id": ME, "workflow_id": 7},
        "runs": {"workflow_runs": [{"id": r} for r in runs]},
    }
    for name, value in data.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
    for run, items in jobs.items():
        value = {"jobs": [{"id": run * 10 + i, "name": n, "conclusion": c} for i, (n, c) in enumerate(items)]}
        (tmp_path / f"jobs-{run}.json").write_text(json.dumps(value))
    calls = tmp_path / "calls"
    calls.unlink(missing_ok=True)
    fake = tmp_path / "gh"
    fake.write_text(
        "#!/bin/bash\n"
        f"printf '%s\\n' \"$*\" >> {calls}\n"
        'q=.; prev=; for a in "$@"; do [ "$prev" = --jq ] && q=$a; prev=$a; done\n'
        'case "$*" in\n'
        f"  *graphql*) {'exit 1' if threads is None else f'f={tmp_path}/threads.json'} ;;\n"
        f"  *-X\\ POST*/rerun*) exit {rerun_rc} ;;\n"
        "  *-X\\ POST*statuses*) exit 0 ;;\n"
        f"  *commits/*/statuses*) f={tmp_path}/statuses.json ;;\n"
        f"  *pulls/*/reviews*) f={tmp_path}/reviews.json ;;\n"
        f"  *issues/*/labels*) f={tmp_path}/labels.json ;;\n"
        f"  *actions/workflows/7/runs\\?head_sha={HEAD}\\&status=completed*) f={tmp_path}/runs.json ;;\n"
        f"  *actions/runs/{ME}\\ *) f={tmp_path}/run.json ;;\n"
        '  *actions/runs/*/jobs*) a="$*"; r=${a#*actions/runs/}; f=' f"{tmp_path}" '/jobs-${r%%/*}.json ;;\n'
        f"  *pulls/1\\ *) f={tmp_path}/pull.json ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n"
        'jq -r "$q" "$f"\n'
    )
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "REPO": "o/r", "PR": "1", "AUTHOR": "app[bot]",
           "HEAD_SHA": HEAD, "HEAD_REPO": head_repo, "RUN_ID": str(ME), "RUN_ATTEMPT": attempt, "EVENT": event,
           "REVIEW": review, "REVIEW_STATE": state, "GITHUB_STEP_SUMMARY": str(tmp_path / "summary")}
    proc = subprocess.run(["bash", "-e", "-c", step["run"]], env=env, capture_output=True, text=True)
    lines = calls.read_text().splitlines() if calls.exists() else []
    reran = sorted(int(c.split("actions/jobs/")[1].split("/")[0]) for c in lines if c.endswith("/rerun"))
    return proc, reran, lines


def test_approval_reruns_only_failed_verdict_jobs_of_earlier_runs(tmp_path):
    jobs = {
        100: [("config / load", "success"), ("review / publish", "success"), ("verdict", "failure")],  # pull_request
        101: [("verdict", "failure")],  # an older dismissal or comment run
        102: [("verdict", "success")],  # already green: left alone
        103: [("verdict-other", "failure"), ("verdict", "cancelled")],  # only the `verdict` job; cancelled also blocks
        ME: [("verdict", "failure")],  # this run (listed while in progress elsewhere): never
    }
    proc, reran, calls = _run(tmp_path, [100, 101, 102, 103, ME], jobs)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert reran == [1002, 1010, 1031]
    assert all("filter=latest" in c for c in calls if "/jobs?" in c), "a rerun job's newest attempt counts"
    assert "reran verdict job 1002 of run 100" in proc.stdout


@pytest.mark.parametrize(
    "kwargs, why",
    [
        ({"head_repo": "fork/r"}, "fork PR: no rerun"),
        ({"pr_head": "moved99999"}, "head moved"),
        ({"attempt": "2"}, None),  # a rerun of an approval run does not cascade
        ({"reviews": []}, None),  # no owner approval: nothing to rerun
        ({"state": "dismissed", "reviews": []}, None),
        ({"state": "commented"}, None),
    ],
)
def test_no_rerun(tmp_path, kwargs, why):
    proc, reran, _ = _run(tmp_path, [100], {100: [("verdict", "failure")]}, **kwargs)
    assert reran == []
    if why:
        assert why in proc.stdout


def test_no_rerun_on_pull_request_events(tmp_path):
    proc, reran, _ = _run(tmp_path, [100], {100: [("verdict", "failure")]}, event="pull_request", state="")
    assert reran == [] and proc.returncode == 0  # owner approval of the head: green, no rerun


def test_refused_rerun_is_not_fatal(tmp_path):
    proc, reran, _ = _run(tmp_path, [100], {100: [("verdict", "failure")]}, rerun_rc=1)
    assert proc.returncode == 0 and reran == [1000]
    assert "::warning title=verdict::could not rerun verdict job 1000 of run 100" in proc.stdout


def test_commented_review_is_green_without_a_status(tmp_path):
    proc, reran, calls = _run(tmp_path, [100], {100: [("verdict", "failure")]}, state="commented", reviews=[])
    assert proc.returncode == 0 and reran == []
    assert not any("POST" in c for c in calls), "no status, no rerun"


def _status(calls):
    """(state, description) of the one `verdict` commit status the run posted."""
    (post,) = [c for c in calls if "-X POST" in c and "statuses" in c]
    return post.split("state=")[1].split(" ")[0], post.split("description=", 1)[1]


def test_status_text_counts_unresolved_threads_without_changing_the_result(tmp_path):
    proc, _, calls = _run(tmp_path, [], {}, event="pull_request", state="", reviews=[], review="success",
                          labels=["ai-review: merge"], threads=[False, True, False])
    assert proc.returncode == 0, proc.stdout + proc.stderr  # merge stays green with open threads
    assert _status(calls) == ("success", "ai-review: merge on new4567; 2 unresolved threads at new4567")
    assert "2 unresolved threads at new4567" in (tmp_path / "summary").read_text()


@pytest.mark.parametrize("threads, tail", [([True], "; 0 unresolved threads at new4567"),
                                           ([False], "; 1 unresolved thread at new4567"), (None, "")])
def test_status_text_thread_count_wording_and_failed_query(tmp_path, threads, tail):
    proc, _, calls = _run(tmp_path, [], {}, event="pull_request", state="", reviews=[], review="success",
                          labels=["ai-review: changes-requested"], threads=threads)
    assert proc.returncode == 1  # red on changes-requested, whatever the count
    assert _status(calls) == ("failure", "changes requested on new4567: see the AI review" + tail)


def test_restored_status_gets_a_fresh_count_and_fits_140_characters(tmp_path):
    old = {"context": "verdict", "creator": {"login": "github-actions[bot]"}, "state": "success",
           "description": "x" * 130 + "; 5 unresolved threads at new4567"}
    proc, _, calls = _run(tmp_path, [], {}, state="dismissed", reviews=[], statuses=[old], threads=[False])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    state, desc = _status(calls)
    assert state == "success" and desc == "x" * 108 + "; 1 unresolved thread at new4567" and len(desc) == 140
