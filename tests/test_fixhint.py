"""aiwf-1st: B1's "possibly fixed by" hint reaches B2 and B2 can confirm it (fixhint, publish_reproduce)."""

import json
from pathlib import Path

import pytest

from aiwf import fixhint, publish, publish_reproduce as pr
from aiwf.publish_triage import MARKER

from test_reproduce import BOT, REPRO, answer, removed
from test_triage import REPO, FakeGh

FIX = "a" * 40
BEFORE = "b" * 40
URL = f"https://github.com/{REPO}/commit/{FIX}"


def triage_comment(url=URL, login=BOT, marker=MARKER):
    body = (f"{marker}\n**AI triage:** bug (high confidence). Wrong total.\n\n"
            f"Possibly fixed on the default branch by {url} (high confidence). Not confirmed.")
    return {"id": 3, "user": {"login": login}, "body": body}


def fake(comment=None, **kw):
    commits = {FIX: {"sha": FIX, "parents": [{"sha": BEFORE}]}}
    return FakeGh(author="rep", commits=commits, comments=[comment or triage_comment()], **kw)


def test_commit_hint_resolves_to_its_first_parent():
    assert fixhint.find(fake(), REPO, 1) == {"kind": "commit", "ref": FIX, "before": BEFORE}


def test_merged_pr_hint_resolves_to_its_base_commit():
    g = fake(triage_comment(f"https://github.com/{REPO}/pull/12"))
    g.pulls = {12: {"merged_at": "2026-01-01", "base": {"sha": BEFORE}}}
    assert fixhint.find(g, REPO, 1) == {"kind": "pull", "ref": "12", "before": BEFORE}


@pytest.mark.parametrize("comment", [
    triage_comment(login="mallory"),  # anyone else's comment is never a hint
    triage_comment(marker="<!-- other -->"),
    triage_comment(f"https://github.com/other/repo/commit/{FIX}"),  # another repo
    triage_comment(f"https://github.com/{REPO}/commit/{FIX[:7]}"),  # not a full SHA
    triage_comment(f"https://github.com/{REPO}/tree/{FIX}"),
    {"id": 3, "user": {"login": BOT}, "body": f"{MARKER}\n**AI triage:** bug. see {URL} (x)"},  # not the fixed sentence
])
def test_only_the_workflows_own_fixed_sentence_is_a_hint(comment):
    assert fixhint.find(fake(comment), REPO, 1) is None


def test_unresolvable_fixes_give_no_hint():
    root = FakeGh(commits={FIX: {"sha": FIX, "parents": []}}, comments=[triage_comment()])
    assert fixhint.find(root, REPO, 1) is None
    bad = FakeGh(commits={FIX: {"sha": FIX, "parents": [{"sha": "main"}]}}, comments=[triage_comment()])
    assert fixhint.find(bad, REPO, 1) is None
    unmerged = fake(triage_comment(f"https://github.com/{REPO}/pull/12"))
    unmerged.pulls = {12: {"merged_at": None, "base": {"sha": BEFORE}}}
    assert fixhint.find(unmerged, REPO, 1) is None


# --- publisher -------------------------------------------------------------------------------------------------------

def publish_fc(g, monkeypatch, result="confirmed", evidence="Fails before, passes now.", **extra):
    monkeypatch.setenv("AIWF_CONFIG", json.dumps({"maintainers": ["esciara"]}))
    d = answer(fix_check={"result": result, "evidence": evidence}, **{"questions": [], "tried": "", **extra})
    assert publish.publish("reproducer", json.dumps(d), REPO, 1, "https://run/9", g)


def test_confirmed_labels_fixed_comments_and_asks_nothing(monkeypatch, tmp_path):
    out = tmp_path / "out"
    out.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    g = fake(labels=("triage: needs-info", "triage: needs-human", "triage: reproduced", "stale"))
    publish_fc(g, monkeypatch)
    assert g.added_labels() == ["triage: fixed"]
    assert set(removed(g)) == {"triage: needs-info", "triage: needs-human", "triage: reproduced", "stale"}
    [body] = g.comment_bodies()
    assert body.startswith(pr.FIX_MARKER) and "Confirmed fixed" in body and "Not closed" in body
    assert "aaaaaaa" in body and "bbbbbbb" in body and "https://run/9" in body and "Fails before" in body
    assert "reproduced=true" not in out.read_text()  # no B3


def test_confirmed_without_a_real_hint_is_not_trusted(monkeypatch):
    g = FakeGh(author="rep")  # the agent claims a fix check, B1 named none
    publish_fc(g, monkeypatch)
    assert g.added_labels() == ["triage: needs-info"]
    assert "@rep" in g.comment_bodies()[0]


@pytest.mark.parametrize("result,evidence", [("unclear", "x"), ("rejected", "x"), ("confirmed", "  ")])
def test_other_results_take_the_needs_info_path(monkeypatch, result, evidence):
    g = fake()
    publish_fc(g, monkeypatch, result, evidence)
    assert g.added_labels() == ["triage: needs-info"]


def test_confirmed_with_a_reproduction_is_the_normal_reproduced_path(monkeypatch):
    g = fake()
    publish_fc(g, monkeypatch, "confirmed", reproduced=True, test=REPRO)
    assert g.added_labels() == ["triage: reproduced"]


@pytest.mark.parametrize("extra", [{"reproduced": True, "test": REPRO}, {}])
def test_a_later_outcome_withdraws_the_fixed_label_and_note(monkeypatch, extra):
    note = {"id": 9, "user": {"login": BOT}, "body": f"{pr.FIX_MARKER}\nConfirmed fixed."}
    g = FakeGh(author="rep", labels=("triage: fixed",), comments=[note])
    monkeypatch.setenv("AIWF_CONFIG", json.dumps({"maintainers": ["esciara"]}))
    assert publish.publish("reproducer", json.dumps(answer(**extra)), REPO, 1, "https://run/9", g)
    assert "triage: fixed" in removed(g)
    assert any(w[3].endswith("/comments/9") and "Superseded" in w[-1] for w in g.writes("PATCH"))


def test_schema_accepts_fix_check_and_rejects_other_results():
    import jsonschema
    schema = json.loads((Path(__file__).parents[1] / "schema" / "reproducer.json").read_text())
    jsonschema.validate(answer(fix_check={"result": "confirmed", "evidence": "e"}), schema)
    jsonschema.validate(answer(), schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(answer(fix_check={"result": "fixed", "evidence": "e"}), schema)
