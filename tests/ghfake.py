"""Shared fake for the `gh` runner (`gh(args) -> stdout`, raising RuntimeError like config.run_gh on failure).

Subclass and override `respond` to answer calls; every call is recorded in `calls`. `method` and `url` read the HTTP
verb and the `repos/...` path out of an `api` argument list, the two things every fake used to parse by hand.
"""

from __future__ import annotations


class RecordingGh:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> str:
        self.calls.append(args)
        return self.respond(args)

    def respond(self, args: list[str]) -> str:
        return "{}"

    @staticmethod
    def method(args: list[str]) -> str:
        return args[args.index("-X") + 1] if "-X" in args else "GET"

    @staticmethod
    def url(args: list[str]) -> str:
        return next(a for a in args[1:] if a.startswith("repos/"))

    def writes(self, method: str | None = None) -> list[list[str]]:
        """Calls that are not GETs (only those with this HTTP verb when given)."""
        found = [c for c in self.calls if self.method(c) != "GET"]
        return [c for c in found if method is None or self.method(c) == method]
