"""Command-line entry point: `aiwf config|parse-command|labels-sync|publish ...`."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from aiwf import commands, config, labels, publish


def _write_outputs(path: str, outputs: dict[str, str]) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        for key, value in outputs.items():
            if "\n" in value:
                raise ValueError(f"output {key} must be single-line")
            fh.write(f"{key}={value}\n")


def cmd_config(args: argparse.Namespace) -> int:
    try:
        if args.file:
            text, source = Path(args.file).read_text(encoding="utf-8"), args.file
        else:
            text, source = config.fetch_from_repo(args.repo, args.path, args.ref or None)
        cfg = config.load(text, source)
    except config.ConfigError as exc:
        print(f"::error title=Invalid ai-workflows config::{exc.source}", file=sys.stderr)
        for err in exc.errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"::error title=Cannot read config::{exc}", file=sys.stderr)
        return 1
    print(config.summary(cfg, source))
    out = args.github_output or os.environ.get("GITHUB_OUTPUT")
    if out:
        _write_outputs(out, config.github_outputs(cfg))
    return 0


def cmd_parse_command(args: argparse.Namespace) -> int:
    """Untrusted inputs come from env vars, never from the command line."""
    cfg = json.loads(os.environ.get("AIWF_CONFIG") or "{}")
    cmd = commands.accept(
        os.environ.get("COMMENT_BODY", ""),
        os.environ.get("COMMENT_AUTHOR", ""),
        cfg.get("maintainers", []),
        args.repo,
        config.run_gh,
    )
    if cmd is None:
        print("no accepted command")
        return 0
    print(f"accepted command: /{cmd.name}")
    out = args.github_output or os.environ.get("GITHUB_OUTPUT")
    if out:
        _write_outputs(out, {"command": cmd.name, "args": json.dumps(cmd.args)})
    return 0


def cmd_labels_sync(args: argparse.Namespace) -> int:
    labels.sync(args.repo, config.run_gh)
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    ok = publish.publish(args.kind, os.environ.get("AGENT_JSON", ""), args.repo, args.issue, args.run_url, config.run_gh)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aiwf")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("config", help="load and validate .github/ai-workflows.yml")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--repo", help="owner/name; read the file via the GitHub API")
    src.add_argument("--file", help="local file (tests, local runs)")
    p.add_argument("--path", default=config.DEFAULT_CONFIG_PATH)
    p.add_argument("--ref", default="", help="git ref; default is the repo's default branch")
    p.add_argument("--github-output", default=None, help="file to append outputs to (default $GITHUB_OUTPUT)")
    p.set_defaults(func=cmd_config)
    p = sub.add_parser("parse-command", help="accept a slash command (env COMMENT_BODY, COMMENT_AUTHOR, AIWF_CONFIG)")
    p.add_argument("--repo", required=True)
    p.add_argument("--github-output", default=None)
    p.set_defaults(func=cmd_parse_command)
    p = sub.add_parser("labels-sync", help="create or update the labels in schema/labels.yml")
    p.add_argument("--repo", required=True)
    p.set_defaults(func=cmd_labels_sync)
    p = sub.add_parser("publish", help="validate agent JSON (env AGENT_JSON) and post the result")
    p.add_argument("--kind", required=True, choices=["ping"])
    p.add_argument("--repo", required=True)
    p.add_argument("--issue", required=True, type=int)
    p.add_argument("--run-url", default="")
    p.set_defaults(func=cmd_publish)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
