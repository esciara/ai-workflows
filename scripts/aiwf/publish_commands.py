"""Publishers for the commands workflow (slash commands that are neither Workflow A nor B, e.g. `/ping`)."""

from __future__ import annotations

from typing import Any

from aiwf import publish


def ping_body(data: dict[str, Any], run_url: str) -> str:
    lines = ["<!-- ai-workflows:ping -->", f"🏓 pong: {data['reply']}"]
    if run_url:
        lines += ["", f"[Run]({run_url})"]
    return "\n".join(lines)


def publish_ping(data: dict[str, Any], repo: str, issue: int, run_url: str, gh: publish.GhRunner) -> None:
    publish.comment(gh, repo, issue, ping_body(data, run_url))
    print(f"replied on {repo}#{issue}")


PUBLISHERS = {"ping": publish_ping}
