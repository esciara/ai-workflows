"""as-agent's git env (ADR-0031): App credential helper + SSH remotes rewritten to HTTPS. No network: curl, openssl,
jq and security are stubbed on PATH; a fake `git` dumps the effective config as git would see it."""
import os
import stat
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dev" / "as-agent"

STUBS = {
    "curl": "#!/bin/sh\necho '{}'\n",
    "jq": "#!/bin/sh\necho fake\n",
    "openssl": "#!/bin/sh\ncat >/dev/null; printf x\n",
    "security": "#!/bin/sh\nexit 1\n",
    # Prints the GIT_CONFIG_* pairs the way git reads them (key=value per index).
    "git": '#!/bin/sh\ni=0\nwhile [ "$i" -lt "$GIT_CONFIG_COUNT" ]; do\n'
           '  eval "printf \'%s=%s\\n\' \\"\\$GIT_CONFIG_KEY_$i\\" \\"\\$GIT_CONFIG_VALUE_$i\\""\n  i=$((i+1))\ndone\n',
}


def run_git(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in STUBS.items():
        f = bin_dir / name
        f.write_text(body)
        f.chmod(f.stat().st_mode | stat.S_IEXEC)
    key = tmp_path / "key.pem"
    key.write_text("dummy")
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "AI_WORKFLOWS_AGENT_APP_ID": "1",
           "AI_WORKFLOWS_AGENT_KEY_PATH": str(key), "HOME": str(tmp_path)}
    out = subprocess.run(["bash", str(SCRIPT), "git", "push"], env=env, capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


def test_git_env_uses_app_credential_and_https(tmp_path):
    lines = run_git(tmp_path)
    assert lines == [
        "credential.https://github.com.helper=",
        "credential.https://github.com.helper=!gh auth git-credential",
        "url.https://github.com/.insteadOf=git@github.com:",
        "url.https://github.com/.insteadOf=ssh://git@github.com/",
    ]


def test_ssh_remote_resolves_to_https(tmp_path):
    """Real git applies the exported rewrite to an SSH origin."""
    lines = run_git(tmp_path)
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_CONFIG")}
    env.update(GIT_CONFIG_COUNT=str(len(lines)), GIT_CONFIG_NOSYSTEM="1", HOME=str(tmp_path))
    for i, line in enumerate(lines):
        k, v = line.split("=", 1)
        env[f"GIT_CONFIG_KEY_{i}"], env[f"GIT_CONFIG_VALUE_{i}"] = k, v
    repo = tmp_path / "r"
    subprocess.run(["git", "init", "-q", str(repo)], check=True, env=env)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", "git@github.com:o/r.git"], check=True, env=env)
    for push in ("", "--push"):
        args = ["git", "-C", str(repo), "remote", "get-url", *([push] if push else []), "origin"]
        url = subprocess.run(args, env=env, capture_output=True, text=True, check=True).stdout.strip()
        assert url == "https://github.com/o/r.git"
