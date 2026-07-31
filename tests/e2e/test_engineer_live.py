"""True end-to-end: a real Claude agent engineers a client from a real HAR.

Costs real API tokens and takes minutes, so it never runs in the default
suite or the PR gate. Opt in explicitly:

    RAE_E2E=1 ANTHROPIC_API_KEY=... uv run pytest -m e2e

Prerequisites beyond the key: the Claude Code CLI on PATH
(`npm install -g @anthropic-ai/claude-code`). The nightly e2e workflow
(.github/workflows/e2e.yml) provides both.

The scenario: serve a deterministic JSON API on loopback, hand the CLI a
HAR of one captured request against it, and let the real agent generate a
Python client and verify it live. Assertions stick to the machine-readable
contract (--json-stream events, exit code, produced file) — never the
agent's prose — to stay stable across model behavior.
"""

import json
import os
import py_compile
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.localserver import FIXTURE_PRODUCTS

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(os.environ.get("RAE_E2E") != "1", reason="real-agent e2e is opt-in: set RAE_E2E=1"),
]

RUN_ID = "e2eengineer"
SCRIPT = Path(sys.executable).parent / "reverse-api-engineer"


def _claude_credentials() -> Path | None:
    creds = Path.home() / ".claude" / ".credentials.json"
    return creds if creds.exists() else None


def _require_prereqs():
    # RAE_E2E=1 is an explicit opt-in, so a missing prerequisite is a hard
    # failure with instructions — a skip here would quietly turn the nightly
    # workflow into a no-op.
    # RAE_E2E_ASSUME_AUTH=1 covers environments where the CLI authenticates
    # ambiently (e.g. through a managed proxy) with none of the usual signals.
    has_auth = (
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        or os.environ.get("RAE_E2E_ASSUME_AUTH") == "1"
        or _claude_credentials()
    )
    if not has_auth:
        pytest.fail("RAE_E2E=1 but no Claude auth found (ANTHROPIC_API_KEY, CLAUDE_CODE_OAUTH_TOKEN, or ~/.claude credentials)")
    if shutil.which("claude") is None:
        pytest.fail("RAE_E2E=1 but the Claude Code CLI is not on PATH: npm install -g @anthropic-ai/claude-code")


def _write_fixture_har(har_path: Path, url: str) -> None:
    body = json.dumps({"products": FIXTURE_PRODUCTS})
    har = {
        "log": {
            "version": "1.2",
            "creator": {"name": "rae-e2e", "version": "0"},
            "entries": [
                {
                    "startedDateTime": datetime.now(UTC).isoformat(),
                    "time": 12,
                    "request": {
                        "method": "GET",
                        "url": url,
                        "httpVersion": "HTTP/1.1",
                        "headers": [{"name": "Accept", "value": "application/json"}],
                        "queryString": [],
                        "cookies": [],
                        "headersSize": -1,
                        "bodySize": 0,
                    },
                    "response": {
                        "status": 200,
                        "statusText": "OK",
                        "httpVersion": "HTTP/1.1",
                        "headers": [{"name": "Content-Type", "value": "application/json"}],
                        "cookies": [],
                        "content": {"size": len(body), "mimeType": "application/json", "text": body},
                        "redirectURL": "",
                        "headersSize": -1,
                        "bodySize": len(body),
                    },
                    "cache": {},
                    "timings": {"send": 0, "wait": 12, "receive": 0},
                }
            ],
        }
    }
    har_path.parent.mkdir(parents=True, exist_ok=True)
    har_path.write_text(json.dumps(har))


def test_engineer_generates_and_verifies_client_live(fixture_site, tmp_path):
    _require_prereqs()

    out_dir = tmp_path / "out"
    home = tmp_path / "home"
    home.mkdir()
    # run_engineer falls back to <output_dir>/har/<run_id>/recording.har for
    # runs that aren't in history, so a fabricated run needs only the HAR.
    _write_fixture_har(out_dir / "har" / RUN_ID / "recording.har", f"{fixture_site}/api/products")

    env = os.environ.copy()
    env["HOME"] = str(home)  # keep ~/.reverse-api (config/history) off the host
    # The isolated HOME hides ~/.claude, so logged-in local runs (no key env)
    # need the CLI's credential + onboarding files carried over. API-key runs
    # (the nightly workflow) never hit this branch.
    creds = _claude_credentials()
    if creds is not None:
        (home / ".claude").mkdir()
        shutil.copy(creds, home / ".claude" / ".credentials.json")
        claude_config = Path.home() / ".claude.json"
        if claude_config.exists():
            shutil.copy(claude_config, home / ".claude.json")

    result = subprocess.run(
        [
            str(SCRIPT),
            "engineer",
            RUN_ID,
            "--json-stream",
            "-o",
            str(out_dir),
            "-m",
            "claude-haiku-4-5",
            "-p",
            (
                "The captured API is a single GET endpoint returning a JSON product "
                "list, and that server is live right now at the URL in the HAR. "
                "Write a minimal Python client exposing get_products(), then run it "
                "against the live server to verify it."
            ),
        ],
        capture_output=True,
        text=True,
        timeout=900,
        env=env,
    )

    events = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            events.append(json.loads(line))
    event_names = [e.get("event") for e in events]

    debug = f"exit={result.returncode}\nevents={event_names}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert result.returncode == 0, debug

    final = events[-1]
    assert final["event"] == "result", debug
    assert final["status"] == "ok", debug
    assert final["script_path"], debug

    # The agent must have actually executed the generated client against the
    # live fixture server — client_executed only fires from the MCP
    # verification tool, never from parsed prose.
    assert "client_executed" in event_names, debug

    script_path = Path(final["script_path"])
    assert script_path.exists(), debug
    assert fixture_site in script_path.read_text(), debug
    py_compile.compile(str(script_path), doraise=True)
