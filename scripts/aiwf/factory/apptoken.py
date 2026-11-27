"""Factory App installation tokens (ADR-0064 decision 2): minted per step, narrowed, one repo, memory only.

The App key comes from the SOPS reader (`secrets.read_secret`) and is passed to `openssl` on stdin, never argv or disk.
A token is returned as a `Token` whose repr and str are redacted; callers read `.reveal()` at the last moment, put it in
an HTTP header or `GH_TOKEN` of one child process, and never in a DBOS step argument or return value, log line or file.
Steps mint their own token inside the step body. Needs the App id (`AIWF_FACTORY_APP_ID`, not a secret).
"""

import base64
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

from aiwf.factory import secrets

API = "https://api.github.com"
APP_ID_ENV = "AIWF_FACTORY_APP_ID"
JWT_TTL = 540  # GitHub allows at most 600 s; 60 s of back-dated iat covers clock drift

# The narrowed permissions per step, as the matching review.yml jobs (ADR-0064 decision 2). Nothing else is requested.
CONTEXT = {"contents": "read", "pull_requests": "read", "issues": "read", "checks": "read", "actions": "read"}
PUBLISH = {"pull_requests": "write", "issues": "write", "contents": "read"}
READ = {"pull_requests": "read", "metadata": "read"}  # doctor

_LEVEL = {"read": 1, "write": 2, "admin": 3}
_pem: str | None = None  # decrypted once per process (ADR-0064 d5), memory only


def _load_pem() -> str:
    global _pem
    if _pem is None:
        try:
            _pem = secrets.read_secret(secrets.FACTORY_APP_PEM)
        except secrets.SecretsError as e:
            raise TokenError(str(e)) from None
    return _pem


Http = Callable[[str, str, dict[str, str], bytes | None], tuple[int, bytes]]


class TokenError(Exception):
    """A mint failure; the message is safe to print (no key, JWT or token)."""


@dataclass(frozen=True)
class Token:
    _value: str = field(repr=False)

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Token(<redacted>)"

    __str__ = __repr__


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def make_jwt(app_id: str, pem: str, now: float | None = None) -> str:
    """RS256 JWT for the App. The PEM goes to openssl on stdin (`-sign /dev/stdin`); only the public signing input touches a temp file."""
    now = int(time.time() if now is None else now)
    head = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps({"iat": now - 60, "exp": now + JWT_TTL, "iss": str(app_id)}, separators=(",", ":")).encode())
    signing_input = f"{head}.{body}".encode()
    with tempfile.NamedTemporaryFile() as f:  # 0600, deleted on close; holds the public signing input only
        f.write(signing_input)
        f.flush()
        try:
            r = subprocess.run(["openssl", "dgst", "-sha256", "-sign", "/dev/stdin", f.name], input=pem.encode(),
                               capture_output=True, check=False, timeout=30)
        except (OSError, subprocess.SubprocessError) as e:
            raise TokenError(f"cannot run openssl ({type(e).__name__})") from None
    if r.returncode != 0 or not r.stdout:
        raise TokenError(f"openssl could not sign the JWT (rc={r.returncode}): is factory_app_pem a valid RSA key?")
    return f"{head}.{body}.{_b64(r.stdout)}"


def _urllib_http(method: str, url: str, headers: dict[str, str], data: bytes | None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, OSError) as e:
        raise TokenError(f"GitHub unreachable ({type(e).__name__})") from None


def _call(http: Http, method: str, path: str, jwt: str, payload: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {jwt}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "aiwf-factory"}
    data = json.dumps(payload).encode() if payload is not None else None
    status, raw = http(method, API + path, headers, data)
    if status >= 300:
        raise TokenError(f"{method} {path} failed with HTTP {status}")  # body not echoed
    try:
        return json.loads(raw)
    except ValueError:
        raise TokenError(f"{method} {path} returned invalid JSON") from None


def mint(repo: str, permissions: dict[str, str], *, app_id: str | None = None, pem: str | None = None,
         http: Http = _urllib_http, now: float | None = None) -> Token:
    """Mint an installation token limited to `repo` ("owner/name") and `permissions`. Call once per step."""
    app_id = app_id or os.environ.get(APP_ID_ENV, "")
    if not app_id:
        raise TokenError(f"{APP_ID_ENV} is not set (the maintainer creates the App, docs/factory-m1.md)")
    if "/" not in repo or not permissions:
        raise TokenError("need repo as owner/name and a non-empty permissions dict")
    pem = pem or _load_pem()
    jwt = make_jwt(app_id, pem, now)
    inst = _call(http, "GET", f"/repos/{repo}/installation", jwt)
    if not isinstance(inst.get("id"), int):
        raise TokenError(f"the App is not installed on {repo}")
    body = {"repositories": [repo.split("/", 1)[1]], "permissions": dict(permissions)}
    resp = _call(http, "POST", f"/app/installations/{inst['id']}/access_tokens", jwt, body)
    tok = resp.get("token")
    if not isinstance(tok, str) or not tok:
        raise TokenError("GitHub returned no token")
    granted = resp.get("permissions")
    if not isinstance(granted, dict):
        raise TokenError("GitHub did not report the token's permissions: refusing the token")
    for name, level in granted.items():  # metadata: read is always added by GitHub
        if name == "metadata" and level == "read":
            continue
        if _LEVEL.get(level, 99) > _LEVEL.get(permissions.get(name), 0):
            raise TokenError("GitHub granted more permissions than requested: refusing the token")
    return Token(tok)
