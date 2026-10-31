"""Independent acceptance-test review (ADR-0014): does tests/e2e/test_wp<N>.py enforce the WP's Done-when?"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schema" / "verifier.json"
PROMPT_PATH = ROOT / "prompts" / "verifier.md"
E2E_DIR = ROOT / "tests" / "e2e"


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
    if verdict["verdict"] == "pass" and verdict["gaps"]:
        raise VerifyError("verdict is pass but gaps is not empty")
    return verdict


def test_files(wp: str) -> list[Path]:
    """The WP's acceptance test followed by its helpers (every other non-test module in tests/e2e).

    A split WP (WP2a) uses its own test_wp2a.py, else its WP's test_wp2.py (ADR-0046).
    """
    test = E2E_DIR / f"test_{wp.lower()}.py"
    if not test.is_file() and wp[-1:].isalpha():
        test = E2E_DIR / f"test_{wp[:-1].lower()}.py"
    if not test.is_file():
        raise VerifyError(f"no acceptance test {(E2E_DIR / f'test_{wp.lower()}.py').relative_to(ROOT)}")
    helpers = sorted(p for p in E2E_DIR.glob("*.py") if not p.name.startswith("test_") and p.name != "__init__.py")
    return [test, *helpers]


def build_pack(wp: str) -> str:
    spec = (ROOT / "docs" / "spec.md").read_text()
    condition = done_when((ROOT / "docs" / "plan.md").read_text(), wp)
    files = "\n".join(f'<file path="{p.relative_to(ROOT)}">\n{p.read_text()}\n</file>' for p in test_files(wp))
    return (
        f"<spec>\n{spec}\n</spec>\n\n<done_when wp=\"{wp}\">\n{condition}\n</done_when>\n\n"
        f"<acceptance_test>\n{files}\n</acceptance_test>\n"
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
    p = argparse.ArgumentParser(prog="verify-wp", description="Independent review: does the WP's acceptance test enforce its 'Done when'?")
    p.add_argument("wp", help="work package id, e.g. WP0")
    p.add_argument("--print-pack", action="store_true", help="print the review pack and exit")
    args = p.parse_args(argv)
    try:
        pack = build_pack(args.wp)
        if args.print_pack:
            print(pack)
            return 0
        verdict = parse_verdict(ask_model(pack))
    except VerifyError as exc:
        print(f"verify-wp: error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(verdict, indent=2))
    return 0 if verdict["verdict"] == "pass" else 1
