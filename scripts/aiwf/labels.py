"""Idempotent label sync from schema/labels.yml (ADR-0006). Never deletes labels."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import yaml

LABELS_PATH = Path(__file__).resolve().parents[2] / "schema" / "labels.yml"

GhRunner = Callable[[list[str]], str]


def load(path: Path = LABELS_PATH) -> list[dict[str, str]]:
    data = yaml.safe_load(path.read_text())
    labels = [
        {"name": str(item["name"]), "color": str(item["color"]).lower().lstrip("#"), "description": str(item["description"])}
        for item in data["labels"]
    ]
    names = [label["name"].lower() for label in labels]
    if len(names) != len(set(names)):
        raise ValueError("duplicate label names in labels.yml")
    return labels


def diff(wanted: list[dict[str, str]], existing: list[dict[str, Any]]) -> tuple[list[dict], list[dict], list[str]]:
    """(to create, to update, unchanged names). Names match case-insensitively, as on GitHub."""
    by_name = {str(e["name"]).lower(): e for e in existing}
    create, update, same = [], [], []
    for label in wanted:
        cur = by_name.get(label["name"].lower())
        if cur is None:
            create.append(label)
        elif (
            cur["name"] != label["name"]
            or str(cur.get("color", "")).lower() != label["color"]
            or (cur.get("description") or "") != label["description"]
        ):
            update.append({**label, "current_name": cur["name"]})
        else:
            same.append(label["name"])
    return create, update, same


def sync(repo: str, gh: GhRunner, wanted: list[dict[str, str]] | None = None) -> tuple[int, int, int]:
    wanted = wanted if wanted is not None else load()
    raw = gh(["api", "--paginate", f"repos/{repo}/labels?per_page=100", "--jq", ".[] | {name, color, description}"])
    existing = [json.loads(line) for line in raw.splitlines() if line.strip()]
    create, update, same = diff(wanted, existing)
    for label in create:
        gh(["api", "-X", "POST", f"repos/{repo}/labels",
            "-f", f"name={label['name']}", "-f", f"color={label['color']}", "-f", f"description={label['description']}"])
        print(f"created  {label['name']}")
    for label in update:
        gh(["api", "-X", "PATCH", f"repos/{repo}/labels/{quote(label['current_name'], safe='')}",
            "-f", f"new_name={label['name']}", "-f", f"color={label['color']}", "-f", f"description={label['description']}"])
        print(f"updated  {label['name']}")
    print(f"labels: {len(create)} created, {len(update)} updated, {len(same)} unchanged")
    return len(create), len(update), len(same)
