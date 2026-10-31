"""Static security policy for GitHub workflow files (run by tests/test_workflow_policy.py)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

SHA_RE = re.compile(r"@[0-9a-f]{40}$")
VERSION_COMMENT_RE = re.compile(r"#\s*v\d")
USES_LINE_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*['\"]?([^'\"\s#]+)['\"]?(.*)$")
AGENT_MARKER_RE = re.compile(r"#\s*aiwf:\s*agent\b")
PR_HEAD_RE = re.compile(r"github\.event\.pull_request\.head\.(?:ref|sha)|refs/pull/")
TOKEN_RE = re.compile(r"GITHUB_TOKEN|github\.token")
SECRET_RE = re.compile(r"secrets\.([A-Za-z0-9_]+)")
EVENT_EXPR_RE = re.compile(r"\$\{\{[^}]*\bgithub\.(?:event\.|head_ref)")
CHECKOUT_ACTION = "actions/checkout"
AGENT_ACTION = "anthropics/claude-code-action"
ALLOWED_AGENT_SECRET = "CLAUDE_CODE_OAUTH_TOKEN"
OWN_REUSABLE_PREFIX = "esciara/ai-workflows/"


def is_exempt(ref: str) -> bool:
    return ref.startswith("./") or ref.startswith(OWN_REUSABLE_PREFIX)


def load_workflow(text: str) -> dict[str, Any] | None:
    """Parsed workflow, or None when the file is not a workflow (no `jobs:`)."""
    doc = yaml.safe_load(text)
    if not isinstance(doc, dict) or not isinstance(doc.get("jobs"), dict):
        return None
    return doc


def triggers(doc: dict[str, Any]) -> set[str]:
    on = doc.get("on", doc.get(True))  # PyYAML parses a bare `on:` key as True
    if isinstance(on, str):
        return {on}
    if isinstance(on, (list, dict)):
        return set(on)
    return set()


def job_blocks(text: str) -> dict[str, str]:
    """Raw text of each job under `jobs:` (comments kept, unlike the parsed YAML)."""
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if re.match(r"^jobs:\s*(#.*)?$", line))
    except StopIteration:
        return {}
    blocks: dict[str, list[str]] = {}
    current = None
    indent = None
    for line in lines[start + 1 :]:
        if line.strip() == "" or (line.lstrip().startswith("#") and current is None):
            continue
        if not line.startswith(" ") and not line.startswith("#"):
            break  # next top-level key
        width = len(line) - len(line.lstrip())
        m = re.match(r"^(\s+)([A-Za-z0-9_-]+):\s*(#.*)?$", line)
        if m and (indent is None or width == indent) and not line.lstrip().startswith("#"):
            indent = width
            current = m.group(2)
            blocks[current] = []
        if current is not None:
            blocks[current].append(line)
    return {name: "\n".join(body) for name, body in blocks.items()}


def has_write(perms: Any) -> bool:
    if perms == "write-all":
        return True
    if isinstance(perms, dict):
        return any(v == "write" for v in perms.values())
    return False


def is_agent_job(job: dict[str, Any], raw: str) -> bool:
    for step in job.get("steps") or []:
        if isinstance(step, dict) and str(step.get("uses", "")).startswith(AGENT_ACTION):
            return True
    return bool(AGENT_MARKER_RE.search(raw))


def check_text(text: str) -> list[str]:
    """Policy violations in one workflow file, as 'rule: detail' strings. [] for non-workflows."""
    doc = load_workflow(text)
    if doc is None:
        return []
    errors: list[str] = []

    # Pinning: every external `uses:` is a full SHA with a version comment on the same line.
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        m = USES_LINE_RE.match(line)
        if not m or is_exempt(m.group(1)):
            continue
        ref, rest = m.group(1), m.group(2)
        if ref.startswith("docker://"):
            if "@sha256:" not in ref:
                errors.append(f"unpinned: line {n}: {ref} (docker image needs @sha256 digest)")
        elif not SHA_RE.search(ref):
            errors.append(f"unpinned: line {n}: {ref} (needs a 40-hex commit SHA)")
        elif not VERSION_COMMENT_RE.search(rest):
            errors.append(f"unpinned: line {n}: {ref} (needs a '# vX' version comment)")

    # Top level: `permissions: {}`, so a job without its own block gets nothing (ADR-0017).
    top = doc.get("permissions")
    if top is None:
        errors.append("permissions: no top-level permissions (needs `permissions: {}`)")
    elif has_write(top):
        errors.append("permissions: top-level permissions grant write")
    elif top != {}:
        errors.append("permissions: top-level permissions must be `{}`")

    blocks = job_blocks(text)
    for name, job in doc["jobs"].items():
        if not isinstance(job, dict):
            continue
        perms = job.get("permissions")
        if perms is None:
            errors.append(f"permissions: job '{name}' has no explicit permissions")
        elif perms == "write-all":
            errors.append(f"permissions: job '{name}' uses write-all")
        if job.get("secrets") == "inherit":
            errors.append(f"secrets-inherit: job '{name}' uses secrets: inherit")
        if is_agent_job(job, blocks.get(name, "")):
            body = json.dumps(job)
            if TOKEN_RE.search(body):
                errors.append(f"agent-secrets: agent job '{name}' references GITHUB_TOKEN / github.token")
            for secret in sorted(set(SECRET_RE.findall(body)) - {ALLOWED_AGENT_SECRET}):
                errors.append(f"agent-secrets: agent job '{name}' references secrets.{secret}")
            if perms is not None and perms != {}:  # agent jobs get no token scope at all (ADR-0018)
                errors.append(f"agent-permissions: agent job '{name}' must have `permissions: {{}}`")

    if "pull_request_target" in triggers(doc) and PR_HEAD_RE.search(json.dumps(doc)):
        errors.append("pull-request-target: pull_request_target workflow checks out the PR head")
    errors += pull_request_target_jobs(doc)
    return errors


def pull_request_target_jobs(doc: dict[str, Any]) -> list[str]:
    """ADR-0044: code that can run on `pull_request_target` (the trigger, or a job whose `if:` names it) makes API calls
    only: no checkout at all, no event data in `run:` (env vars instead), and no secrets in a job that runs on it."""
    on_trigger = "pull_request_target" in triggers(doc)
    errors = []
    for name, job in doc["jobs"].items():
        if not isinstance(job, dict):
            continue
        named = "pull_request_target" in str(job.get("if", ""))
        if not (on_trigger or named):
            continue
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            if str(step.get("uses", "")).startswith(CHECKOUT_ACTION):
                errors.append(f"pull-request-target: job '{name}' checks out code (API calls only)")
            if EVENT_EXPR_RE.search(str(step.get("run", ""))):
                errors.append(f"pull-request-target: job '{name}' puts event data in run: (pass it through env)")
        if named and SECRET_RE.search(json.dumps(job)):
            errors.append(f"pull-request-target: job '{name}' runs on pull_request_target with secrets")
    return errors


def check_file(path: Path) -> list[str]:
    return check_text(path.read_text())
