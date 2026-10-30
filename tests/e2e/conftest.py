import os
import time

import pytest

import playground as pg


def pytest_collection_modifyitems(config, items):
    if os.environ.get("AIWF_E2E") == "1":
        return
    skip = pytest.mark.skip(reason="end-to-end test: set AIWF_E2E=1 to run against the playground")
    for item in items:
        if "/e2e/" in str(item.fspath):
            item.add_marker(skip)


FIXTURE_TITLE = "[e2e] WP1 /ping fixture"


@pytest.fixture(scope="session")
def fixture_issue() -> dict:
    """The reusable test-fixture issue (found by title, created once). Never deleted."""
    found = pg.api(f"repos/{pg.REPO}/issues?labels={pg.FIXTURE_LABEL}&state=open&per_page=100")
    for issue in found:
        if issue["title"] == FIXTURE_TITLE and "pull_request" not in issue:
            return {"number": issue["number"], "title": issue["title"]}
    issue = pg.api(
        f"repos/{pg.REPO}/issues",
        f"title={FIXTURE_TITLE}",
        "body=Reusable fixture for tests/e2e/test_wp1.py in esciara/ai-workflows.",
        f"labels[]={pg.FIXTURE_LABEL}",
        method="POST",
    )
    return {"number": issue["number"], "title": issue["title"]}


@pytest.fixture
def throwaway_pr():
    """A test-fixture PR on its own branch; branch deleted (and PR closed) in teardown."""
    branch = f"e2e-wp1-{int(time.time())}"
    base = pg.api(f"repos/{pg.REPO}")["default_branch"]
    sha = pg.api(f"repos/{pg.REPO}/git/ref/heads/{base}")["object"]["sha"]
    pg.api(f"repos/{pg.REPO}/git/refs", f"ref=refs/heads/{branch}", f"sha={sha}", method="POST")
    pr = None
    try:
        pg.api(
            f"repos/{pg.REPO}/contents/e2e/{branch}.md",
            f"message=test: e2e throwaway {branch}",
            "content=dGhyb3dhd2F5Cg==",  # "throwaway\n"
            f"branch={branch}",
            method="PUT",
        )
        title = f"[e2e] WP1 /ping on a PR ({branch})"
        pr = pg.api(
            f"repos/{pg.REPO}/pulls", f"title={title}", f"head={branch}", f"base={base}",
            "body=Throwaway PR for tests/e2e/test_wp1.py; closed by its teardown.", method="POST",
        )
        pg.api(f"repos/{pg.REPO}/issues/{pr['number']}/labels", f"labels[]={pg.FIXTURE_LABEL}", method="POST")
        yield {"number": pr["number"], "title": title}
    finally:
        pg.gh(["api", "-X", "DELETE", f"repos/{pg.REPO}/git/refs/heads/{branch}"])
        if pr and pg.api(f"repos/{pg.REPO}/pulls/{pr['number']}")["state"] == "open":
            pg.api(f"repos/{pg.REPO}/pulls/{pr['number']}", "state=closed", method="PATCH")
