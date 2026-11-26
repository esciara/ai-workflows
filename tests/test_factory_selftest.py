import json

from aiwf.factory import selftest as st

HELLO = json.dumps({"sandbox": "aiwf-x-1", "output": {"result": "Hello, world!"}})
HELLO2 = json.dumps({"sandbox": "aiwf-x-2", "output": {"result": "Hello, world!"}})
TWO = f"{HELLO}\n{HELLO2}\n"


def make_run(script):
    """script: list of (prefix, (rc, out, err)); first matching prefix wins, in order of calls recorded."""
    calls = []

    def run(args, timeout):
        calls.append(args)
        for prefix, res in script:
            if args[: len(prefix)] == prefix:
                return res(args) if callable(res) else res
        raise AssertionError(f"unexpected {args}")

    run.calls = calls
    return run


M0 = st.M0_CMD


def test_aiwf_sandboxes_parses_quiet_and_table():
    assert st.aiwf_sandboxes("aiwf-1-1\nother\n  aiwf-2-2   running\n") == ["aiwf-1-1", "aiwf-2-2"]
    assert st.aiwf_sandboxes("") == []


def test_count_results():
    assert st.count_hello_results(TWO + "noise\n") == 2
    assert st.count_hello_results(HELLO + "\n" + json.dumps({"sandbox": "a", "output": "nope"})) == 1
    assert st.count_results("x\n" + TWO) == 2


def test_keychain_verdicts():
    assert st.keychain_verdict(0, "", "factory")[0]
    ok, msg = st.keychain_verdict(36, "User interaction is not allowed.", "factory")
    assert not ok and "security unlock-keychain ~/Library/Keychains/login.keychain-db" in msg
    ok, msg = st.keychain_verdict(44, "The specified item could not be found", "factory")
    assert not ok and "add-generic-password -a factory -s aiwf-claude-oauth -w" in msg
    assert not st.keychain_verdict(1, "weird", "factory")[0]


def test_keychain_probe_has_no_w_flag():
    run = make_run([(["security"], (0, "SECRET-OUTPUT", ""))])
    assert st.SelfTest(run=run).check_keychain()[0]
    assert "-w" not in run.calls[0]


def test_normal_run_pass_and_leftover_fail():
    run = make_run([(M0, (0, TWO, "")), (["sbx", "ls"], (0, "", ""))])
    assert st.SelfTest(run=run).check_normal_run()[0]
    run = make_run([(M0, (0, TWO, "")), (["sbx", "ls"], (0, "aiwf-x-1\n", ""))])
    ok, msg = st.SelfTest(run=run).check_normal_run()
    assert not ok and "aiwf-x-1" in msg
    run = make_run([(M0, (0, HELLO + "\n", "")), (["sbx", "ls"], (0, "", ""))])
    assert not st.SelfTest(run=run).check_normal_run()[0]


def test_token_in_db(tmp_path):
    t = st.SelfTest(run=make_run([(["grep"], (1, "0\n", ""))]), home=tmp_path)
    assert t.check_no_token_in_db()[0]
    t = st.SelfTest(run=make_run([(["grep"], (0, "3\n", ""))]), home=tmp_path)
    assert not t.check_no_token_in_db()[0]
    t = st.SelfTest(run=make_run([(["grep"], (2, "", "no such file"))]), home=tmp_path)
    assert not t.check_no_token_in_db()[0]


class Proc:
    def __init__(self, alive=True):
        self.alive, self.killed, self.returncode = alive, False, None if alive else 0

    def poll(self):
        return None if self.alive else 0

    def kill(self):
        self.killed = True

    def wait(self):
        pass


def test_kill_resume_pass():
    proc, slept = Proc(), []
    run = make_run([(M0, (0, TWO, "")), (["sbx", "ls"], (0, "", ""))])
    t = st.SelfTest(run=run, spawn=lambda: proc, sleep=slept.append)
    assert t.check_kill_resume()[0] and proc.killed and slept == [st.KILL_AFTER]


def test_kill_resume_fails():
    ls_ok = (["sbx", "ls"], (0, "", ""))
    assert not st.SelfTest(run=make_run([ls_ok]), spawn=lambda: Proc(alive=False), sleep=lambda s: None).check_kill_resume()[0]
    run = make_run([(M0, (0, HELLO + "\n", "")), ls_ok])
    assert not st.SelfTest(run=run, spawn=Proc, sleep=lambda s: None).check_kill_resume()[0]
    run = make_run([(M0, (0, TWO, "")), (["sbx", "ls"], (0, "aiwf-z-1\n", ""))])
    assert not st.SelfTest(run=run, spawn=Proc, sleep=lambda s: None).check_kill_resume()[0]


def test_main_stops_at_keychain(capsys):
    run = make_run([(["security"], (36, "", "User interaction is not allowed."))])
    assert st.main(st.SelfTest(run=run)) == 1
    out = capsys.readouterr().out
    assert out.startswith("FAIL keychain") and "unlock-keychain" in out and len(run.calls) == 1


def test_main_all_pass_and_any_fail(capsys, tmp_path):
    script = [(["security"], (0, "", "")), (M0, (0, TWO, "")), (["sbx", "ls"], (0, "", "")), (["grep"], (1, "0\n", ""))]
    t = st.SelfTest(run=make_run(script), spawn=Proc, sleep=lambda s: None, home=tmp_path)
    assert st.main(t) == 0
    out = capsys.readouterr().out
    assert sum(l.startswith("PASS ") for l in out.splitlines()) == 4 and "SUMMARY: PASS (4/4" in out
    script[3] = (["grep"], (0, "1\n", ""))
    t = st.SelfTest(run=make_run(script), spawn=Proc, sleep=lambda s: None, home=tmp_path)
    assert st.main(t) == 1
    assert "FAIL no-token-in-db" in capsys.readouterr().out
