"""Claims tied to agent lifetime (ADR-0015). No real bd: a fake records calls and answers from a tiny in-memory board."""

import io
import json
import subprocess
from pathlib import Path

import pytest

from aiwf import claims

ROOT = Path(__file__).resolve().parents[1]


class FakeBd:
    def __init__(self):
        self.issues = {}  # id -> {"status", "assignee"}
        self.slot_holder = None
        self.calls = []
        self.fail = set()  # subcommands that fail

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        out, rc = "", 0
        if cmd[0] == "bd":
            sub = cmd[1]
            if sub in self.fail:
                rc = 1
            elif sub == "update" and "--claim" in cmd:
                issue = self.issues.setdefault(cmd[2], {"status": "open", "assignee": None})
                if issue["assignee"] not in (None, cmd[-1]):
                    rc = 1
                else:
                    issue.update(status="in_progress", assignee=cmd[-1])
            elif sub == "show":
                out = json.dumps([{"id": cmd[2], **self.issues.get(cmd[2], {"status": "open"})}])
            elif sub == "unclaim":
                self.issues[cmd[2]].update(status="open", assignee=None)
            elif sub == "merge-slot" and cmd[2] == "check":
                out = json.dumps({"holder": self.slot_holder})
            elif sub == "merge-slot" and cmd[2] == "release":
                self.slot_holder = None
        return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr="err" if rc else "")

    def bd_calls(self, sub):
        return [c for c in self.calls if c[0] == "bd" and c[1] == sub]


@pytest.fixture
def env(tmp_path, monkeypatch):
    (tmp_path / ".beads").mkdir()
    fake = FakeBd()
    monkeypatch.setattr(claims, "RUN", fake)
    monkeypatch.setattr(claims, "SLEEP", lambda s: None)
    monkeypatch.setattr(claims, "beads_root", lambda cwd: tmp_path)
    monkeypatch.setattr(claims, "start_loop", lambda root, sid, pid: fake.calls.append(["start_loop", sid]))
    monkeypatch.setattr(claims, "claude_pid", lambda: 1)
    return tmp_path, fake


def load(root):
    return json.loads((root / ".beads" / claims.STATE_NAME).read_text())


@pytest.mark.parametrize(
    "command",
    [
        "bd update aiwf-wp2 --claim",
        "cd x && bd update aiwf-wp3 --assignee=me",
        "bd create 'x' -a me",
        "/opt/homebrew/bin/bd unclaim aiwf-wp2",
        "bd reclaim --older-than 1m",
        "bd assign aiwf-wp2 me",
        "bd close aiwf-wp2 --force",
        "echo hi; bd --actor x update aiwf-wp2 --claim",
    ],
)
def test_guard_blocks_claim_assignment_force_reclaim(command):
    assert claims.guard(command)


@pytest.mark.parametrize(
    "command",
    ["bd update aiwf-wp2 -s in_review", "bd list -a me", "bd show aiwf-wp2 --json", "git commit -m 'bd update --claim'", "grep -- --claim notes.txt", "bd heartbeat aiwf-wp2"],
)
def test_guard_allows_other_commands(command):
    assert claims.guard(command) is None


