"""The committed board export `docs/board.jsonl` (ADR-0036): a stable, secret-scanned snapshot of the local beads database.

Only real board changes show up in it: volatile fields (lease, heartbeat, `updated_at`) and the merge-slot bead are
dropped, and records are sorted by id with sorted keys, so re-exporting an unchanged board gives the same bytes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD_PATH = ROOT / "docs" / "board.jsonl"
BD_EXPORT = ["bd", "export"]
# change without a real board change (leases, heartbeats, timestamps), or personal data (`owner` is an email address)
VOLATILE_FIELDS = frozenset({"updated_at", "lease_expires_at", "heartbeat_at", "owner"})
# the merge slot flips on every acquire/release; it is coordination state, not board content
EXCLUDED_LABELS = frozenset({"gt:slot"})


class BoardError(Exception):
    pass


class SecretScanError(Exception):
    pass


def normalize(records: list[dict]) -> list[dict]:
    out = []
    for r in records:
        if EXCLUDED_LABELS & set(r.get("labels") or []):
            continue
        out.append({k: v for k, v in r.items() if k not in VOLATILE_FIELDS})
    return sorted(out, key=lambda r: r["id"])


def dumps(records: list[dict]) -> str:
    return "".join(json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n" for r in records)


def parse(text: str) -> list[dict]:
    records = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BoardError(f"line {n}: {exc}") from exc
        if not isinstance(rec, dict) or "id" not in rec:
            raise BoardError(f"line {n}: expected a JSON object with an id")
        records.append(rec)
    return records


def fresh_export(cwd: Path = ROOT, timeout: float = 30) -> str:
    """`bd export` of the local database, normalised."""
    raw = subprocess.run(BD_EXPORT, cwd=cwd, check=True, capture_output=True, text=True, timeout=timeout).stdout
    return dumps(normalize(parse(raw)))


def scan_secrets(text: str) -> list[str]:
    """Rule ids of secrets gitleaks finds in `text`; raises SecretScanError if the scan cannot run."""
    exe = shutil.which("gitleaks")
    if exe is None:
        raise SecretScanError("gitleaks not installed; refusing to write the board export unscanned")
    proc = subprocess.run(
        [exe, "stdin", "--no-banner", "--redact", "-l", "error", "--report-format", "json", "--report-path", "-"],
        input=text,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode not in (0, 1):
        raise SecretScanError(f"gitleaks failed (exit {proc.returncode}): {proc.stderr.strip()}")
    try:
        findings = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise SecretScanError(f"unreadable gitleaks report: {exc}") from exc
    if proc.returncode == 1 and not findings:
        raise SecretScanError("gitleaks reported leaks but no findings")
    return sorted({f.get("RuleID", "?") for f in findings})
