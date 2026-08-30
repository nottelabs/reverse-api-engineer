"""Tests for managed OpenCode server startup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx2 as httpx
import pytest

from reverse_api import opencode_runtime


@pytest.fixture(autouse=True)
def reset_runtime_state():
    opencode_runtime._PROCESS = None
    opencode_runtime._PROCESS_URL = None
    opencode_runtime._PROCESS_ENV_OVERRIDES = {}
    yield
    opencode_runtime._PROCESS = None
    opencode_runtime._PROCESS_URL = None
    opencode_runtime._PROCESS_ENV_OVERRIDES = {}


def _health_response(version: str = "1.18.4") -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"healthy": True, "version": version}
    return response


def _catalog_response() -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "default": {"openai": "gpt-paid", "opencode": "big-pickle"},
        "providers": [
            {
                "id": "openai",
                "models": {
                    "gpt-paid": {
                        "status": "active",
                        "cost": {"input": 1, "output": 2},
                        "capabilities": {"toolcall": True},
                    }
                },
            },
            {
                "id": "opencode",
                "models": {
                    "big-pickle": {
                        "status": "active",
                        "cost": {"input": 0, "output": 0},
                        "capabilities": {"toolcall": True},
                    },
                    "no-tools-free": {
                        "status": "active",
                        "cost": {"input": 0, "output": 0},
                        "capabilities": {"toolcall": False},
                    },
                },
            },
        ],
    }
    return response


@pytest.mark.asyncio
async def test_reuses_healthy_server():
    client = AsyncMock()
    client.get = AsyncMock(return_value=_health_response())

    status = await opencode_runtime.ensure_opencode_server(client, base_url="http://127.0.0.1:4096")

    assert status.health["version"] == "1.18.4"
    assert status.started is False
    assert status.version_warning is None


@pytest.mark.asyncio
async def test_warns_for_compatible_but_older_server():
    client = AsyncMock()
    client.get = AsyncMock(return_value=_health_response("1.0.203"))

    status = await opencode_runtime.ensure_opencode_server(client, base_url="http://127.0.0.1:4096")

    assert "older than RAE's tested v1.18.4" in str(status.version_warning)


@pytest.mark.asyncio
async def test_validates_connected_provider_model_pair():
    client = AsyncMock()
    client.get = AsyncMock(return_value=_catalog_response())

    await opencode_runtime.validate_opencode_model(client, "opencode", "big-pickle")

    client.get.assert_awaited_once_with("/config/providers", timeout=10.0)


@pytest.mark.asyncio
async def test_model_catalog_endpoint_is_required_for_compatibility():
    request = httpx.Request("GET", "http://127.0.0.1:4096/config/providers")
    response = httpx.Response(404, request=request)
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)

    with pytest.raises(opencode_runtime.OpenCodeSetupError, match="server is incompatible"):
        await opencode_runtime.validate_opencode_model(client, "opencode", "big-pickle")


@pytest.mark.asyncio
async def test_invalid_provider_suggests_connected_and_free_models():
    client = AsyncMock()
    client.get = AsyncMock(return_value=_catalog_response())

    with pytest.raises(opencode_runtime.OpenCodeSetupError) as error:
        await opencode_runtime.validate_opencode_model(client, "anthropic", "claude-opus-4-6")

    message = str(error.value)
    assert "provider 'anthropic' is not connected" in message
    assert "Connected providers: openai, opencode" in message
    assert "opencode/big-pickle" in message
    assert "/settings" in message


@pytest.mark.asyncio
async def test_invalid_model_suggests_valid_pair_for_provider():
    client = AsyncMock()
    client.get = AsyncMock(return_value=_catalog_response())

    with pytest.raises(opencode_runtime.OpenCodeSetupError) as error:
        await opencode_runtime.validate_opencode_model(client, "openai", "missing")

    message = str(error.value)
    assert "openai/missing is not available" in message
    assert "Try: openai/gpt-paid" in message
    assert "opencode/big-pickle" in message


@pytest.mark.asyncio
async def test_rejects_model_without_tool_calling():
    client = AsyncMock()
    client.get = AsyncMock(return_value=_catalog_response())

    with pytest.raises(opencode_runtime.OpenCodeSetupError, match="does not support tool calling"):
        await opencode_runtime.validate_opencode_model(client, "opencode", "no-tools-free")


@pytest.mark.asyncio
async def test_starts_latest_package_without_global_opencode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENCODE_SERVER_PASSWORD", "secret")
    request = httpx.Request("GET", "http://127.0.0.1:4096/global/health")
    client = AsyncMock()
    client.get = AsyncMock(side_effect=[httpx.ConnectError("refused", request=request), _health_response()])
    process = MagicMock()
    process.poll.return_value = None

    with patch.object(opencode_runtime, "_config_manager_snapshot", return_value={}):
        with patch.object(
            opencode_runtime.shutil,
            "which",
            side_effect=lambda name: None if name == "opencode" else f"/bin/{name}",
        ):
            with patch.object(opencode_runtime.subprocess, "Popen", return_value=process) as popen:
                status = await opencode_runtime.ensure_opencode_server(
                    client,
                    base_url="http://127.0.0.1:4096",
                    env_overrides={"OPENCODE_CONFIG_CONTENT": "{}"},
                    timeout=1,
                )

    assert status.started is True
    assert status.package == "opencode-ai@latest"
    assert client.get.await_args_list[0].kwargs == {"timeout": 2.0}
    argv = popen.call_args.args[0]
    assert argv == [
        "/bin/npx",
        "-y",
        "opencode-ai@latest",
        "serve",
        "--hostname",
        "127.0.0.1",
        "--port",
        "4096",
    ]
    assert popen.call_args.kwargs["env"]["OPENCODE_SERVER_PASSWORD"] == "secret"
    assert popen.call_args.kwargs["env"]["OPENCODE_CONFIG_CONTENT"] == "{}"


@pytest.mark.asyncio
async def test_disabled_auto_start_has_actionable_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RAE_OPENCODE_AUTO_START", "0")
    request = httpx.Request("GET", "http://127.0.0.1:4096/global/health")
    client = AsyncMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("refused", request=request))

    with pytest.raises(opencode_runtime.OpenCodeSetupError, match="disabled"):
        await opencode_runtime.ensure_opencode_server(client, base_url="http://127.0.0.1:4096")


@pytest.mark.asyncio
async def test_restarts_managed_server_when_provider_config_changes():
    client = AsyncMock()
    client.get = AsyncMock(side_effect=[_health_response(), _health_response()])
    old_process = MagicMock()
    old_process.poll.return_value = None
    new_process = MagicMock()
    new_process.poll.return_value = None
    opencode_runtime._PROCESS = old_process
    opencode_runtime._PROCESS_URL = "http://127.0.0.1:4096"
    opencode_runtime._PROCESS_ENV_OVERRIDES = {"OPENCODE_CONFIG_CONTENT": '{"old":true}'}

    with patch.object(opencode_runtime, "_config_manager_snapshot", return_value={}):
        with patch.object(opencode_runtime.shutil, "which", side_effect=lambda name: f"/bin/{name}"):
            with patch.object(opencode_runtime.subprocess, "Popen", return_value=new_process):
                status = await opencode_runtime.ensure_opencode_server(
                    client,
                    base_url="http://127.0.0.1:4096",
                    env_overrides={"OPENCODE_CONFIG_CONTENT": '{"ollama":true}'},
                    timeout=1,
                )

    assert status.started is True
    old_process.terminate.assert_called_once_with()
    assert opencode_runtime._PROCESS_ENV_OVERRIDES == {"OPENCODE_CONFIG_CONTENT": '{"ollama":true}'}


@pytest.mark.asyncio
async def test_refuses_to_auto_start_remote_host():
    request = httpx.Request("GET", "https://opencode.example.com/global/health")
    client = AsyncMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("refused", request=request))

    with patch.object(opencode_runtime, "_config_manager_snapshot", return_value={}):
        with pytest.raises(opencode_runtime.OpenCodeSetupError, match="non-loopback"):
            await opencode_runtime.ensure_opencode_server(client, base_url="http://opencode.example.com:4096")


@pytest.mark.asyncio
async def test_start_timeout_stops_managed_child():
    request = httpx.Request("GET", "http://127.0.0.1:4096/global/health")
    client = AsyncMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("refused", request=request))
    process = MagicMock()
    process.poll.return_value = None

    with patch.object(opencode_runtime, "_config_manager_snapshot", return_value={}):
        with patch.object(opencode_runtime.shutil, "which", side_effect=lambda name: f"/bin/{name}"):
            with patch.object(opencode_runtime.subprocess, "Popen", return_value=process):
                with patch.object(opencode_runtime.time, "monotonic", side_effect=[0.0, 2.0]):
                    with pytest.raises(opencode_runtime.OpenCodeSetupError, match="Timed out"):
                        await opencode_runtime.ensure_opencode_server(
                            client,
                            base_url="http://127.0.0.1:4096",
                            timeout=1,
                        )

    process.terminate.assert_called_once_with()


def test_runtime_settings_environment_overrides(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENCODE_BASE_URL", "http://localhost:7777/")
    monkeypatch.setenv("RAE_OPENCODE_PACKAGE", "opencode-ai@test")
    monkeypatch.setenv("RAE_OPENCODE_AUTO_START", "false")

    assert opencode_runtime.opencode_base_url() == "http://localhost:7777"
    assert opencode_runtime.opencode_npx_package() == "opencode-ai@test"
    assert opencode_runtime.opencode_auto_start() is False


def test_stop_managed_server_terminates_child():
    process = MagicMock()
    process.poll.return_value = None
    opencode_runtime._PROCESS = process
    opencode_runtime._PROCESS_URL = "http://127.0.0.1:4096"

    opencode_runtime.stop_managed_opencode_server()

    process.terminate.assert_called_once_with()
    process.wait.assert_called_once_with(timeout=3)
    assert opencode_runtime._PROCESS is None
