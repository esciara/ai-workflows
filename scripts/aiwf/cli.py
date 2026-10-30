"""Command-line entry point: `aiwf config ...`."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from aiwf import config


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
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
