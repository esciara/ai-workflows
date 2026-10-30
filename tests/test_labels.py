import json
import re

from aiwf import labels

ROOT = labels.LABELS_PATH.parents[1]


def test_label_file_covers_every_label_in_the_spec():
    spec = (ROOT / "docs" / "spec.md").read_text()
    named = set(re.findall(r"`((?:type|triage|fix|ai-review|ai): [a-z-]+)`", spec))
    named |= {"stale", "keep-open", "ai-fix"}
    # the spec's labels table abbreviates siblings, e.g. `type: bug` / `feature` / `question`
    named |= {"type: feature", "type: question", "triage: duplicate", "fix: needs-maintainer"}
    assert named <= {label["name"] for label in labels.load()}


def test_label_colours_are_hex():
    for label in labels.load():
        assert re.fullmatch(r"[0-9a-f]{6}", label["color"]), label
        assert label["description"] and len(label["description"]) <= 100, label


WANTED = [
    {"name": "type: bug", "color": "d73a4a", "description": "Bug"},
    {"name": "ai: error", "color": "b60205", "description": "Failed"},
    {"name": "stale", "color": "ffffff", "description": "Stale"},
]


def test_diff_create_update_leave_alone():
    existing = [
        {"name": "type: bug", "color": "D73A4A", "description": "Bug"},  # same (colour case ignored)
        {"name": "AI: Error", "color": "b60205", "description": "Failed"},  # rename case
        {"name": "wontfix", "color": "ffffff", "description": "not ours"},  # untouched
    ]
    create, update, same = labels.diff(WANTED, existing)
    assert [c["name"] for c in create] == ["stale"]
    assert [(u["current_name"], u["name"]) for u in update] == [("AI: Error", "ai: error")]
    assert same == ["type: bug"]


def test_diff_detects_colour_and_description_changes():
    existing = [
        {"name": "type: bug", "color": "000000", "description": "Bug"},
        {"name": "ai: error", "color": "b60205", "description": None},
        {"name": "stale", "color": "ffffff", "description": "Stale"},
    ]
    create, update, same = labels.diff(WANTED, existing)
    assert create == [] and same == ["stale"]
    assert [u["name"] for u in update] == ["type: bug", "ai: error"]


class FakeGh:
    def __init__(self, existing):
        self.existing, self.calls = existing, []

    def __call__(self, args):
        self.calls.append(args)
        if "--paginate" in args:
            return "\n".join(json.dumps(e) for e in self.existing) + "\n"
        return "{}"


def test_sync_is_idempotent_and_encodes_names():
    gh = FakeGh([{"name": "AI: Error", "color": "b60205", "description": "Failed"}])
    assert labels.sync("o/r", gh, WANTED) == (2, 1, 0)
    writes = gh.calls[1:]
    assert [w[2] for w in writes] == ["POST", "POST", "PATCH"]
    assert writes[2][3] == "repos/o/r/labels/AI%3A%20Error"
    assert not any("DELETE" in w for w in gh.calls)

    gh = FakeGh(WANTED)
    assert labels.sync("o/r", gh, WANTED) == (0, 0, 3)
    assert len(gh.calls) == 1  # list only, no writes
