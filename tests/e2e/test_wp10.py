"""WP10 acceptance test. Done when: after an approved fix loop, one issue comment mentions the maintainer, gives the
compare link from the default branch to `ai-fix/issue-<n>` with the title and the label `ai-fix` pre-filled, and holds
the PR body to paste; Workflow B opens no PR (spec: B6, ADR-0061).

Runs against the playground (AIWF_E2E=1) with an e2e slot (AIWF_E2E_SLOT=1|2|3|any, ADR-0056), like WP9: the coupon bug
from WP8 is opened by the tester App, gets the maintainer's `/reproduce` (B2, B3, B4), then `/fix` (B5, then B6).

1. Seeded bug, `/fix`: the run succeeds, the `handover` job ran and the escalation job did not. One comment (hidden
   marker) mentions each of `maintainers`, links to `compare/<default>...ai-fix/issue-<n>` with `labels=ai-fix` and a
   `title` naming the issue, and holds `Fixes #<n>` and a round-by-round log. No `fix: needs-maintainer`, no PR for the
   branch (open or closed).

Left to unit tests: escaping and length caps of untrusted text, URL encoding, the rerun updating the comment in place, a
deleted branch, `ai: off`. The nested Workflow A run on the PR the maintainer opens is outside B (ADR-0061).
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

from triage_core import bot_comments, e2e_config, labels
from triage_fix import (COUPON_BUG, COUPON_FILES, ESCALATE_JOB, FIX_MARKER, GUIDANCE, NEEDS_MAINTAINER, fix, fix_branch,
                        fix_prs, open_as_reporter, opened, reproduce_and_analyse, rounds, tag)  # noqa: F401 (fixtures)
import playground as pg

HANDOVER_MARKER = "<!-- ai-workflows:fix-pr -->"
HANDOVER_JOB = "triage / fix / handover"


def test_an_approved_fix_gives_the_compare_link_comment_and_opens_no_pr(e2e_target, tag, opened):
    issue = open_as_reporter("handover", COUPON_BUG, tag, opened)
    reproduce_and_analyse(issue, COUPON_FILES)

    _, run = fix(issue, GUIDANCE)
    n = issue["number"]
    assert rounds(run), run["jobs"]
    assert run["jobs"].get(HANDOVER_JOB) == "success", run["jobs"]
    assert run["jobs"].get(ESCALATE_JOB) in (None, "skipped"), run["jobs"]
    assert NEEDS_MAINTAINER not in labels(n)
    assert not bot_comments(n, FIX_MARKER), "an approved fix posted an escalation comment"

    default = pg.api(f"repos/{pg.REPO}")["default_branch"]
    branch = fix_branch(n)
    notes = bot_comments(n, HANDOVER_MARKER)
    assert len(notes) == 1, [c["html_url"] for c in notes]
    text = notes[0]["body"]
    print(text)
    for login in e2e_config()["maintainers"]:
        assert f"@{login}" in text, f"the hand-over comment does not mention {login}"
    link = re.search(r"\]\((https://\S+/compare/\S+)\)", text)
    assert link, "no compare link in the hand-over comment"
    url = urlsplit(link.group(1))
    q = parse_qs(url.query)
    assert url.path == f"/{pg.REPO}/compare/{default}...{branch}", url.path
    assert q.get("labels") == ["ai-fix"], q
    assert q.get("title") and f"#{n}" in q["title"][0], q
    pasted = text.split("PR description to paste:", 1)[1]
    assert f"Fixes #{n}" in pasted and re.search(r"- Round 1: ", pasted), pasted
    assert not fix_prs(n), "Workflow B opened a PR (ADR-0061)"
