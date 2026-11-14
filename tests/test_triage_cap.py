"""ADR-0058: daily triage caps for issues from outside authors (no network)."""

import json

import pytest

from aiwf import cli, publish_triage as pt, triage_cap as tc
from ghfake import RecordingGh

REPO = "o/r"
MAINT = ["Boss"]
NOW = "2026-11-14T12:00:00Z"
LIMITS = {"triage_per_author_per_day": 3, "triage_per_day": 20}


def issue(number, login, created=NOW, pr=False):
    out = {"number": number, "user": {"login": login}, "created_at": created}
    if pr:
        out["pull_request"] = {"url": "x"}
    return out


def reason(issues, number, author, **limits):
    return tc.cap_reason(issues, number, author, MAINT, {**LIMITS, **limits})


# --- per-author cap -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("count,capped", [(2, False), (3, False), (4, True)])
def test_per_author_under_at_over(count, capped):
    issues = [issue(n, "eve") for n in range(1, count + 1)]
    assert bool(reason(issues, count, "eve")) is capped


def test_per_author_cap_is_per_author_and_case_insensitive():
    issues = [issue(1, "Eve"), issue(2, "eve"), issue(3, "EVE"), issue(4, "bob")]
    assert reason(issues, 4, "bob") == ""
    assert "this author" in reason([*issues, issue(5, "eve")], 5, "eve")


# --- repo-wide cap --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("count,capped", [(19, False), (20, False), (21, True)])
def test_per_day_under_at_over(count, capped):
    issues = [issue(n, f"user{n}") for n in range(1, count + 1)]
    got = reason(issues, count, f"user{count}")
    assert bool(got) is capped
    assert not got or "triage_per_day=20" in got


@pytest.mark.parametrize("key", ["triage_per_day", "triage_per_author_per_day"])
def test_zero_means_never_triage_outsiders(key):
    assert reason([issue(1, "eve")], 1, "eve", **{key: 0})
    assert reason([], 1, "eve", **{key: 0})  # the current issue counts even when the list lags


# --- exemptions and what counts -------------------------------------------------------------------------------------

def test_maintainer_never_capped_and_not_counted():
    issues = [issue(n, "boss") for n in range(1, 30)]
    assert reason(issues, 29, "BOSS", triage_per_day=0) == ""
    assert reason([*issues, issue(30, "eve")], 30, "eve", triage_per_day=1) == ""


def test_ordering_by_number_whatever_the_list_order():
    """A burst of 5 from one author: issues 1-3 triaged, 4-5 capped, in any order the runs see the list."""
    issues = [issue(n, "eve") for n in (5, 2, 4, 1, 3)]
    assert [bool(reason(issues, n, "eve")) for n in range(1, 6)] == [False, False, False, True, True]


# --- check(): API, window, pull requests, event ---------------------------------------------------------------------

class Gh(RecordingGh):
    def __init__(self, author, listed):
        super().__init__()
        self.author, self.listed = author, listed

    def respond(self, args):
        url = self.url(args)
        if url == f"repos/{REPO}/issues/{self.current}":
            return json.dumps(issue(self.current, self.author))
        assert url.startswith(f"repos/{REPO}/issues?state=all&since=2026-11-13T12%3A00%3A00Z&")
        assert "--paginate" in args
        return "\n".join(json.dumps(i) for i in self.listed)


def run_check(author, listed, current, event="issues", **limits):
    gh = Gh(author, listed)
    gh.current = current
    cfg = {"maintainers": MAINT, "limits": {**LIMITS, **limits}}
    return tc.check(gh, REPO, current, cfg, event), gh


def test_check_drops_pull_requests():
    listed = [issue(1, "eve", pr=True), issue(2, "eve", pr=True), issue(3, "eve")]
    assert run_check("eve", listed, 3, triage_per_author_per_day=1)[0] == ""


def test_check_drops_issues_outside_the_window():
    listed = [issue(1, "eve", created="2026-11-13T11:59:59Z"), issue(2, "eve")]
    assert run_check("eve", listed, 2, triage_per_author_per_day=1)[0] == ""
    listed[0]["created_at"] = "2026-11-13T12:00:00Z"
    assert run_check("eve", listed, 2, triage_per_author_per_day=1)[0]


def test_check_counts_closed_and_capped_issues():
    """Every issue opened counts (ADR-0058 point 3): the list is state=all and labels are not read."""
    listed = [{**issue(1, "eve"), "state": "closed", "labels": [{"name": "triage: needs-human"}]}, issue(2, "eve")]
    assert run_check("eve", listed, 2, triage_per_author_per_day=1)[0]


def test_retriage_never_capped():
    got, gh = run_check("eve", [issue(1, "eve")], 1, event="issue_comment", triage_per_day=0)
    assert got == "" and gh.calls == []


def test_maintainer_check_skips_the_list():
    got, gh = run_check("boss", [], 1, triage_per_day=0)
    assert got == "" and len(gh.calls) == 1


def test_cli_writes_capped_output(tmp_path, monkeypatch):
    gh = Gh("eve", [issue(1, "eve")])
    gh.current = 1
    monkeypatch.setattr(tc.config, "run_gh", gh)
    monkeypatch.setenv("AIWF_CONFIG", json.dumps({"maintainers": MAINT, "limits": {**LIMITS, "triage_per_day": 0}}))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "issues")
    out = tmp_path / "out"
    assert cli.main(["triage-cap", "--repo", REPO, "--issue", "1", "--github-output", str(out)]) == 0
    assert out.read_text() == "capped=true\n"


# --- publish for a capped issue -------------------------------------------------------------------------------------

class PubGh(RecordingGh):
    def respond(self, args):
        return "" if "--paginate" in args else "{}"


def test_publish_capped_label_and_fixed_comment():
    gh = PubGh()
    pt.publish_capped(REPO, 7, gh)
    labels, comment = gh.writes("POST")
    assert labels[-2:] == ["-f", "labels[]=triage: needs-human"]
    body = comment[-1].removeprefix("body=")
    assert body == f"{pt.MARKER}\n**AI triage:** Automatic triage limit reached for today; a maintainer can run `/retriage`."


class CliGh(RecordingGh):
    def __init__(self, labels):
        super().__init__()
        self.labels = labels

    def respond(self, args):
        if self.url(args).endswith("/labels?per_page=100"):
            return json.dumps([{"name": n} for n in self.labels])
        return "" if "--paginate" in args else "{}"


@pytest.mark.parametrize("labels,writes", [(["ai: off"], 0), ([], 2)])
def test_cli_triage_capped_respects_ai_off(monkeypatch, labels, writes):
    gh = CliGh(labels)
    monkeypatch.setattr(tc.config, "run_gh", gh)
    assert cli.main(["triage-capped", "--repo", REPO, "--issue", "7"]) == 0
    assert len(gh.writes()) == writes
