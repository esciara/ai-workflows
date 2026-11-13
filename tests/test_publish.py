import json

import pytest

from aiwf import cli, publish

# Pass 1 of triage (extractor) has a schema but no publisher: handy for the shared validate/publish path.
VALID = {"reported_version": "1.2.0", "search_phrases": ["KeyError: total"], "file_paths": [],
         "suspicious_instructions": []}


def test_valid_output():
    assert publish.validate("extractor", json.dumps(VALID)) == VALID


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "not json",
        json.dumps(VALID)[:-1],  # truncated
        "[]",
        '"pong"',
        "null",
        "{}",
        json.dumps({**VALID, "reported_version": 42}),
        json.dumps({**VALID, "labels": ["ai-review: merge"]}),  # extra keys
        json.dumps({**VALID, "search_phrases": ["line one\nline two"]}),
        json.dumps({**VALID, "file_paths": ["../../etc/passwd; rm -rf /"]}),
        "[" * 5000 + "]" * 5000,  # deep nesting
        json.dumps({**VALID, "search_phrases": ["y" * 70_000]}),  # oversized
    ],
)
def test_invalid_output_rejected(raw):
    with pytest.raises(publish.InvalidOutput):
        publish.validate("extractor", raw)


@pytest.fixture
def extractor_publisher(monkeypatch):
    got = []
    monkeypatch.setattr(publish, "publishers", lambda: {"extractor": lambda data, *rest: got.append(data)})
    return got


def test_publish_valid_calls_the_publisher_only(extractor_publisher, gh):
    assert publish.publish("extractor", json.dumps(VALID), "o/r", 7, "https://run", gh)
    assert extractor_publisher == [VALID] and gh.calls == []


def test_publish_invalid_labels_error_and_posts_nothing(extractor_publisher, gh):
    assert not publish.publish("extractor", "{}", "o/r", 7, "", gh)
    assert extractor_publisher == []
    assert gh.calls == [["api", "-X", "POST", "repos/o/r/issues/7/labels", "-f", "labels[]=ai: error"]]


def test_cli_publish_exit_codes(monkeypatch, gh):
    monkeypatch.setattr(cli.config, "run_gh", lambda args: "[]" if "?per_page" in args[-1] else gh(args))
    monkeypatch.setenv("AGENT_JSON", "")
    assert cli.main(["publish", "--kind", "classifier", "--repo", "o/r", "--issue", "3"]) == 1
    assert gh.calls == [["api", "-X", "POST", "repos/o/r/issues/3/labels", "-f", "labels[]=ai: error"]]