def run_hook(event, payload, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    rc = claims.main(["hook", event])
    return rc, capsys.readouterr().out


def test_pre_bash_denies_only_subagents(env, monkeypatch, capsys):
    cmd = {"tool_input": {"command": "bd update aiwf-wp2 --claim"}}
    rc, out = run_hook("pre-bash", {**cmd, "agent_id": "a1", "agent_type": "general-purpose"}, monkeypatch, capsys)
    decision = json.loads(out)["hookSpecificOutput"]
    assert rc == 0 and decision["permissionDecision"] == "deny" and "orchestrator" in decision["permissionDecisionReason"]
    assert run_hook("pre-bash", cmd, monkeypatch, capsys) == (0, "")


def spawn(bead="aiwf-wp2", background=True, agent_id=None):
    tool_input = {"description": f"{bead}: build it", "prompt": "...", "subagent_type": "general-purpose"}
    if background is not None:
        tool_input["run_in_background"] = background
    return {"session_id": "s", "tool_name": "Agent", "tool_input": tool_input, **({"agent_id": agent_id} if agent_id else {})}


def launched(payload, agent="a1"):
    return {**payload, "tool_response": {"isAsync": True, "status": "async_launched", "agentId": agent}}


def test_bead_of_needs_strict_description_prefix():
    assert claims.bead_of({"description": "aiwf-wp2: build"}) == "aiwf-wp2"
    assert claims.bead_of({"description": "aiwf-2en.1: x"}) == "aiwf-2en.1"
    for d in ("fix aiwf-wp2: x", "aiwf-wp2 build", "explore: aiwf-wp2", "wp2: x"):
        assert claims.bead_of({"description": d}) is None


def test_spawn_claims_then_binds_agent_id_from_tool_response(env, monkeypatch, capsys):
    root, fake = env
    assert run_hook("pre-agent", spawn(), monkeypatch, capsys) == (0, "")
    assert fake.issues["aiwf-wp2"] == {"status": "in_progress", "assignee": "track-aiwf-wp2"}
    run_hook("post-agent", launched(spawn()), monkeypatch, capsys)
    assert load(root)["agents"] == {"a1": {"bead": "aiwf-wp2", "actor": "track-aiwf-wp2", "session_id": "s", "active": True}}
    assert run_hook("pre-agent", spawn(), monkeypatch, capsys) == (0, "")  # same actor already holds it: re-spawn allowed


@pytest.mark.parametrize(
    "payload,holder,why",
    [(spawn(background=None), None, "run_in_background"), (spawn(background=False), None, "run_in_background"), (spawn(agent_id="t1"), None, "only the orchestrator"), (spawn(), "someone", "cannot claim")],
)
def test_track_spawn_denied_unless_background_by_orchestrator_and_claimable(env, monkeypatch, capsys, payload, holder, why):
    _, fake = env
    if holder:
        fake.issues["aiwf-wp2"] = {"status": "in_progress", "assignee": holder}
    rc, out = run_hook("pre-agent", payload, monkeypatch, capsys)
    assert rc == 0 and why in json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
    assert fake.issues.get("aiwf-wp2", {}).get("assignee") == holder


def test_agents_without_bead_and_foreground_results_are_ignored(env, monkeypatch, capsys):
    root, fake = env
    plain = {"session_id": "s", "tool_input": {"description": "explore code", "run_in_background": False}}
    assert run_hook("pre-agent", plain, monkeypatch, capsys) == (0, "")
    run_hook("post-agent", launched(plain), monkeypatch, capsys)
    run_hook("post-agent", {**spawn(), "tool_response": {"status": "completed", "agentId": "a1"}}, monkeypatch, capsys)
    assert fake.calls == [] and not (root / ".beads" / claims.STATE_NAME).exists()


def bound(root, fake, agent="a1", bead="aiwf-wp2", session="s"):
    assert claims.claim(root, bead) is None
    claims.bind(root, agent, bead, session)


def test_unbound_agent_end_is_a_noop(env, monkeypatch, capsys):
    _, fake = env
    run_hook("subagent-stop", {"session_id": "s", "agent_id": "zz"}, monkeypatch, capsys)
    assert fake.bd_calls("show") == fake.bd_calls("unclaim") == []


@pytest.mark.parametrize("status,rebound", [("in_progress", True), ("in_review", True), ("open", False)])
def test_send_message_rebinds_resumed_agent(env, monkeypatch, capsys, status, rebound):
    root, fake = env
    bound(root, fake)
    fake.issues["aiwf-wp2"]["status"] = "in_review"
    run_hook("subagent-stop", {"session_id": "s", "agent_id": "a1"}, monkeypatch, capsys)
    assert load(root)["agents"]["a1"]["active"] is False
    fake.issues["aiwf-wp2"]["status"] = status
    run_hook("post-send", {"session_id": "s", "tool_input": {"to": "a1", "message": "fix the review"}}, monkeypatch, capsys)
    assert load(root)["agents"]["a1"]["active"] is rebound


@pytest.mark.parametrize(
    "event,payload",
    [
        ("subagent-stop", {"agent_id": "a1"}),
        ("stop-failure", {"agent_id": "a1", "error": "boom"}),
        ("task-stop", {"tool_input": {"task_id": "a1"}}),
    ],
)
def test_agent_end_releases_its_bead_and_merge_slot(env, monkeypatch, capsys, event, payload):
    root, fake = env
    bound(root, fake)
    fake.slot_holder = "track-aiwf-wp2"
    run_hook(event, {"session_id": "s", **payload}, monkeypatch, capsys)
    assert fake.issues["aiwf-wp2"] == {"status": "open", "assignee": None}
    assert fake.slot_holder is None
    assert ["bd", "unclaim", "aiwf-wp2", "--if-assignee", "track-aiwf-wp2", "--reason", "agent ended (ADR-0015 hook)"] in fake.calls
    assert load(root)["agents"]["a1"]["active"] is False


def test_in_review_bead_is_not_released(env, monkeypatch, capsys):
    root, fake = env
    bound(root, fake)
    fake.issues["aiwf-wp2"]["status"] = "in_review"
    run_hook("subagent-stop", {"session_id": "s", "agent_id": "a1"}, monkeypatch, capsys)
    assert fake.issues["aiwf-wp2"]["status"] == "in_review" and fake.bd_calls("unclaim") == []


def test_failed_release_retries_then_keeps_the_binding(env, monkeypatch, capsys):
    root, fake = env
    bound(root, fake)
    fake.fail.add("unclaim")
    run_hook("subagent-stop", {"session_id": "s", "agent_id": "a1"}, monkeypatch, capsys)
    assert len(fake.bd_calls("unclaim")) == claims.RETRIES
    assert "a1" in load(root)["agents"]


def test_session_end_releases_all_its_beads(env, monkeypatch, capsys):
    root, fake = env
    bound(root, fake, "a1", "aiwf-wp2", "s")
    bound(root, fake, "b1", "aiwf-wp3", "other")
    run_hook("session-end", {"session_id": "s", "reason": "other"}, monkeypatch, capsys)
    assert fake.issues["aiwf-wp2"]["status"] == "open" and fake.issues["aiwf-wp3"]["status"] == "in_progress"
    assert list(load(root)["agents"]) == ["b1"]


def test_loop_releases_session_when_claude_dies(env, monkeypatch):
    root, fake = env
    bound(root, fake)
    monkeypatch.setattr(claims, "_alive", lambda pid: False)
    claims.loop(root, "s", 12345)
    assert fake.issues["aiwf-wp2"]["status"] == "open" and load(root)["agents"] == {}


def test_heartbeat_covers_session_beads_at_most_once_a_minute(env):
    root, fake = env
    bound(root, fake, "a1", "aiwf-wp2", "s")
    bound(root, fake, "b1", "aiwf-wp3", "other")
    claims.heartbeat(root, "s", now=1000)
    claims.heartbeat(root, "s", now=1030)
    claims.heartbeat(root, "s", now=1061)
    assert fake.bd_calls("heartbeat") == [["bd", "heartbeat", "aiwf-wp2", "--actor", "track-aiwf-wp2"]] * 2


def test_reaper_is_rate_limited_and_skips_after_sleep(env):
    root, fake = env
    assert claims.reap(root, 10_000) == "ran"
    assert claims.reap(root, 10_060) == "rate-limited"
    assert claims.reap(root, 10_200) == "ran"
    assert claims.reap(root, 20_000).startswith("skipped")
    assert claims.reap(root, 20_130) == "ran"
    assert fake.bd_calls("reclaim") == [["bd", "reclaim", "--older-than", "10m"]] * 3


def test_session_start_starts_loop(env, monkeypatch, capsys):
    _, fake = env
    assert run_hook("session-start", {"session_id": "s", "source": "startup"}, monkeypatch, capsys) == (0, "")
    assert run_hook("session-start", {"session_id": "s", "agent_id": "a1"}, monkeypatch, capsys) == (0, "")
    assert fake.calls.count(["start_loop", "s"]) == 2


def test_hooks_are_noops_without_a_board(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(claims, "beads_root", lambda cwd: None)
    monkeypatch.setattr(claims, "RUN", lambda *a, **k: calls.append(a))
    for event in ("session-start", "post-send", "subagent-stop", "task-stop", "stop-failure", "session-end"):
        assert run_hook(event, {"session_id": "s", "agent_id": "a1"}, monkeypatch, capsys) == (0, "")
    assert calls == []


def test_beads_root_needs_bd_and_beads_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(claims.shutil, "which", lambda name: None)
    assert claims.beads_root(tmp_path) is None
    monkeypatch.setattr(claims.shutil, "which", lambda name: "/bin/bd")
    monkeypatch.setattr(claims, "RUN", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout=f"{tmp_path}/.git\n"))
    assert claims.beads_root(tmp_path) is None
    (tmp_path / ".beads").mkdir()
    assert claims.beads_root(tmp_path) == tmp_path


def test_internal_error_exits_zero(env, monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("bd exploded")

    monkeypatch.setattr(claims, "release_agent", boom)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "s", "agent_id": "a1"})))
    assert claims.main(["hook", "subagent-stop"]) == 0
    assert "bd exploded" in capsys.readouterr().err


