"""WP13 acceptance test. Done when: review runs on a branch locally and in a fork, with nothing posted upstream.

1. Level 0, local (needs the `claude` CLI logged in on this machine; skipped without it): a throwaway git repo with a
   `main` and a `feat` branch holding a seeded bug (a percent no longer divided by 100). `claude -p
   /ai-workflows:review main --plugin-dir plugin` finds the bug in `cart.py`. A shim `gh` first on PATH records every
   call and a bare remote receives nothing: after the run there are no gh calls, the remote has no `feat`, and the
   working tree is untouched.
2. Level 1, in a fork (AIWF_E2E=1, AIWF_E2E_SLOT=any): a repo with Workflow A installed (the playground, through its
   e2e caller, standing in for a fork) reviews a seeded-bug PR opened inside it with the commit under test: one summary
   comment, one verdict label, Request changes. Limit: a fork install is the install of docs/install.md (test_wp14), so
   this repeats the first half of test_wp3 and has no real upstream to prove "nothing posted" against. The real fork
   opinionated-digital-center/ai-workflows-playground has no secret (only the maintainer can set one), so it is unused.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

import playground as pg
from review_core import check_review
from review_seeded import head_sha, review_run, seeded_pr, summary

PLUGIN = pg.ROOT / "plugin"
BASE = "def pct(price, percent):\n    return price * (1 - percent / 100)\n"
BUGGY = "def pct(price, percent):\n    return price * (1 - percent)\n"
CHANGES = "ai-review: changes-requested"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.mark.skipif(shutil.which("claude") is None, reason="needs the claude CLI")
def test_local_review_finds_a_seeded_bug_and_posts_nothing(tmp_path):
    remote, repo, shim = tmp_path / "remote.git", tmp_path / "repo", tmp_path / "bin"
    shim.mkdir()
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "e2e@example.com")
    git(repo, "config", "user.name", "e2e")
    (repo / "cart.py").write_text(BASE)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "switch", "-qc", "feat")
    (repo / "cart.py").write_text(BUGGY)
    git(repo, "commit", "-qam", "fix pricing")
    head = git(repo, "rev-parse", "HEAD")
    calls = tmp_path / "gh-calls.log"
    (shim / "gh").write_text(f'#!/bin/sh\necho "$@" >> {calls}\nexit 1\n')
    (shim / "gh").chmod(0o755)

    out = subprocess.run(["claude", "-p", "/ai-workflows:review main", "--plugin-dir", str(PLUGIN), "--max-turns", "15",
                          "--model", "sonnet"], cwd=repo, capture_output=True, text=True, timeout=600,
                         env={**os.environ, "PATH": f"{shim}:{os.environ['PATH']}"})
    print(out.stdout, out.stderr)
    assert out.returncode == 0, out.stderr
    assert "cart.py" in out.stdout and "changes-requested" in out.stdout and "blocking" in out.stdout, "bug not found"
    assert not calls.exists(), f"the skill called gh: {calls.read_text()}"
    assert git(remote, "for-each-ref") == "", "something reached the remote"
    assert git(repo, "rev-parse", "HEAD") == head and git(repo, "status", "--porcelain") == "", "the repo changed"


def test_review_runs_on_a_pr_inside_a_fork_install(e2e_target):
    with seeded_pr() as pr:
        number = pr["number"]
        sha = head_sha(number)
        review_run(sha, after="1970-01-01T00:00:00Z")
        check_review(number, sha, e2e_target)
        print(summary(number))
        assert CHANGES in {lb["name"] for lb in pg.api(f"repos/{pg.REPO}/issues/{number}/labels?per_page=100")}
