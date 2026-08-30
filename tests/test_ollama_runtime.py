"""Tests for Ollama discovery and OpenCode configuration."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2 as httpx
import pytest

from reverse_api import ollama_runtime


def _tags_payload() -> dict:
    return {
        "models": [
            {
                "name": "qwen3:4b",
                "size": 2_497_000_000,
            },
            {
                "name": "tiny:no-tools",
                "size": 100,
            },
            {
                "name": "tools:short-context",
                "size": 200,
            },
        ]
    }


def _show_payload(model: str) -> dict:
    metadata = {
        "qwen3:4b": ("qwen3", ["completion", "tools", "thinking"], "4.0B", 262_144),
        "tiny:no-tools": ("llama", ["completion"], "1B", 131_072),
        "tools:short-context": ("qwen", ["completion", "tools"], "2B", 32_768),
    }
    architecture, capabilities, parameter_size, context_length = metadata[model]
    return {
        "capabilities": capabilities,
        "details": {"parameter_size": parameter_size},
        "model_info": {
            "general.architecture": architecture,
            f"{architecture}.context_length": context_length,
        },
    }


def _models() -> tuple[ollama_runtime.OllamaModel, ...]:
    return tuple(ollama_runtime._parse_model(tag, _show_payload(tag["name"])) for tag in _tags_payload()["models"])


def _response(payload: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload if payload is not None else _tags_payload()
    return response


@pytest.fixture(autouse=True)
def reset_runtime_state():
    ollama_runtime._PROCESS = None
    ollama_runtime._PROCESS_URL = None
    ollama_runtime._PROCESS_CONTEXT_LENGTH = None
    yield
    ollama_runtime._PROCESS = None
    ollama_runtime._PROCESS_URL = None
    ollama_runtime._PROCESS_CONTEXT_LENGTH = None


def test_parse_show_metadata_filters_agent_compatible_models():
    models = _models()
    status = ollama_runtime.OllamaStatus(base_url="http://127.0.0.1:11434", models=models)

    assert [model.name for model in models] == ["qwen3:4b", "tiny:no-tools", "tools:short-context"]
    assert [model.name for model in status.compatible_models] == ["qwen3:4b"]


@pytest.mark.asyncio
async def test_reuses_running_ollama():
    client = AsyncMock()
    client.get = AsyncMock(return_value=_response())
    client.post = AsyncMock(side_effect=lambda _path, json: _response(_show_payload(json["model"])))

    with patch.object(ollama_runtime.httpx, "AsyncClient") as async_client:
        async_client.return_value.__aenter__ = AsyncMock(return_value=client)
        async_client.return_value.__aexit__ = AsyncMock(return_value=False)
        status = await ollama_runtime.ensure_ollama_models()

    assert status.started is False
    assert status.allocated_context_length is None
    assert status.models[0].name == "qwen3:4b"
    assert status.models[0].supports_opencode is True
    assert client.post.await_count == 3
    client.post.assert_any_await("/api/show", json={"model": "qwen3:4b"})


@pytest.mark.asyncio
async def test_starts_installed_ollama_daemon(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RAE_OLLAMA_BASE_URL", "127.0.0.1:11434")
    request = httpx.Request("GET", "http://127.0.0.1:11434/api/tags")
    client = AsyncMock()
    client.get = AsyncMock(side_effect=[httpx.ConnectError("refused", request=request), _response()])
    client.post = AsyncMock(side_effect=lambda _path, json: _response(_show_payload(json["model"])))
    process = MagicMock()
    process.poll.return_value = None

    with patch.object(ollama_runtime.httpx, "AsyncClient") as async_client:
        async_client.return_value.__aenter__ = AsyncMock(return_value=client)
        async_client.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch.object(ollama_runtime.shutil, "which", return_value="/usr/local/bin/ollama"):
            with patch.object(ollama_runtime.subprocess, "Popen", return_value=process) as popen:
                status = await ollama_runtime.ensure_ollama_models(timeout=1)

    assert status.started is True
    assert popen.call_args.args[0] == ["/usr/local/bin/ollama", "serve"]
    assert popen.call_args.kwargs["env"]["OLLAMA_HOST"] == "127.0.0.1:11434"
    assert popen.call_args.kwargs["env"]["OLLAMA_CONTEXT_LENGTH"] == "65536"
    assert status.allocated_context_length == 65_536


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_name", "message"),
    [
        ("missing:model", "not installed"),
        ("tiny:no-tools", "does not advertise tool calling"),
        ("tools:short-context", "requires at least 65,536"),
    ],
)
async def test_prepare_model_rejects_incompatible_models(model_name: str, message: str):
    status = ollama_runtime.OllamaStatus(
        base_url="http://127.0.0.1:11434",
        models=_models(),
    )
    with patch.object(ollama_runtime, "ensure_ollama_models", new=AsyncMock(return_value=status)):
        with pytest.raises(ollama_runtime.OllamaSetupError, match=message):
            await ollama_runtime.prepare_ollama_model(model_name)


def test_opencode_env_preserves_existing_config(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENCODE_CONFIG_CONTENT", '{"plugin":["example"],"provider":{"custom":{"name":"Custom"}}}')
    status = ollama_runtime.OllamaStatus(
        base_url="http://127.0.0.1:11434",
        models=_models(),
    )
    setup = ollama_runtime.OllamaProviderSetup(status=status, model=status.models[0])

    env = ollama_runtime.opencode_ollama_env(setup)
    config = json.loads(env["OPENCODE_CONFIG_CONTENT"])

    assert config["plugin"] == ["example"]
    assert config["provider"]["custom"]["name"] == "Custom"
    assert config["provider"]["ollama"]["options"]["baseURL"] == "http://127.0.0.1:11434/v1"
    assert list(config["provider"]["ollama"]["models"]) == ["qwen3:4b"]
    assert config["provider"]["ollama"]["models"]["qwen3:4b"]["limit"]["context"] == 262_144
    assert config["small_model"] == "ollama/qwen3:4b"


def test_opencode_env_advertises_managed_context_allocation():
    status = ollama_runtime.OllamaStatus(
        base_url="http://127.0.0.1:11434",
        models=_models(),
        started=True,
        allocated_context_length=65_536,
    )
    setup = ollama_runtime.OllamaProviderSetup(status=status, model=status.models[0])

    config = json.loads(ollama_runtime.opencode_ollama_env(setup)["OPENCODE_CONFIG_CONTENT"])

    assert config["provider"]["ollama"]["models"]["qwen3:4b"]["limit"]["context"] == 65_536


@pytest.mark.asyncio
async def test_validate_existing_opencode_ollama_config():
    client = AsyncMock()
    client.get = AsyncMock(return_value=_response({"provider": {"ollama": {"models": {"qwen3:4b": {"name": "qwen3:4b"}}}}}))

    await ollama_runtime.validate_opencode_ollama_provider(client, "qwen3:4b")

    client.get.assert_awaited_once_with("/config", timeout=5.0)


@pytest.mark.asyncio
async def test_validate_existing_opencode_requires_model_config():
    client = AsyncMock()
    client.get = AsyncMock(return_value=_response({"provider": {}}))

    with pytest.raises(ollama_runtime.OllamaSetupError, match="not configured"):
        await ollama_runtime.validate_opencode_ollama_provider(client, "qwen3:4b")


def test_stop_managed_ollama_server():
    process = MagicMock()
    process.poll.return_value = None
    ollama_runtime._PROCESS = process
    ollama_runtime._PROCESS_URL = "http://127.0.0.1:11434"
    ollama_runtime._PROCESS_CONTEXT_LENGTH = 65_536

    ollama_runtime.stop_managed_ollama_server()

    process.terminate.assert_called_once_with()
    process.wait.assert_called_once_with(timeout=3)
    assert ollama_runtime._PROCESS_CONTEXT_LENGTH is None
