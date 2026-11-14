"""The verdict-only pull_request_review run must not share the PR's concurrency group (it could replace a queued review)."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def test_review_event_has_own_concurrency_group():
    doc = yaml.safe_load((ROOT / ".github" / "workflows" / "ai-review.yml").read_text())
    group = doc["concurrency"]["group"]
    assert "pull_request_review" in group and "verdict-" in group
    # per-run group: reruns of several stale review runs must not queue in one group (ADR-0059)
    assert "github.run_id" in group.split("||")[0]
    assert doc["concurrency"]["cancel-in-progress"] is False
