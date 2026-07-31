"""Run the installed console script as a real subprocess — no CliRunner.

CliRunner tests import the CLI in-process with mocks around it; they can't
notice a broken entry point, an import-time crash in the locked environment,
or drift in the machine-readable error contract that scripted callers (and
the --json wrappers) depend on. These do.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(sys.executable).parent / "reverse-api-engineer"


def _run_cli(args: list[str], tmp_home: Path) -> subprocess.CompletedProcess:
    # Isolated HOME: the CLI reads/writes ~/.reverse-api (config + history)
    # at import time, and these tests must not touch the developer's real one.
    env = os.environ.copy()
    env["HOME"] = str(tmp_home)
    return subprocess.run(
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )


@pytest.fixture
def tmp_home(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    return home


def test_console_script_is_installed():
    assert SCRIPT.exists(), f"console script not found at {SCRIPT} — the package is not installed in this environment (run `uv sync`)"


def test_help_runs_clean(tmp_home):
    result = _run_cli(["--help"], tmp_home)
    assert result.returncode == 0, result.stderr
    assert "reverse-api-engineer" in result.stdout


def test_engineer_json_missing_run_id_is_machine_readable(tmp_home):
    result = _run_cli(["engineer", "--json"], tmp_home)
    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error_kind"] == "misuse"
    assert "RUN_ID" in payload["error"]


def test_engineer_json_unknown_run_fails_with_error_payload(tmp_home, tmp_path):
    result = _run_cli(["engineer", "nosuchrun", "--json", "-o", str(tmp_path / "out")], tmp_home)
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["run_id"] == "nosuchrun"
