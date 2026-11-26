"""Secrets at rest (ADR-0064 decision 5): one SOPS-encrypted YAML file, one age key file, both under ~/.config/aiwf.

The runner refuses to start unless the key file (and its directory) belong to the running user with mode 0600 (0700).
Each value is decrypted once with `sops decrypt --extract` and read from stdout into memory: never argv, logs or DBOS.
Messages never include sops stderr or any value.
"""

import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

CLAUDE_OAUTH = "claude_oauth"
FACTORY_APP_PEM = "factory_app_pem"


class SecretsError(Exception):
    """A refusal to read secrets; the message is safe to print."""


@dataclass(frozen=True)
class Paths:
    key: Path
    enc: Path

    @property
    def directory(self) -> Path:
        return self.key.parent


def default_paths() -> Paths:
    base = Path(os.environ.get("AIWF_CONFIG_DIR") or Path.home() / ".config" / "aiwf")
    return Paths(key=base / "age.key", enc=base / "secrets.enc.yaml")


def _problems_for(path: Path, want_mode: int, kind: str, uid: int) -> list[str]:
    try:
        st = path.lstat()  # lstat: a symlink is refused, not followed
    except FileNotFoundError:
        return [f"{kind} {path} is missing"]
    out = []
    if kind == "key file" and not stat.S_ISREG(st.st_mode):
        out.append(f"{kind} {path} is not a regular file")
    if kind == "directory" and not stat.S_ISDIR(st.st_mode):
        out.append(f"{kind} {path} is not a directory")
    if st.st_uid != uid:
        out.append(f"{kind} {path} is owned by uid {st.st_uid}, expected {uid}")
    mode = stat.S_IMODE(st.st_mode)
    if mode != want_mode:
        out.append(f"{kind} {path} has mode {mode:04o}, expected {want_mode:04o}: run chmod {want_mode:o} {path}")
    return out


def check_key_file(paths: Paths, uid: int | None = None) -> list[str]:
    """Return the problems with the age key file and its directory (empty list: fine)."""
    uid = os.getuid() if uid is None else uid
    return _problems_for(paths.directory, 0o700, "directory", uid) + _problems_for(paths.key, 0o600, "key file", uid)


def require_safe(paths: Paths, uid: int | None = None) -> None:
    problems = check_key_file(paths, uid)
    if problems:
        raise SecretsError("refusing to start: " + "; ".join(problems))
    if not paths.enc.is_file():
        raise SecretsError(f"secrets file {paths.enc} is missing")


def read_secret(name: str, paths: Paths | None = None, uid: int | None = None) -> str:
    """Decrypt one value. Raises SecretsError (safe message) on a bad key file, sops failure or empty value."""
    paths = paths or default_paths()
    require_safe(paths, uid)
    env = {**os.environ, "SOPS_AGE_KEY_FILE": str(paths.key)}
    try:
        r = subprocess.run(
            ["sops", "decrypt", "--extract", f'["{name}"]', str(paths.enc)],
            capture_output=True, text=True, check=False, env=env, stdin=subprocess.DEVNULL, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise SecretsError(f"cannot run sops ({type(e).__name__}): is it installed and on PATH?") from None
    if r.returncode != 0:
        raise SecretsError(f"sops could not decrypt {name!r} (rc={r.returncode}): wrong key, or no such entry")
    value = r.stdout.strip()
    if not value:
        raise SecretsError(f"secret {name!r} is empty")
    return value
