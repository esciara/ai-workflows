import base64
import pickle
import json
import logging
import subprocess

import pytest

from aiwf.factory import apptoken

TOKEN = "ghs_SECRETINSTALLATIONTOKEN"


@pytest.fixture(scope="module")
def pem():
    return subprocess.run(["openssl", "genrsa", "2048"], capture_output=True, text=True, check=True).stdout


def unb64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class FakeHttp:
    def __init__(self, granted=None, installed=True, repos=None):
        self.calls = []
        self.granted = granted
        self.repos = repos
        self.installed = installed

    def __call__(self, method, url, headers, data):
        self.calls.append((method, url, headers, json.loads(data) if data else None))
        if url.endswith("/installation"):
            return (200, json.dumps({"id": 77} if self.installed else {}).encode())
        body = self.calls[-1][3]
        return (201, json.dumps({"token": TOKEN, "permissions": self.granted or body["permissions"],
                                            "repositories": self.repos or [{"name": n} for n in body["repositories"]]}).encode())


def test_jwt_is_rs256_with_app_id_and_valid_signature(pem, tmp_path):
    jwt = apptoken.make_jwt("123", pem, now=1000)
    h, b, s = jwt.split(".")
    assert json.loads(unb64(h)) == {"alg": "RS256", "typ": "JWT"}
    claims = json.loads(unb64(b))
    assert claims == {"iat": 940, "exp": 1540, "iss": "123"}
    (tmp_path / "k").write_text(pem)
    pub = subprocess.run(["openssl", "rsa", "-in", str(tmp_path / "k"), "-pubout"], capture_output=True, check=True).stdout
    (tmp_path / "pub").write_bytes(pub)
    (tmp_path / "sig").write_bytes(unb64(s))
    (tmp_path / "msg").write_bytes(f"{h}.{b}".encode())
    r = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(tmp_path / "pub"), "-signature", str(tmp_path / "sig"),
                        str(tmp_path / "msg")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_request_body_has_only_step_permissions_and_one_repo(pem):
    http = FakeHttp()
    tok = apptoken.mint("esciara/ai-workflows-playground", apptoken.PUBLISH, app_id="123", pem=pem, http=http)
    (m1, u1, h1, _), (m2, u2, h2, body) = http.calls
    assert (m1, u1) == ("GET", "https://api.github.com/repos/esciara/ai-workflows-playground/installation")
    assert (m2, u2) == ("POST", "https://api.github.com/app/installations/77/access_tokens")
    assert body == {"repositories": ["ai-workflows-playground"],
                    "permissions": {"pull_requests": "write", "issues": "write", "contents": "read"}}
    assert h2["Authorization"].startswith("Bearer ") and TOKEN not in h2["Authorization"]
    assert tok.reveal() == TOKEN


def test_presets_match_adr_0064():
    assert apptoken.CONTEXT == {"contents": "read", "pull_requests": "read", "issues": "read", "checks": "read", "actions": "read"}
    assert apptoken.PUBLISH == {"pull_requests": "write", "issues": "write", "contents": "read"}
    for preset in (apptoken.CONTEXT, apptoken.PUBLISH, apptoken.READ):
        assert not {"workflows", "administration", "statuses", "secrets"} & set(preset)


def test_token_never_in_repr_str_or_logs(pem, caplog):
    tok = apptoken.mint("o/r", apptoken.READ, app_id="1", pem=pem, http=FakeHttp())
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("t").info("minted %s %r", tok, tok)
    assert TOKEN not in repr(tok) + str(tok) + caplog.text


def test_refuses_token_with_extra_permissions(pem):
    with pytest.raises(apptoken.TokenError, match="more permissions"):
        apptoken.mint("o/r", apptoken.READ, app_id="1", pem=pem, http=FakeHttp(granted={"pull_requests": "read", "contents": "write"}))


def test_extra_level_or_missing_permissions_refused(pem):
    with pytest.raises(apptoken.TokenError, match="more permissions"):
        apptoken.mint("o/r", apptoken.READ, app_id="1", pem=pem, http=FakeHttp(granted={"pull_requests": "write"}))
    http = lambda m, u, h, d: (200, b'{"id": 1}') if u.endswith("/installation") else (201, b'{"token": "x"}')  # noqa: E731
    with pytest.raises(apptoken.TokenError, match="did not report"):
        apptoken.mint("o/r", apptoken.READ, app_id="1", pem=pem, http=http)


def test_metadata_read_added_by_github_is_accepted(pem):
    http = FakeHttp(granted={**apptoken.PUBLISH, "metadata": "read"})
    assert apptoken.mint("o/r", apptoken.PUBLISH, app_id="1", pem=pem, http=http).reveal() == TOKEN


def test_pem_decrypted_once_per_process(pem, monkeypatch):
    monkeypatch.setattr(apptoken, "_pem", None)
    n = []
    monkeypatch.setattr(apptoken.secrets, "read_secret", lambda name, *a, **k: n.append(name) or pem)
    for _ in range(3):
        apptoken.mint("o/r", apptoken.READ, app_id="1", http=FakeHttp())
    assert n == ["factory_app_pem"]


