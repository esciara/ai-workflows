"""Claims tied to agent lifetime (ADR-0015): assignment, heartbeat, release and reaper, driven by Claude Code hooks.

Push model, parent-side binding: the orchestrator spawns a track agent with the Agent tool, `run_in_background: true`
and a description starting with the bead id (`aiwf-wp2: ...`). PreToolUse(Agent) claims the bead (or denies the spawn);
PostToolUse(Agent) binds it to the `agentId` of the tool response; PostToolUse(SendMessage) re-binds a resumed agent.
State lives in `.beads/aiwf-claims.json` of the main checkout (not in git).
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


BEAD_IN_DESCRIPTION = re.compile(r"^(aiwf-[a-z0-9]+(?:\.[0-9]+)*):")


def actor_for(bead: str) -> str:
    return f"track-{bead}"


def bead_of(tool_input: dict) -> str | None:
    """Bead id of an Agent call: its description must start with `<bead>:`."""
    m = BEAD_IN_DESCRIPTION.match(str((tool_input or {}).get("description", "")))
    return m.group(1) if m else None


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
        for key, empty in (("agents", {}), ("heartbeats", {}), ("loops", {}), ("reaper", 0)):
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


def _issue(root: Path, bead: str) -> dict | None:
    show = bd(root, "show", bead, "--json")
    return _json(show) if show.returncode == 0 else None


def _holds(issue: dict | None, actor: str) -> bool:
    return bool(issue) and issue.get("status") == "in_progress" and issue.get("assignee") == actor


# ---------------------------------------------------------------- actions


def claim(root: Path, bead: str) -> str | None:
    """Claim `bead` for its track actor; None on success (also when that actor already holds it), else why not."""
    actor = actor_for(bead)
    if _holds(_issue(root, bead), actor):
        return None
    r = bd(root, "update", bead, "--claim", "--actor", actor)
    return None if r.returncode == 0 else (r.stderr.strip() or r.stdout.strip() or "claim failed")


def bind(root: Path, agent_id: str, bead: str, session_id: str) -> None:
    with state(root) as s:
        s["agents"][agent_id] = {"bead": bead, "actor": actor_for(bead), "session_id": session_id, "active": True}


def rebind(root: Path, agent_id: str, session_id: str) -> None:
    """A released agent resumed by SendMessage: track it again if its bead is still assigned to it or in_review."""
    with state(root) as s:
        entry = s["agents"].get(agent_id)
    if not entry or entry["active"]:
        return
    issue = _issue(root, entry["bead"])
    if _holds(issue, entry["actor"]) or (issue or {}).get("status") == "in_review":
        with state(root) as s:
            s["agents"][agent_id].update(active=True, session_id=session_id)


def release_bead(root: Path, bead: str, actor: str) -> bool:
    """Unclaim `bead` if `actor` still holds it in_progress, and free the merge slot if `actor` holds it."""
    for attempt in range(RETRIES):
        issue = _issue(root, bead)
        ok = issue is not None
        if _holds(issue, actor):
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
    """Unknown agent ids (not bound yet, or not a track) are a no-op. The entry is kept, inactive, for a re-bind."""
    with state(root) as s:
        entry = s["agents"].get(agent_id)
    if entry and entry["active"] and release_bead(root, entry["bead"], entry["actor"]):
        with state(root) as s:
            s["agents"][agent_id]["active"] = False
            s["heartbeats"].pop(entry["bead"], None)


def release_session(root: Path, session_id: str) -> None:
    """Session over (SessionEnd, or its Claude process died): release its agents' beads and forget them."""
    with state(root) as s:
        agents = [a for a, e in s["agents"].items() if e["session_id"] == session_id]
    for agent_id in agents:
        release_agent(root, agent_id)
    with state(root) as s:
        s["agents"] = {a: e for a, e in s["agents"].items() if e["session_id"] != session_id or e["active"]}
        s["loops"].pop(session_id, None)


def heartbeat(root: Path, session_id: str, now: float) -> None:
    with state(root) as s:
        held = [e for e in s["agents"].values() if e["session_id"] == session_id and e["active"]]
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
    with contextlib.suppress(Exception):  # crash or kill -9 of Claude: no SessionEnd, so release here
        release_session(root, session_id)


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


def _deny(msg: str) -> int:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": msg}}))
    return 0


def hook(event: str, payload: dict) -> int:
    cwd = payload.get("cwd") or os.getcwd()
    agent_id = payload.get("agent_id")
    tool_input = payload.get("tool_input") or {}
    if event == "pre-bash":
        reason = guard(tool_input.get("command", "")) if agent_id else None
        if reason:
            return _deny(f"{reason} is reserved to the orchestrator (ADR-0015, push model): track agents never claim, assign, unclaim, reclaim or force. Ask the orchestrator.")
        return 0
    bead = bead_of(tool_input) if event in ("pre-agent", "post-agent") else None
    if event == "pre-agent" and bead:
        if agent_id:
            return _deny(f"only the orchestrator spawns track agents ({bead}, ADR-0015).")
        if tool_input.get("run_in_background") is not True:
            return _deny(f"a track agent ({bead}) must be spawned with run_in_background: true (ADR-0015): only a background launch returns its agent id at once, to bind the claim to it.")
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
    elif event == "pre-agent" and bead:
        reason = claim(root, bead)
        if reason:
            return _deny(f"cannot claim {bead} for {actor_for(bead)} (ADR-0015): {reason}")
    elif event == "post-agent" and bead:
        response = payload.get("tool_response")
        if isinstance(response, dict) and response.get("agentId") and response.get("status") == "async_launched":
            bind(root, response["agentId"], bead, session_id)
    elif event == "post-send" and tool_input.get("to"):
        rebind(root, tool_input["to"], session_id)
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
    h.add_argument("event", choices=["session-start", "pre-agent", "post-agent", "post-send", "subagent-stop", "task-stop", "stop-failure", "session-end", "pre-bash"])
    lp = sub.add_parser("loop", help="internal: heartbeat loop of one session")
    lp.add_argument("session_id")
    lp.add_argument("parent_pid", type=int)
    args = ap.parse_args(argv)
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
