import pytest

from aiwf.devguard import decide, maintainer_allowed

PG = "esciara/ai-workflows-playground"
AGENT = "scripts/dev/as-agent"

ALLOWED = [
    "gh pr view 3", "gh -R esciara/ai-workflows pr list --json number", "gh run watch 12", "gh issue list",
    "gh api repos/esciara/ai-workflows/pulls", "gh api -X GET repos/x/y/issues --jq .[]", "gh auth status",
    "git status", "git fetch origin", "git pull --rebase", "git ls-remote origin e2e-target", "git log --grep push",
    f"{AGENT} gh pr create --title t --body b", f"{AGENT} git push -u origin HEAD", f"{AGENT} git push origin wp2-x",
    f"{AGENT} git push --force-with-lease origin wp2-x", f"{AGENT} git push origin main-fix",
    f"cd ../x && {AGENT} git -C dir push origin HEAD:wp2-x", "scripts/dev/as-tester issue comment 3 --body hi",
    f"scripts/dev/as-maintainer pr review 4 -R {PG} --approve",
    "git push https://github.com/opinionated-digital-center/ai-workflows-playground.git HEAD:fork-bug",
    "uv run --extra test pytest -q", "echo hello | grep gh",
]
BLOCKED = [
    "gh pr merge 3", "cd x && gh pr merge 3", f"{AGENT} gh pr merge 3 --rebase", "echo \"gh pr merge\"",  # known false positive
    "gh api -X PUT repos/esciara/ai-workflows/pulls/3/merge", f"{AGENT} gh api -X PUT repos/o/r/pulls/3/merge",
    "gh auth token", f"{AGENT} gh pr review 3 --approve", f"{AGENT} gh api repos/o/r/pulls/3/reviews -f event=APPROVE",
    "gh pr create --title t", "GH_TOKEN=abc gh pr create", "command gh pr comment 3 -b x", "/opt/homebrew/bin/gh issue edit 3",
    "env FOO=1 gh label create x", "gh api repos/o/r/issues -f title=x", "gh api -X POST repos/o/r/labels",
    "gh api --method=PATCH repos/o/r", "gh api graphql -f query=q", "gh pr view 3; gh pr close 3",
    "git push origin wp2-x", "git -C dir push origin wp2-x", "bash -c 'git push origin x'", "eval gh pr close 3",
    f"{AGENT} git push origin main", f"{AGENT} git -C dir push origin main", f"{AGENT} git push origin HEAD:main",
    f"{AGENT} git push origin HEAD:refs/heads/main", f"{AGENT} git push --force origin wp2-x", f"{AGENT} git push -f origin x",
    f"{AGENT} git push origin +x", f"{AGENT} git push --delete origin x", f"{AGENT} git push origin :x",
    f"{AGENT} git push --mirror origin", f"{AGENT} gh api -X DELETE repos/esciara/ai-workflows/git/refs/heads/x",
    f"sh -c \"{AGENT} git push origin 'HEAD:main'\"", "git -C dir push origin main",
]


@pytest.mark.parametrize("command", ALLOWED)
def test_hook_allows(command):
    assert decide(command) == (True, "")


@pytest.mark.parametrize("command", BLOCKED)
def test_hook_blocks(command):
    allowed, why = decide(command)
    assert not allowed and why


def body(path):
    return ["api", "-X", "POST", f"repos/{PG}/{path}"]


@pytest.mark.parametrize("args", [
    ["issue", "comment", "3", "-R", PG, "--body", "/fix"], ["gh", "pr", "comment", "4", "--repo", PG, "-b", "/review --x"],
    ["pr", "review", "4", "-R", PG, "--approve"], ["pr", "review", "4", "-R", PG, "--request-changes", "-b", "no"],
    [*body("issues/3/comments"), "-f", "body=/fix"], [*body("pulls/4/reviews"), "-f", "event=APPROVE", "-f", "body=ok"],
    [*body("actions/workflows/9/dispatches"), "-f", "ref=main", "-F", "return_run_details=true"],
])
def test_as_maintainer_allows(args):
    assert maintainer_allowed(args) == (True, "")


@pytest.mark.parametrize("args", [
    ["pr", "merge", "4", "-R", PG], ["issue", "comment", "3", "--body", "x"], ["issue", "comment", "3", "-R", "esciara/ai-workflows", "-b", "x"],
    ["pr", "review", "4", "-R", PG, "--approve", "--body-file", "/etc/passwd"], ["issue", "comment", "-R", PG, "-b", "x"],
    ["issue", "edit", "3", "-R", PG], ["auth", "token"], ["api", f"repos/{PG}/issues/3/comments"],
    ["api", "-X", "POST", "repos/esciara/ai-workflows/issues/3/comments", "-f", "body=x"],
    [*body("issues/3/comments"), "-f", "title=x"], [*body("issues/3/comments"), "-F", "body=@secret"],
    [*body("pulls/4/merge")], [*body("issues/3/comments"), f"repos/{PG}/issues/4/comments"], [],
])
def test_as_maintainer_refuses(args):
    allowed, why = maintainer_allowed(args)
    assert not allowed and why