class FakeDbos:
    """Records every step's arguments and return value, as DBOS does in its SQLite."""

    def __init__(self):
        self.records = []

    def step(self, fn):
        def wrapper(*a, **k):
            out = fn(*a, **k)
            self.records.append(pickle.dumps({"args": a, "kwargs": k, "result": out}))  # as DBOS stores them
            return out
        return wrapper


def test_token_never_reaches_step_args_or_return_value(pem):
    dbos = FakeDbos()
    seen_by_github = []

    @dbos.step
    def publish_step(repo, pr):
        http = FakeHttp()
        tok = apptoken.mint(repo, apptoken.PUBLISH, app_id="1", pem=pem, http=http)
        seen_by_github.append(tok.reveal())  # the one legitimate use: an HTTP header or GH_TOKEN of a child
        return {"posted": pr}

    publish_step("o/r", 5)
    assert seen_by_github == [TOKEN]
    assert dbos.records and all(TOKEN.encode() not in r for r in dbos.records)


def test_token_cannot_be_pickled_as_step_arg_or_result(pem):
    tok = apptoken.mint("o/r", apptoken.READ, app_id="1", pem=pem, http=FakeHttp())
    dbos = FakeDbos()
    with pytest.raises(TypeError, match="cannot be serialized"):
        dbos.step(lambda t: "x")(tok)
    with pytest.raises(TypeError, match="cannot be serialized"):
        dbos.step(lambda: {"tok": tok})()


def test_other_repositories_refused(pem):
    with pytest.raises(apptoken.TokenError, match="other repositories"):
        apptoken.mint("o/r", apptoken.READ, app_id="1", pem=pem, http=FakeHttp(repos=[{"name": "r"}, {"name": "x"}]))


def test_doctor_check_handles_bad_body(monkeypatch):
    from aiwf.factory import doctor
    monkeypatch.setattr(apptoken, "mint", lambda *a, **k: apptoken.Token("t"))
    monkeypatch.setattr(apptoken, "_urllib_http", lambda *a: (200, b"<html>"))
    ok, msg = doctor.check_app_token()
    assert not ok and "unexpected body" in msg
    monkeypatch.setattr(apptoken, "_urllib_http", lambda *a: (200, b'[{"n": 1}, {"n": 2}]'))
    ok, msg = doctor.check_app_token()
    assert ok and "2 open PR" in msg


def test_not_installed_and_http_error_messages_are_safe(pem):
    with pytest.raises(apptoken.TokenError, match="not installed"):
        apptoken.mint("o/r", apptoken.READ, app_id="1", pem=pem, http=FakeHttp(installed=False))
    with pytest.raises(apptoken.TokenError, match="HTTP 401") as e:
        apptoken.mint("o/r", apptoken.READ, app_id="1", pem=pem, http=lambda *a: (401, b"secret body"))
    assert "secret body" not in str(e.value)


def test_missing_app_id_and_bad_args(pem, monkeypatch):
    monkeypatch.delenv("AIWF_FACTORY_APP_ID", raising=False)
    with pytest.raises(apptoken.TokenError, match="AIWF_FACTORY_APP_ID"):
        apptoken.mint("o/r", apptoken.READ, pem=pem, http=FakeHttp())
    with pytest.raises(apptoken.TokenError):
        apptoken.mint("noslash", apptoken.READ, app_id="1", pem=pem, http=FakeHttp())
    with pytest.raises(apptoken.TokenError):
        apptoken.mint("o/r", {}, app_id="1", pem=pem, http=FakeHttp())


def test_bad_pem_gives_safe_error():
    with pytest.raises(apptoken.TokenError, match="valid RSA key") as e:
        apptoken.make_jwt("1", "-----BEGIN PRIVATE KEY-----\nSECRETPEMBODY\n-----END PRIVATE KEY-----\n")
    assert "SECRETPEMBODY" not in str(e.value)


def test_pem_comes_from_secrets_reader(pem, monkeypatch):
    monkeypatch.setattr(apptoken, "_pem", None)
    asked = []
    monkeypatch.setattr(apptoken.secrets, "read_secret", lambda name, *a, **k: asked.append(name) or pem)
    apptoken.mint("o/r", apptoken.READ, app_id="1", http=FakeHttp())
    assert asked == ["factory_app_pem"]


def test_openssl_gets_key_on_stdin_not_argv(pem, monkeypatch):
    seen = {}
    real = subprocess.run

    def spy(args, **kw):
        seen["args"], seen["input"] = args, kw.get("input")
        return real(args, **kw)

    monkeypatch.setattr(apptoken.subprocess, "run", spy)
    apptoken.make_jwt("1", pem)
    assert pem not in " ".join(seen["args"]) and seen["input"] == pem.encode()


def test_bot_login_is_configurable(monkeypatch):
    import importlib

    from aiwf import ghapi
    monkeypatch.setenv("AIWF_BOT_LOGIN", "esciara-ai-workflows-factory[bot]")
    importlib.reload(ghapi)
    assert ghapi.BOT == "esciara-ai-workflows-factory[bot]"
    monkeypatch.delenv("AIWF_BOT_LOGIN")
    importlib.reload(ghapi)
    assert ghapi.BOT == "github-actions[bot]"
