"""Independent WP verifier: build an evidence pack, ask a fresh model, validate its verdict."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schema" / "verifier.json"
PROMPT_PATH = ROOT / "prompts" / "verifier.md"
DEFAULT_REPO = "esciara/ai-workflows"
LOG_HEAD, LOG_TAIL = 4000, 8000
RUN_URL_RE = re.compile(r"https://github\.com/([\w.-]+/[\w.-]+)/actions/runs/(\d+)")

Runner = Callable[[list[str]], str]


class VerifyError(Exception):
    pass


def run(cmd: list[str], stdin: str | None = None, cwd: str | None = None) -> str:
    proc = subprocess.run(cmd, input=stdin, capture_output=True, text=True, cwd=cwd)
    if proc.returncode != 0:
        raise VerifyError(f"{cmd[0]} {cmd[1]} failed: {proc.stderr.strip()[:500]}")
    return proc.stdout


def done_when(plan_text: str, wp: str) -> str:
    """The 'Done when' cell for `wp` from the WP table in docs/plan.md."""
    col = None
    for line in plan_text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if "Done when" in cells:
            col = cells.index("Done when")
        elif col is not None and cells[0] == wp and len(cells) > col:
            return cells[col]
    raise VerifyError(f"no 'Done when' entry for {wp} in docs/plan.md")


def run_links(body: str) -> list[tuple[str, str]]:
    """(repo, run id) for each distinct Actions run URL in `body`, in order."""
    seen: list[tuple[str, str]] = []
    for m in RUN_URL_RE.finditer(body):
        if (m.group(1), m.group(2)) not in seen:
            seen.append((m.group(1), m.group(2)))
    return seen


def truncate(text: str, head: int = LOG_HEAD, tail: int = LOG_TAIL) -> str:
    if len(text) <= head + tail:
        return text
    return f"{text[:head]}\n[... {len(text) - head - tail} chars cut ...]\n{text[-tail:]}"


def parse_verdict(raw: str) -> dict[str, Any]:
    """Validated verdict from `claude -p --output-format json` stdout."""
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        raise VerifyError("verifier output is not JSON") from None
    verdict = envelope.get("structured_output") if isinstance(envelope, dict) else None
    if verdict is None and isinstance(envelope, dict) and isinstance(envelope.get("result"), str):
        try:
            verdict = json.loads(envelope["result"])
        except json.JSONDecodeError:
            raise VerifyError("verifier result is not JSON") from None
    if verdict is None:
        verdict = envelope
    errors = sorted(Draft202012Validator(json.loads(SCHEMA_PATH.read_text())).iter_errors(verdict), key=str)
    if errors:
        raise VerifyError("verdict fails schema: " + "; ".join(e.message for e in errors))
    if verdict["verdict"] == "pass" and verdict["unmet"]:
        raise VerifyError("verdict is pass but unmet is not empty")
    return verdict


def build_pack(wp: str, pr: str, repo: str, gh: Runner) -> str:
    spec = (ROOT / "docs" / "spec.md").read_text()
    condition = done_when((ROOT / "docs" / "plan.md").read_text(), wp)
    body = gh(["pr", "view", pr, "--repo", repo, "--json", "body", "-q", ".body"])
    runs = []
    for run_repo, run_id in run_links(body):
        meta = gh(["run", "view", run_id, "--repo", run_repo, "--json", "conclusion,status,event,displayTitle,url"])
        try:
            log = gh(["run", "view", run_id, "--repo", run_repo, "--log"])
        except VerifyError as exc:
            log = f"(log unavailable: {exc})"
        runs.append(f'<run repo="{run_repo}" id="{run_id}">\n{meta.strip()}\n<log>\n{truncate(log)}\n</log>\n</run>')
    return (
        f"<spec>\n{spec}\n</spec>\n\n<done_when wp=\"{wp}\">\n{condition}\n</done_when>\n\n"
        f"<evidence>\n<pr_body>\n{body}\n</pr_body>\n" + "\n".join(runs) + "\n</evidence>\n"
    )


def ask_model(pack: str) -> str:
    schema = json.loads(SCHEMA_PATH.read_text())
    schema.pop("$schema", None)  # the CLI's validator does not resolve the 2020-12 meta-schema URI
    schema = json.dumps(schema)
    cmd = [
        "claude", "-p", "--model", "sonnet", "--tools", "", "--safe-mode", "--no-session-persistence",
        "--output-format", "json", "--json-schema", schema, "--system-prompt", PROMPT_PATH.read_text(),
    ]
    with tempfile.TemporaryDirectory() as empty:  # no repo files in the verifier's cwd
        return run(cmd, stdin=pack, cwd=empty)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="verify-wp", description="Independent check that a WP's PR evidence proves its 'Done when'.")
    p.add_argument("wp", help="work package id, e.g. WP0")
    p.add_argument("pr", help="PR number on --repo")
    p.add_argument("--repo", default=DEFAULT_REPO)
    p.add_argument("--print-pack", action="store_true", help="print the evidence pack and exit")
    args = p.parse_args(argv)
    try:
        pack = build_pack(args.wp, args.pr, args.repo, lambda a: run(["gh", *a]))
        if args.print_pack:
            print(pack)
            return 0
        verdict = parse_verdict(ask_model(pack))
    except VerifyError as exc:
        print(f"verify-wp: error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(verdict, indent=2))
    return 0 if verdict["verdict"] == "pass" else 1
