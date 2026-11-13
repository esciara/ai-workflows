"""templates/caller.yml's concurrency group (checkpoint item 3), evaluated on sample events.

A group keeps one pending run, so a plain comment in the item's group would replace a queued review of a new push.
Plain comments get their own group; pushes, fork pushes and anything that may be a command stay in the item's group.
"""

import json
import re
from pathlib import Path

import pytest

from aiwf import commands, policy

ROOT = Path(__file__).resolve().parents[1]
GROUP = policy.load_workflow((ROOT / "templates" / "caller.yml").read_text())["concurrency"]["group"]
RUN_ID = 987654321

TOKEN = re.compile(r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<op>==|!=|&&|\|\||!|\(|\)|,)|(?P<name>[A-Za-z_][\w.-]*))")
FUNCS = {
    "startsWith": lambda s, p: str(s or "").lower().startswith(str(p).lower()),
    "contains": lambda s, p: str(p).lower() in str(s or "").lower(),
    "fromJSON": json.loads,
    "format": lambda f, *a: re.sub(r"\{(\d+)\}", lambda m: str(a[int(m.group(1))]), f),
}


def _expr(src: str, ctx: dict):
    """The subset of GitHub expressions the group uses, translated to Python (and/or/not return values alike)."""
    out, pos = [], 0
    while pos < len(src.rstrip()):
        m = TOKEN.match(src, pos)
        assert m, f"unsupported expression syntax at {src[pos:]!r}"
        pos = m.end()
        if m["str"]:
            out.append(repr(m["str"][1:-1].replace("''", "'")))
        elif m["op"]:
            out.append({"&&": " and ", "||": " or ", "!": " not "}.get(m["op"], m["op"]))
        elif m["name"] in FUNCS:
            out.append(f"F[{m['name']!r}]")
        else:
            out.append(f"C({m['name']!r})")

    def lookup(path: str):
        val = ctx
        for part in path.split("."):
            val = val.get(part) if isinstance(val, dict) else None
        return val

    return eval("".join(out), {"F": FUNCS, "C": lookup})  # noqa: S307 - our own template, fixed tokens only


def group(event: str, payload: dict) -> str:
    ctx = {"github": {"event_name": event, "event": payload, "run_id": RUN_ID}}
    parts = re.split(r"\$\{\{(.*?)\}\}", GROUP)
    return "".join(p if i % 2 == 0 else str(_expr(p, ctx) or "") for i, p in enumerate(parts))


PR = {"pull_request": {"number": 7}}


def comment(body: str, on_pr: bool = True) -> dict:
    issue = {"number": 7, **({"pull_request": {"url": "x"}} if on_pr else {})}
    return {"issue": issue, "comment": {"body": body}}


def test_pushes_share_the_item_group():
    assert group("pull_request", PR) == "ai-workflows-7"
    assert group("pull_request_target", PR) == "ai-workflows-fork-push-7"
    assert group("issues", {"issue": {"number": 7}}) == "ai-workflows-7"
    assert group("schedule", {}) == f"ai-workflows-{RUN_ID}"


@pytest.mark.parametrize("on_pr", [True, False])
@pytest.mark.parametrize("body", [
    "/review", "/fix", "  /retriage", "   /no-fix reason", "\n\n/fix", "\r\n  \r\n/fix please", " \t\n /review",
    "see a /path",  # not a command, but kept with the item: a false positive only waits
    "/unknown",
])
def test_comments_that_may_be_commands_stay_in_the_item_group(body, on_pr):
    assert group("issue_comment", comment(body, on_pr)) == "ai-workflows-7"


@pytest.mark.parametrize("on_pr", [True, False])
@pytest.mark.parametrize("body", ["LGTM", "thanks!", "", "see https://example.com/x", "a/b", "> quoted\tline"])
def test_plain_comments_get_their_own_group(body, on_pr):
    assert group("issue_comment", comment(body, on_pr)) == f"ai-workflows-comment-{RUN_ID}-7"


@pytest.mark.parametrize("body", [
    "/review", "  /fix", "   /no-fix why", "\n/retriage", "\r\n/fix", " \n   /review", "\t\n/fix", "text\n\n/fix",
])
def test_every_parsed_command_stays_in_the_item_group(body):
    """Never a false negative: what commands.parse accepts is never put in a unique group."""
    if commands.parse(body) is not None:
        assert group("issue_comment", comment(body)) == "ai-workflows-7"
