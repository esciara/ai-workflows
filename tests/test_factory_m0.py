import pytest

from aiwf.factory import m0


class Fake:
    def __init__(self, ls="", fail_exec=()):
        self.calls, self.live, self.ls, self.fail_exec = [], set(), ls, fail_exec
        self.token_flags = []

    def __call__(self, args, check=True, with_token=False):
        self.calls.append(args)
        self.token_flags.append(with_token)
        if args[:2] == ["sbx", "create"]:
            self.live.add(args[args.index("--name") + 1])
        elif args[:2] == ["sbx", "rm"]:
            self.live.discard(args[2])
        elif args[:2] == ["sbx", "exec"]:
            if args[2] in self.fail_exec:
                raise RuntimeError("boom")
            return '{"result": "hello world"}'
        elif args[:2] == ["sbx", "ls"]:
            return self.ls
        return ""


def test_names_unique_and_prefixed():
    a, b = m0.sandbox_name("abcdef123456", 1), m0.sandbox_name("abcdef123456", 2)
    assert a != b and a.startswith("aiwf-abcdef12-")


def test_created_and_removed_even_when_one_raises(monkeypatch):
    fake = Fake(fail_exec={"aiwf-wf000000-2"})
    monkeypatch.setattr(m0, "run_sbx", fake)
    assert m0.hello_body("wf000000", 1)["output"] == {"result": "hello world"}
    with pytest.raises(RuntimeError):
        m0.hello_body("wf000000", 2)
    creates = [c[c.index("--name") + 1] for c in fake.calls if c[:2] == ["sbx", "create"]]
    assert sorted(creates) == ["aiwf-wf000000-1", "aiwf-wf000000-2"]
    assert fake.live == set()


def test_reaper_removes_only_aiwf(monkeypatch):
    fake = Fake(ls="aiwf-1-1\nother\naiwf-2-2\n")
    monkeypatch.setattr(m0, "run_sbx", fake)
    assert m0.reap() == ["aiwf-1-1", "aiwf-2-2"]
    removed = [c[2] for c in fake.calls if c[:2] == ["sbx", "rm"]]
    assert removed == ["aiwf-1-1", "aiwf-2-2"]


def test_stale_sandbox_removed_before_create(monkeypatch):
    fake = Fake()
    monkeypatch.setattr(m0, "run_sbx", fake)
    m0.hello_body("wf000000", 1)
    kinds = [c[1] for c in fake.calls]
    assert kinds[:2] == ["rm", "create"]


TOKEN = "sk-ant-oat-SECRET-123"


@pytest.fixture(autouse=True)
def token(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    m0.load_token()
    yield
    monkeypatch.setattr(m0, "_token", None)


def test_create_has_resource_limits_and_token_never_in_argv(monkeypatch):
    fake = Fake()
    monkeypatch.setattr(m0, "run_sbx", fake)
    m0.hello_body("wf000000", 1)
    create = next(c for c in fake.calls if c[:2] == ["sbx", "create"])
    assert create[create.index("--cpus") + 1] == "2" and create[create.index("-m") + 1] == "4g"
    assert all(TOKEN not in a for c in fake.calls for a in c)
    assert [c[1] for c, t in zip(fake.calls, fake.token_flags) if t] == ["exec"]


def test_missing_token_fails_clearly(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN")
    monkeypatch.setattr(m0.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 44, "stdout": ""})())
    with pytest.raises(SystemExit) as e:
        m0.load_token()
    assert TOKEN not in str(e.value) and "security add-generic-password" in str(e.value)


def test_run_sbx_env_and_stdin(monkeypatch):
    seen = {}

    def fake_run(args, **kw):
        seen.update(kw, args=args)
        return type("R", (), {"returncode": 0, "stdout": "ok"})()

    monkeypatch.setattr(m0.subprocess, "run", fake_run)
    m0.run_sbx(["sbx", "exec", "x"], with_token=True)
    assert seen["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == TOKEN and seen["stdin"] == m0.subprocess.DEVNULL
    m0.run_sbx(["sbx", "ls"])
    assert seen["env"] is None


def test_main_runs_two_hellos_and_registers_stable_names(monkeypatch, tmp_path, capsys):
    dbos = pytest.importorskip("dbos")
    monkeypatch.setenv("AIWF_FACTORY_DB", str(tmp_path / "d.sqlite"))
    monkeypatch.setenv("AIWF_FACTORY_VERSION", "test")
    fake = Fake()
    monkeypatch.setattr(m0, "run_sbx", fake)
    try:
        assert m0.main() == 0
        names = {w.name for w in dbos.DBOS.list_workflows()}
        assert "hello_two" in names  # main() looks up a PENDING run by this exact name
    finally:
        dbos.DBOS.destroy()
    assert capsys.readouterr().out.count("hello world") == 2
    assert fake.live == set()
    assert TOKEN.encode() not in (tmp_path / "d.sqlite").read_bytes()


class FakeDBOS:
    def __init__(self, runs):
        self.runs, self.kwargs = runs, None

    def list_workflows(self, **kw):
        self.kwargs = kw
        v = kw["app_version"]
        return [r for r in self.runs if r.app_version == v and r.status in kw["status"]]


class Run:
    def __init__(self, wid, status, app_version):
        self.workflow_id, self.status, self.app_version = wid, status, app_version


def test_resumed_run_found_when_pending_or_reenqueued():
    for status in ("PENDING", "ENQUEUED"):
        d = FakeDBOS([Run("w1", status, "v2")])
        assert m0.resumed_run(d, "v2") == "w1"
        assert d.kwargs["name"] == "hello_two"


def test_resumed_run_ignores_other_version_and_finished():
    d = FakeDBOS([Run("old", "PENDING", "v1"), Run("done", "SUCCESS", "v2")])
    assert m0.resumed_run(d, "v2") is None
