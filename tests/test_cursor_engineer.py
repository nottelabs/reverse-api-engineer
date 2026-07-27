"""Tests for Cursor SDK bridge integration (mocked, no real API calls)."""

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reverse_api.cursor_engineer import CursorEngineer, CursorStreamUI, _ensure_cursor_bridge_deps


@pytest.fixture
def har_path(tmp_path: Path) -> Path:
    p = tmp_path / "recording.har"
    p.write_text('{"log":{"entries":[]}}')
    return p


@pytest.mark.asyncio
async def test_cursor_engineer_analyze_missing_api_key(har_path: Path) -> None:
    with patch.dict("os.environ", {"CURSOR_API_KEY": ""}):
        with patch("reverse_api.cursor_engineer._ensure_cursor_bridge_deps", return_value=None):
            eng = CursorEngineer(
                run_id="abc123",
                har_path=har_path,
                prompt="test",
                cursor_model="composer-2",
                sdk="cursor",
                interactive=False,
                verbose=False,
            )
            out = await eng.analyze_and_generate()
    assert out is None


@pytest.mark.asyncio
async def test_cursor_engineer_one_turn_error(har_path: Path) -> None:
    with patch.dict("os.environ", {"CURSOR_API_KEY": "test-key"}):
        with patch("reverse_api.cursor_engineer._ensure_cursor_bridge_deps", return_value=None):
            eng = CursorEngineer(
                run_id="abc123",
                har_path=har_path,
                prompt="test",
                cursor_model="composer-2",
                sdk="cursor",
                interactive=False,
                verbose=False,
            )
            with patch.object(eng, "_one_turn", new=AsyncMock(return_value={"error": "simulated"})):
                out = await eng.analyze_and_generate()
    assert out is None


@pytest.mark.asyncio
async def test_cursor_engineer_success_non_interactive(har_path: Path) -> None:
    with patch.dict("os.environ", {"CURSOR_API_KEY": "test-key"}):
        with patch("reverse_api.cursor_engineer._ensure_cursor_bridge_deps", return_value=None):
            eng = CursorEngineer(
                run_id="abc123",
                har_path=har_path,
                prompt="test",
                cursor_model="composer-2",
                sdk="cursor",
                interactive=False,
                verbose=False,
            )
            with patch.object(
                eng,
                "_one_turn",
                new=AsyncMock(return_value={"ok": True, "agentId": "agent-xyz"}),
            ):
                with patch.object(eng.ui, "success", MagicMock()):
                    with patch.object(eng.ui.console, "print", MagicMock()):
                        out = await eng.analyze_and_generate()
            assert out is not None
    assert out.get("script_path", "").endswith("api_client.py")
    assert isinstance(eng.ui, CursorStreamUI)


def test_cursor_stream_ui_routes_thinking_to_buffer(har_path: Path) -> None:
    with patch.dict("os.environ", {"CURSOR_API_KEY": "x"}):
        with patch("reverse_api.cursor_engineer._ensure_cursor_bridge_deps", return_value=None):
            eng = CursorEngineer(
                run_id="r2",
                har_path=har_path,
                prompt="p",
                sdk="cursor",
                interactive=False,
                verbose=True,
            )
    eng._cursor_reset_stream_buffers()
    eng.ui.thinking("alpha")
    eng.ui.thinking("beta")
    assert eng._cursor_thinking_acc == "alphabeta"


def test_ensure_bridge_missing_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import reverse_api.cursor_engineer as ce

    monkeypatch.setattr(ce, "_BRIDGE_SCRIPT", tmp_path / "nonexistent.mjs")
    err = _ensure_cursor_bridge_deps()
    assert err is not None


def _mock_bridge_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    import reverse_api.cursor_engineer as ce

    bridge = tmp_path / "cursor_bridge"
    marker = bridge / "node_modules" / "@cursor" / "sdk"
    stamp = bridge / "node_modules" / ".rae-package-lock.sha256"
    marker.mkdir(parents=True)
    (bridge / "run.mjs").write_text("")
    (bridge / "package-lock.json").write_text('{"lockfileVersion":3}\n')
    monkeypatch.setattr(ce, "_BRIDGE_DIR", bridge)
    monkeypatch.setattr(ce, "_BRIDGE_SCRIPT", bridge / "run.mjs")
    monkeypatch.setattr(ce, "_BRIDGE_LOCKFILE", bridge / "package-lock.json")
    monkeypatch.setattr(ce, "_SDK_MARKER", marker)
    monkeypatch.setattr(ce, "_BRIDGE_INSTALL_STAMP", stamp)
    monkeypatch.setattr(ce, "_cursor_node_version_error", lambda: None)
    return bridge, stamp