def test_claude_pid_skips_shell_ancestors(monkeypatch):
    table = {100: "1 /bin/sh", 1: "0 claude"}
    monkeypatch.setattr(claims.os, "getppid", lambda: 100)
    monkeypatch.setattr(claims, "RUN", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout=table[int(cmd[-1])]))
    assert claims.claude_pid() == 1


def test_settings_wire_every_event_with_room_to_finish():
    hooks = json.loads((ROOT / ".claude" / "settings.json").read_text())["hooks"]
    wired = {}
    for event, groups in hooks.items():
        for g in groups:
            for h in g["hooks"]:
                if "claims-hook" in h["command"]:
                    wired[event, g.get("matcher")] = (h["command"].rsplit(" ", 1)[1], h["timeout"])
    assert {k: v[0] for k, v in wired.items()} == {
        ("SessionStart", None): "session-start",
        ("SubagentStop", None): "subagent-stop",
        ("StopFailure", None): "stop-failure",
        ("SessionEnd", None): "session-end",
        ("PreToolUse", "Bash"): "pre-bash",
        ("PreToolUse", "Agent"): "pre-agent",
        ("PostToolUse", "TaskStop"): "task-stop",
        ("PostToolUse", "Agent"): "post-agent",
        ("PostToolUse", "SendMessage"): "post-send",
    }
    assert wired["SessionEnd", None][1] >= 10 and wired["PreToolUse", "Bash"][1] <= 10
