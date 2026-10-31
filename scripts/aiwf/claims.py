"""Claims tied to agent lifetime (ADR-0015): assignment, heartbeat, release and reaper, driven by Claude Code hooks.

Push model: the orchestrator runs `assign` just before spawning a track agent; SubagentStart binds that pending
assignment to the agent's `agent_id`. State lives in `.beads/aiwf-claims.json` of the main checkout (not in git).
Hooks never fail the tool call: every error ends in exit 0, except the deliberate PreToolUse deny. Stdlib only.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

STATE_NAME = "aiwf-claims.json"
HEARTBEAT_EVERY = 120  # loop period, s; bd lease TTL is 5 min
HEARTBEAT_MIN_GAP = 60  # at most one heartbeat per bead per minute
REAP_EVERY = 120  # reaper rate limit, s
REAP_WINDOW = 600  # reaper's previous run older than this: the machine slept, skip once
RECLAIM_OLDER_THAN = "10m"
RETRIES = 3
SHELLS = {"sh", "bash", "zsh", "dash", "fish"}
RUN = subprocess.run  # replaced in tests
SLEEP = time.sleep


def actor_for(bead: str) -> str:
    return f"track-{bead}"


# ---------------------------------------------------------------- guard


_SEP = re.compile(r"\|\||&&|[;|&\n]")
_ASSIGN_SUBCOMMANDS = {"update", "create", "q", "edit"}
_FORBIDDEN_SUBCOMMANDS = {"reclaim", "unclaim", "assign"}


def guard(command: str) -> str | None:
    """Why a track agent may not run `command`, or None. Best effort: matches command text."""
    for segment in _SEP.split(command):
        try:
            words = shlex.split(segment)
        except ValueError:
            words = segment.split()
        for i, w in enumerate(words):
            if os.path.basename(w) != "bd":
                continue
            rest = words[i + 1 :]
            sub = next((x for x in rest if not x.startswith("-")), "")
            if sub in _FORBIDDEN_SUBCOMMANDS:
                return f"`bd {sub}`"
            for x in rest:
                flag = x.split("=", 1)[0]
                if flag in ("--claim", "--force"):
                    return f"`bd {flag}`"
                if sub in _ASSIGN_SUBCOMMANDS and flag in ("--assignee", "-a"):
                    return f"`bd {sub} {flag}`"
    return None


# ---------------------------------------------------------------- state


def beads_root(cwd: str | os.PathLike) -> Path | None:
    """Main checkout holding `.beads/`, or None when bd or the board is missing (cloud sessions, CI)."""
    if shutil.which("bd") is None:
        return None
    r = RUN(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=cwd, capture_output=True, text=True, timeout=5)
    if r.returncode != 0:
        return None
    root = Path(r.stdout.strip()).parent
    return root if (root / ".beads").is_dir() else None


@contextlib.contextmanager
def state(root: Path):
    path = root / ".beads" / STATE_NAME
    with open(root / ".beads" / "aiwf-claims.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            data = json.loads(path.read_text()) if path.exists() else {}
        except json.JSONDecodeError:
            data = {}
        for key, empty in (("pending", []), ("agents", {}), ("heartbeats", {}), ("loops", {}), ("reaper", 0)):
            data.setdefault(key, empty)
        yield data
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1, sort_keys=True))
        tmp.replace(path)


def bd(root: Path, *args: str, timeout: float = 15) -> subprocess.CompletedProcess:
    return RUN(["bd", *args], cwd=root, capture_output=True, text=True, timeout=timeout)


def _json(r: subprocess.CompletedProcess) -> dict:
    data = json.loads(r.stdout)
    return data[0] if isinstance(data, list) else data


# ---------------------------------------------------------------- actions


def assign(root: Path, bead: str, agent_type: str = "general-purpose") -> int:
    actor = actor_for(bead)
    r = bd(root, "update", bead, "--claim", "--actor", actor)
    if r.returncode != 0:
        print(f"board-assign: {bead}: {r.stderr.strip() or r.stdout.strip()}", file=sys.stderr)
        return 1
    with state(root) as s:
        s["pending"].append({"bead": bead, "actor": actor, "agent_type": agent_type})
    print(f"{bead} assigned to {actor}; spawn its agent ({agent_type}) now")
    return 0


def bind(root: Path, agent_id: str, agent_type: str, session_id: str) -> None:
    with state(root) as s:
        for i, p in enumerate(s["pending"]):
            if p["agent_type"] in (agent_type, "*"):
                s["pending"].pop(i)
                s["agents"][agent_id] = {"bead": p["bead"], "actor": p["actor"], "session_id": session_id}
                return


def release_bead(root: Path, bead: str, actor: str) -> bool:
    """Unclaim `bead` if `actor` still holds it in_progress, and free the merge slot if `actor` holds it."""
    for attempt in range(RETRIES):
        ok = True
        show = bd(root, "show", bead, "--json")
        if show.returncode != 0:
            ok = False
        else:
            issue = _json(show)
            if issue.get("status") == "in_progress" and issue.get("assignee") == actor:
                ok = bd(root, "unclaim", bead, "--if-assignee", actor, "--reason", "agent ended (ADR-0015 hook)").returncode == 0
        slot = bd(root, "merge-slot", "check", "--json")
        if slot.returncode == 0 and _json(slot).get("holder") == actor:
            ok = bd(root, "merge-slot", "release", "--holder", actor).returncode == 0 and ok
        if ok:
            return True
        if attempt + 1 < RETRIES:
            SLEEP(0.5)
    return False


def release_agent(root: Path, agent_id: str) -> None:
    with state(root) as s:
        entry = s["agents"].get(agent_id)
    if entry and release_bead(root, entry["bead"], entry["actor"]):
        with state(root) as s:
            s["agents"].pop(agent_id, None)
            s["heartbeats"].pop(entry["bead"], None)


def release_session(root: Path, session_id: str) -> None:
    """Session over: release its agents' beads and assignments no agent picked up."""
    with state(root) as s:
        agents = {a: e for a, e in s["agents"].items() if e["session_id"] == session_id}
        pending = list(s["pending"])
    for agent_id in agents:
        release_agent(root, agent_id)
    done = [p for p in pending if release_bead(root, p["bead"], p["actor"])]
    with state(root) as s:
        s["pending"] = [p for p in s["pending"] if p not in done]
        s["loops"].pop(session_id, None)


