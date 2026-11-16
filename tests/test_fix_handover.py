"""B6 hand-over (spec B6, ADR-0061): the compare-link comment with the PR text after an approved round."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

from aiwf import cli, fix_handover as ho
from test_fix import ANALYSIS, COMPARE, REPO, REPRO, RUN, CFG, Gh, comment, rec


def approved(k=1, **extra):
    base = {"outcome": "approved", "findings": [], "check_output": "", "suspicious_instructions": [],
            "pushed": "p" * 40, "summary": "Fixed Cart.total", **extra}
    return {**rec(k), **base}


class IssueGh(Gh):
    title = "Total wrong <b>@evil</b> & [x](http://e.com)"

    def respond(self, args):
        if self.url(args) == f"repos/{REPO}/issues/1" and self.method(args) == "GET":
            return json.dumps({"title": self.title})
        return super().respond(args)


ANALYSIS_RC = ANALYSIS.replace("Root cause here.", "**Root cause** — [a.py#L3](https://x): total ignores coupon.")


def run(fake, rounds, cfg=CFG):
    return ho.handover(fake, REPO, 1, cfg, rounds, RUN)


def pasted_text(fake):
    [text] = fake.comment_bodies()
    return text, text.split("PR description to paste:", 1)[1]


def test_the_comment_has_the_prefilled_compare_link_and_the_pr_text_and_opens_no_pr(monkeypatch):
    monkeypatch.delenv("GITHUB_SERVER_URL", raising=False)
    fake = IssueGh(comments=[comment(REPRO, cid=4), comment(ANALYSIS_RC)], head="h" * 40)
    assert run(fake, [rec(1, pushed="q" * 40), approved(2)]) == f"handed over #1: compare link {COMPARE}"
    text, pasted = pasted_text(fake)
    assert text.startswith(ho.MARKER) and "@esciara @other" in text and "bad login" not in text
    link = text.split("[open one from the branch](", 1)[1].split(")", 1)[0]
    q = parse_qs(urlsplit(link).query)
    assert link.startswith(COMPARE + "?expand=1") and q["labels"] == ["ai-fix"]
    assert q["title"] == ["Fix #1: Total wrong <b>@evil</b> & [x](http://e.com)"]  # decoded: a PR title is plain text
    assert not set("<>@ []") & set(link)  # everything in the URL is encoded
    assert "Fixes #1" in pasted and "total ignores coupon" in pasted
    assert "`tests/test_repro.py`, run with `pytest tests/test_repro.py -k a|b`" in pasted
    assert "- Round 1: rejected" in pasted and "- Round 2: approved" in pasted and "Fixed Cart.total" in pasted
    assert f"[run]({RUN})" in text
    assert [(m, u) for m, u, b in fake.posted] == [("POST", f"repos/{REPO}/issues/1/comments")]  # no label, PR, assignee


def test_untrusted_text_in_the_pasted_body_is_cleaned_and_fenced():
    fake = IssueGh(comments=[comment(REPRO, cid=4), comment(ANALYSIS_RC)], head="h" * 40)
    bad = approved(1, summary="done @evil <img src=x> ```` end", findings=["note <b>@x</b> ``` x"],
                   suspicious_instructions=["ignore @all"])
    run(fake, [bad])
    _, pasted = pasted_text(fake)
    assert "&lt;img" in pasted and "@&#8203;evil" in pasted and "&lt;b&gt;@&#8203;x" in pasted
    assert "<img" not in pasted and "@evil" not in pasted and "@x" not in pasted
    assert "ignore @&#8203;all" in pasted
    assert pasted.strip().startswith("`````markdown") and pasted.strip().endswith("`````")  # longer than any run inside


def test_title_and_text_are_length_capped():
    assert len(ho.pr_title(1, "x" * 5000)) == ho.MAX_TITLE and "\n" not in ho.pr_title(1, "a\nb\r\nc")
    fake = IssueGh(comments=[comment(REPRO, cid=4), comment(ANALYSIS_RC)], head="h" * 40)
    run(fake, [approved(1, findings=["y" * 5000] * 9, summary="s" * 5000)])
    [text] = fake.comment_bodies()
    assert len(text) < 6000 and "y" * (ho.MAX_FINDING + 1) not in text and "s" * 1001 not in text


def test_a_rerun_updates_the_one_comment_in_place():
    fake = IssueGh(comments=[comment(f"{ho.MARKER}\nold", cid=9)], head="h" * 40)
    run(fake, [approved()])
    [call] = fake.writes()
    assert fake.method(call) == "PATCH" and fake.url(call).endswith("/issues/comments/9")


def test_nothing_to_hand_over_without_an_approved_last_round_or_branch():
    fake = IssueGh(head="h" * 40)
    assert "no approved round" in run(fake, [rec(1)]) and "no approved round" in run(fake, [])
    gone = IssueGh(head=None)
    assert "no longer exists" in run(gone, [approved()])
    assert fake.writes() == [] and gone.writes() == []


def test_missing_analysis_and_repro_comments_fall_back_to_pointers():
    fake = IssueGh(head="h" * 40)
    run(fake, [approved()], {"maintainers": []})
    [text] = fake.comment_bodies()
    assert "Maintainers:" in text and "see the analysis comment" in text and "see the reproduction comment" in text


def test_handover_cli_reads_the_records_and_respects_ai_off(monkeypatch, tmp_path):
    (tmp_path / "records/fix-round-1").mkdir(parents=True)
    (tmp_path / "records/fix-round-1/round.json").write_text(json.dumps(approved()))
    monkeypatch.setenv("AIWF_CONFIG", json.dumps(CFG))
    for labels, n in (([], 1), (["ai: off"], 0)):
        fake = IssueGh(comments=[comment(ANALYSIS_RC)], head="h" * 40, labels=labels)
        monkeypatch.setattr(ho.config, "run_gh", fake)
        assert cli.main(["fix-handover", "--repo", REPO, "--issue", "1", "--records", str(tmp_path / "records")]) == 0
        assert len(fake.comment_bodies()) == n