@pytest.mark.parametrize("version", ["v22.13.0", "v23.0.0", "v25.8.2"])
def test_cursor_node_version_accepts_supported_versions(
    version: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import reverse_api.cursor_engineer as ce

    monkeypatch.setattr(ce.shutil, "which", lambda _: "/usr/bin/node")
    with patch.object(ce.subprocess, "run", return_value=MagicMock(stdout=f"{version}\n")):
        assert ce._cursor_node_version_error() is None


@pytest.mark.parametrize("version", ["v18.17.0", "v22.12.9"])
def test_cursor_node_version_rejects_unsupported_versions(
    version: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import reverse_api.cursor_engineer as ce

    monkeypatch.setattr(ce.shutil, "which", lambda _: "/usr/bin/node")
    with patch.object(ce.subprocess, "run", return_value=MagicMock(stdout=f"{version}\n")):
        error = ce._cursor_node_version_error()

    assert error is not None
    assert "requires Node.js 22.13+" in error
    assert version.lstrip("v") in error


def test_cursor_node_version_reports_missing_node(monkeypatch: pytest.MonkeyPatch) -> None:
    import reverse_api.cursor_engineer as ce

    monkeypatch.setattr(ce.shutil, "which", lambda _: None)
    assert ce._cursor_node_version_error() == (
        "node not found in PATH (Cursor SDK requires Node.js 22.13+)"
    )


def test_ensure_bridge_rejects_unsupported_node_before_current_fast_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import reverse_api.cursor_engineer as ce

    bridge, stamp = _mock_bridge_paths(tmp_path, monkeypatch)
    digest = hashlib.sha256((bridge / "package-lock.json").read_bytes()).hexdigest()
    stamp.write_text(f"{digest}\n")
    monkeypatch.setattr(
        ce,
        "_cursor_node_version_error",
        lambda: "Cursor SDK requires Node.js 22.13+; found Node.js 22.12.9",
    )

    with patch.object(ce.subprocess, "run") as run:
        error = _ensure_cursor_bridge_deps()

    assert error == "Cursor SDK requires Node.js 22.13+; found Node.js 22.12.9"
    run.assert_not_called()


def test_ensure_bridge_skips_install_when_lock_stamp_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bridge, stamp = _mock_bridge_paths(tmp_path, monkeypatch)
    digest = hashlib.sha256((bridge / "package-lock.json").read_bytes()).hexdigest()
    stamp.write_text(f"{digest}\n")

    with patch("reverse_api.cursor_engineer.subprocess.run") as run:
        assert _ensure_cursor_bridge_deps() is None

    run.assert_not_called()


@pytest.mark.parametrize("stamp_value", [None, "stale\n"], ids=["missing", "stale"])
def test_ensure_bridge_reinstalls_when_lock_stamp_is_not_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stamp_value: str | None
) -> None:
    bridge, stamp = _mock_bridge_paths(tmp_path, monkeypatch)
    if stamp_value is not None:
        stamp.write_text(stamp_value)
    monkeypatch.setattr("reverse_api.cursor_engineer.shutil.which", lambda _: "/usr/bin/npm")

    with patch("reverse_api.cursor_engineer.subprocess.run") as run:
        assert _ensure_cursor_bridge_deps() is None

    run.assert_called_once_with(
        ["/usr/bin/npm", "install", "--no-fund", "--no-audit"],
        cwd=str(bridge),
        check=True,
        timeout=600,
        capture_output=True,
        text=True,
    )
    expected = hashlib.sha256((bridge / "package-lock.json").read_bytes()).hexdigest()
    assert stamp.read_text().strip() == expected


def test_cursor_stream_buffers_merge_assistant(tmp_path: Path) -> None:
    har = tmp_path / "recording.har"
    har.write_text("{}")
    with patch.dict("os.environ", {"CURSOR_API_KEY": "x"}):
        with patch("reverse_api.cursor_engineer._ensure_cursor_bridge_deps", return_value=None):
            eng = CursorEngineer(
                run_id="r1",
                har_path=har,
                prompt="p",
                cursor_model="composer-2",
                sdk="cursor",
                interactive=False,
                verbose=False,
                output_dir=str(tmp_path),
            )
    eng._cursor_reset_stream_buffers()
    eng._cursor_feed_assistant("Hello")
    eng._cursor_feed_assistant("Hello world")
    assert eng._cursor_assistant_acc == "Hello world"
    eng._cursor_reset_stream_buffers()
    eng._cursor_feed_assistant("Hello")
    eng._cursor_feed_assistant(" world")
    assert eng._cursor_assistant_acc == "Hello world"
    eng._cursor_feed_thinking(" t1")
    eng._cursor_feed_thinking(" t2")
    assert eng._cursor_thinking_acc == " t1 t2"


def test_cursor_reset_clears_started_calls(har_path: Path) -> None:
    """_cursor_started_calls is cleared each turn so stale ids can't suppress tool_start."""
    with patch.dict("os.environ", {"CURSOR_API_KEY": "x"}):
        with patch("reverse_api.cursor_engineer._ensure_cursor_bridge_deps", return_value=None):
            eng = CursorEngineer(
                run_id="r4",
                har_path=har_path,
                prompt="p",
                sdk="cursor",
                interactive=False,
                verbose=False,
            )
    eng._cursor_started_calls.add("stale-call-id")
    eng._cursor_reset_stream_buffers()
    assert eng._cursor_started_calls == set()