def heartbeat(root: Path, session_id: str, now: float) -> None:
    with state(root) as s:
        held = [e for e in s["agents"].values() if e["session_id"] == session_id] + list(s["pending"])
        due = [e for e in held if now - s["heartbeats"].get(e["bead"], 0) >= HEARTBEAT_MIN_GAP]
        for e in due:
            s["heartbeats"][e["bead"]] = now
    for e in due:
        bd(root, "heartbeat", e["bead"], "--actor", e["actor"])  # fails harmlessly once the bead is in_review or closed


def reap(root: Path, now: float) -> str:
    with state(root) as s:
        last = s["reaper"]
        if now - last < REAP_EVERY:
            return "rate-limited"
        s["reaper"] = now
    if last and now - last > REAP_WINDOW:
        return "skipped: previous run too old (machine slept?)"
    bd(root, "reclaim", "--older-than", RECLAIM_OLDER_THAN)
    return "ran"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def claude_pid() -> int:
    """The Claude Code process: the first ancestor of the hook that is not a shell (the hook runs under sh/bash)."""
    pid = os.getppid()
    for _ in range(4):
        r = RUN(["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
        parts = r.stdout.split(None, 1)
        if len(parts) != 2 or os.path.basename(parts[1].strip()).lstrip("-") not in SHELLS:
            return pid
        pid = int(parts[0])
    return pid


def loop(root: Path, session_id: str, parent_pid: int) -> None:
    next_beat = 0.0
    while _alive(parent_pid):
        now = time.time()
        if now >= next_beat:
            with contextlib.suppress(Exception):
                heartbeat(root, session_id, now)
                reap(root, now)
            next_beat = now + HEARTBEAT_EVERY
        SLEEP(5)


def start_loop(root: Path, session_id: str, parent_pid: int) -> None:
    with state(root) as s:
        pid = s["loops"].get(session_id)
        if pid and _alive(pid):
            return
        scripts = str(Path(__file__).resolve().parents[1])
        proc = subprocess.Popen(
            [sys.executable, "-c", "import sys; from aiwf.claims import main; sys.exit(main(sys.argv[1:]))", "loop", session_id, str(parent_pid)],
            cwd=root,
            env={**os.environ, "PYTHONPATH": scripts},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        s["loops"][session_id] = proc.pid


def stale_warning(cwd: str) -> str | None:
    from aiwf import board, generated

    top = RUN(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True, timeout=5)
    root = Path(top.stdout.strip())
    msgs = generated.stale(root, board.fresh_export(root, timeout=15))
    if not msgs:
        return None
    return "aiwf (ADR-0015): a sync PR is due: " + "; ".join(msgs) + ". Orchestrator: branch sync-<date>, run render-progress, render-adr-index, render-diagrams."


# ---------------------------------------------------------------- hook entry


def hook(event: str, payload: dict) -> int:
    cwd = payload.get("cwd") or os.getcwd()
    agent_id = payload.get("agent_id")
    if event == "pre-bash":
        reason = guard((payload.get("tool_input") or {}).get("command", "")) if agent_id else None
        if reason:
            msg = f"{reason} is reserved to the orchestrator (ADR-0015, push model): track agents never claim, assign, unclaim, reclaim or force. Ask the orchestrator."
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": msg}}))
        return 0
    root = beads_root(cwd)
    if root is None:
        return 0
    session_id = payload.get("session_id", "")
    now = time.time()
    if event == "session-start":
        start_loop(root, session_id, claude_pid())
        reap(root, now)
        if not agent_id:
            warning = stale_warning(cwd)
            if warning:
                print(warning)
    elif event == "subagent-start" and agent_id:
        bind(root, agent_id, payload.get("agent_type", ""), session_id)
    elif event in ("subagent-stop", "stop-failure") and agent_id:
        release_agent(root, agent_id)
        reap(root, now)
    elif event == "task-stop":
        task_id = (payload.get("tool_input") or {}).get("task_id")
        if task_id:
            release_agent(root, task_id)
    elif event == "session-end":
        release_session(root, session_id)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="claims", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hook", help="Claude Code hook entry; reads the hook JSON on stdin")
    h.add_argument("event", choices=["session-start", "subagent-start", "subagent-stop", "task-stop", "stop-failure", "session-end", "pre-bash"])
    a = sub.add_parser("assign", help="orchestrator: claim a bead for its track agent, just before spawning it")
    a.add_argument("bead")
    a.add_argument("--agent-type", default="general-purpose", help="subagent type of the agent to bind ('*' for any)")
    lp = sub.add_parser("loop", help="internal: heartbeat loop of one session")
    lp.add_argument("session_id")
    lp.add_argument("parent_pid", type=int)
    args = ap.parse_args(argv)
    if args.cmd == "assign":
        root = beads_root(os.getcwd())
        if root is None:
            print("board-assign: bd or .beads/ not found", file=sys.stderr)
            return 2
        return assign(root, args.bead, args.agent_type)
    if args.cmd == "loop":
        loop(Path.cwd(), args.session_id, args.parent_pid)
        return 0
    try:
        return hook(args.event, json.loads(sys.stdin.read() or "{}"))
    except Exception as exc:  # a hook must never fail the tool call
        print(f"aiwf claims hook {args.event}: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
