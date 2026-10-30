"""Load, validate and normalise a target repo's .github/ai-workflows.yml."""

from __future__ import annotations

import base64
import copy
import json
import subprocess
from pathlib import Path
from typing import Any, Callable

import yaml
from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "ai-workflows.schema.json"
DEFAULT_CONFIG_PATH = ".github/ai-workflows.yml"

GhRunner = Callable[[list[str]], str]


class ConfigError(Exception):
    """Invalid or unreadable config. `errors` holds one 'path: reason' line per problem."""

    def __init__(self, source: str, errors: list[str]):
        self.source = source
        self.errors = errors
        super().__init__(f"{source}: " + "; ".join(errors))


def run_gh(args: list[str]) -> str:
    """Run the gh CLI (auth via GH_TOKEN in env, never passed on the command line)."""
    proc = subprocess.run(["gh", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"gh exited with {proc.returncode}")
    return proc.stdout


def load_schema(path: Path = SCHEMA_PATH) -> dict[str, Any]:
    return json.loads(path.read_text())


def fetch_from_repo(repo: str, path: str, ref: str | None = None, gh: GhRunner | None = None) -> tuple[str, str]:
    """Return (text, source) for `path` in `repo` at `ref` (default: the repo's default branch)."""
    gh = gh or run_gh
    if not ref:
        try:
            ref = gh(["api", f"repos/{repo}", "--jq", ".default_branch"]).strip()
        except RuntimeError as exc:
            raise ConfigError(repo, [f"cannot read repo metadata: {exc}"]) from None
    source = f"{repo}:{path}@{ref}"
    try:
        raw = gh(["api", f"repos/{repo}/contents/{path}?ref={ref}"])
    except RuntimeError as exc:
        reason = "file not found" if "404" in str(exc) or "Not Found" in str(exc) else str(exc)
        raise ConfigError(source, [reason]) from None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise ConfigError(source, ["unexpected response from GitHub contents API"]) from None
    if not isinstance(payload, dict) or payload.get("type") != "file":
        raise ConfigError(source, ["path is not a file"])
    try:
        text = base64.b64decode(payload.get("content", "")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        raise ConfigError(source, ["content is not valid base64/UTF-8"]) from None
    return text, source


def parse(text: str, source: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"line {mark.line + 1}" if mark else "file"
        raise ConfigError(source, [f"{where}: invalid YAML ({getattr(exc, 'problem', exc)})"]) from None
    if data is None:
        raise ConfigError(source, ["file is empty"])
    if not isinstance(data, dict):
        raise ConfigError(source, ["top level must be a mapping"])
    return data


def _path(parts) -> str:
    out = "$"
    for p in parts:
        out += f"[{p}]" if isinstance(p, int) else f".{p}"
    return out


def validate(data: dict[str, Any], source: str, schema: dict[str, Any] | None = None) -> None:
    schema = schema or load_schema()
    errors = [
        f"{_path(e.absolute_path)}: {e.message}"
        for e in sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(map(str, e.absolute_path)))
    ]
    if errors:
        raise ConfigError(source, errors)


def apply_defaults(data: dict[str, Any], schema: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a copy of `data` with every schema `default` filled in, recursively."""
    schema = schema or load_schema()

    def fill(node: Any, sch: dict[str, Any]) -> Any:
        if not isinstance(node, dict):
            return node
        for key, sub in sch.get("properties", {}).items():
            if key not in node and "default" in sub:
                node[key] = copy.deepcopy(sub["default"])
            if key in node:
                node[key] = fill(node[key], sub)
        return node

    return fill(copy.deepcopy(data), schema)


def check_semantics(cfg: dict[str, Any], source: str) -> None:
    d = cfg["reporter_silence_days"]
    if not d["ping"] < d["stale"] < d["close"]:
        raise ConfigError(
            source,
            [f"$.reporter_silence_days: must satisfy ping < stale < close (got {d['ping']}, {d['stale']}, {d['close']})"],
        )


def load(text: str, source: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
    schema = schema or load_schema()
    data = parse(text, source)
    validate(data, source, schema)
    cfg = apply_defaults(data, schema)
    check_semantics(cfg, source)
    return cfg


def summary(cfg: dict[str, Any], source: str) -> str:
    wf = cfg["workflows"]
    lines = [
        f"Config OK: {source}",
        f"  enabled:          {cfg['enabled']}",
        f"  maintainers:      {', '.join(cfg['maintainers'])}",
        f"  workflows:        review={wf['review']} triage={wf['triage']}",
        f"  setup / test:     {cfg.get('setup', '-')} / {cfg.get('test', '-')}",
        f"  risk_paths:       high={len(cfg['risk_paths']['high'])} medium={len(cfg['risk_paths']['medium'])} patterns",
        f"  limits:           {cfg['limits']}",
        f"  silence days:     {cfg['reporter_silence_days']}",
        f"  notify/fork_prs:  {cfg['notify']} / {cfg['fork_prs']}",
    ]
    if "model" in cfg:
        lines.append(f"  model:            {cfg['model']}")
    if "required_checks" in cfg:
        lines.append(f"  required_checks:  {', '.join(cfg['required_checks'])}")
    return "\n".join(lines)


def github_outputs(cfg: dict[str, Any]) -> dict[str, str]:
    return {
        "config": json.dumps(cfg, separators=(",", ":"), sort_keys=True),
        "enabled": json.dumps(cfg["enabled"]),
        "review": json.dumps(cfg["enabled"] and cfg["workflows"]["review"]),
        "triage": json.dumps(cfg["enabled"] and cfg["workflows"]["triage"]),
    }
