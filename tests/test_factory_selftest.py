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
        self.alive, self.returncode = alive, (None if alive else 0)

    def poll(self):
        return None if self.alive else 0

    pid = 1

    def wait(self):
        pass


def test_kill_resume_pass():
    proc, slept, killed = Proc(), [], []
    counts = iter([1, 0])
    run = make_run([(M0, (0, TWO, "")), (["sbx", "ls"], (0, "", ""))])
    t = st.SelfTest(run=run, spawn=lambda: proc, sleep=slept.append, kill=killed.append, unfinished=lambda: next(counts))
    assert t.check_kill_resume()[0] and killed == [proc] and slept == [st.KILL_AFTER]


def test_kill_resume_needs_a_pending_workflow_and_completion():
    run = make_run([(M0, (0, TWO, "")), (["sbx", "ls"], (0, "", ""))])
    t = st.SelfTest(run=run, spawn=Proc, sleep=lambda s: None, kill=lambda p: None, unfinished=lambda: 0)
    assert "nothing to resume" in t.check_kill_resume()[1]
    counts = iter([1, 1])
    t = st.SelfTest(run=run, spawn=Proc, sleep=lambda s: None, kill=lambda p: None, unfinished=lambda: next(counts))
    assert "still unfinished" in t.check_kill_resume()[1]


def test_unfinished_hello_two(tmp_path):
    import sqlite3
    db = tmp_path / "d.sqlite"
    con = sqlite3.connect(db)
    con.execute("create table workflow_status (name text, status text)")
    con.executemany("insert into workflow_status values (?, ?)",
                    [("hello_two", "PENDING"), ("hello_two", "SUCCESS"), ("hello", "PENDING")])
    con.commit(); con.close()
    assert st.unfinished_hello_two(str(db)) == 1


def test_hello_variants_match():
    assert st.count_hello_results(json.dumps({"sandbox": "a", "output": {"result": "Hello world!"}})) == 1


def test_kill_resume_fails():
    ls_ok = (["sbx", "ls"], (0, "", ""))
    kw = dict(spawn=Proc, sleep=lambda s: None, kill=lambda p: None)
    assert not st.SelfTest(run=make_run([ls_ok]), **{**kw, "spawn": lambda: Proc(alive=False)}).check_kill_resume()[0]
    run = make_run([(M0, (0, HELLO + "\n", "")), ls_ok])
    assert not st.SelfTest(run=run, unfinished=iter([1, 0]).__next__, **kw).check_kill_resume()[0]
    run = make_run([(M0, (0, TWO, "")), (["sbx", "ls"], (0, "aiwf-z-1\n", ""))])
    assert not st.SelfTest(run=run, unfinished=iter([1, 0]).__next__, **kw).check_kill_resume()[0]


def test_main_stops_at_keychain(capsys):
    run = make_run([(["security"], (36, "", "User interaction is not allowed."))])
    assert st.main(st.SelfTest(run=run)) == 1
    out = capsys.readouterr().out
    assert out.startswith("FAIL keychain") and "unlock-keychain" in out and len(run.calls) == 1


def test_main_all_pass_and_any_fail(capsys, tmp_path):
    script = [(["security"], (0, "", "")), (M0, (0, TWO, "")), (["sbx", "ls"], (0, "", "")), (["grep"], (1, "0\n", ""))]
    kw = dict(spawn=Proc, sleep=lambda s: None, home=tmp_path, kill=lambda p: None)
    t = st.SelfTest(run=make_run(script), unfinished=iter([1, 0]).__next__, **kw)
    assert st.main(t) == 0
    out = capsys.readouterr().out
    assert sum(l.startswith("PASS ") for l in out.splitlines()) == 4 and "SUMMARY: PASS (4/4" in out
    script[3] = (["grep"], (0, "1\n", ""))
    t = st.SelfTest(run=make_run(script), unfinished=iter([1, 0]).__next__, **kw)
    assert st.main(t) == 1
    assert "FAIL no-token-in-db" in capsys.readouterr().out
