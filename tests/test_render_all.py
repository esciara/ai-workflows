"""scripts/dev/render-all (ADR-0046): runs the three renderers in order and stops at the first error. Renderers stubbed."""
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dev" / "render-all"
STEPS = ["render-progress", "render-adr-index", "render-diagrams"]


def setup(tmp_path, fail=None):
    log = tmp_path / "log"
    for step in STEPS:
        stub = tmp_path / step
        code = 3 if step == fail else 0
        stub.write_text(f'#!/bin/sh\necho "{step} $*" >> "{log}"\nexit {code}\n')
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    shutil.copy(SCRIPT, tmp_path / "render-all")
    return tmp_path / "render-all", log


def test_runs_all_in_order(tmp_path):
    script, log = setup(tmp_path)
    assert subprocess.run([script], capture_output=True).returncode == 0
    assert log.read_text().split("\n")[:3] == ["render-progress ", "render-adr-index ", "render-diagrams "]


def test_no_export_goes_to_render_progress_only(tmp_path):
    script, log = setup(tmp_path)
    assert subprocess.run([script, "--no-export"], capture_output=True).returncode == 0
    assert log.read_text().splitlines() == ["render-progress --no-export", "render-adr-index ", "render-diagrams "]


@pytest.mark.parametrize("fail", STEPS)
def test_stops_at_first_error(tmp_path, fail):
    script, log = setup(tmp_path, fail)
    proc = subprocess.run([script], capture_output=True, text=True)
    assert proc.returncode == 3
    assert f"{fail} failed" in proc.stderr
    ran = [line.split()[0] for line in log.read_text().splitlines()]
    assert ran == STEPS[: STEPS.index(fail) + 1]


def test_unknown_argument_runs_nothing(tmp_path):
    script, log = setup(tmp_path)
    assert subprocess.run([script, "--check"], capture_output=True).returncode == 2
    assert not log.exists()
