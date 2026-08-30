"""Ollama discovery, lifecycle, and OpenCode provider configuration."""

from __future__ import annotations

import asyncio
import atexit
import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx2 as httpx

from .utils import get_config_path

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
MIN_OPENCODE_CONTEXT = 65_536
_START_TIMEOUT_SECONDS = 30.0

_PROCESS: subprocess.Popen[bytes] | None = None
_PROCESS_URL: str | None = None
_PROCESS_CONTEXT_LENGTH: int | None = None
_PROCESS_LOCK = threading.Lock()
_ATEXIT_REGISTERED = False


class OllamaSetupError(RuntimeError):
    """Raised when Ollama or the selected model is not ready for agent use."""


@dataclass(frozen=True)
class OllamaModel:
    """Installed Ollama model metadata relevant to OpenCode."""

    name: str
    size: int
    capabilities: tuple[str, ...]
    context_length: int
    parameter_size: str = ""

    @property
    def supports_tools(self) -> bool:
        return "tools" in self.capabilities

    @property
    def supports_opencode(self) -> bool:
        return self.supports_tools and self.context_length >= MIN_OPENCODE_CONTEXT


@dataclass(frozen=True)
class OllamaStatus:
    """Ollama daemon state and installed models."""

    base_url: str
    models: tuple[OllamaModel, ...]
    started: bool = False
    allocated_context_length: int | None = None

    @property
    def compatible_models(self) -> tuple[OllamaModel, ...]:
        return tuple(model for model in self.models if model.supports_opencode)


@dataclass(frozen=True)
class OllamaProviderSetup:
    """Validated model plus the daemon state used to configure OpenCode."""

    status: OllamaStatus
    model: OllamaModel


def _config_manager_snapshot() -> dict[str, Any]:
    try:
        from .config import ConfigManager

        return ConfigManager(get_config_path()).config.copy()
    except Exception:
        return {}


def ollama_base_url() -> str:
    """Return the Ollama API URL, with an RAE-specific env override."""

    env = os.environ.get("RAE_OLLAMA_BASE_URL", "").strip()
    if env:
        if "://" not in env:
            env = f"http://{env}"
        return env.rstrip("/")
    configured = str(_config_manager_snapshot().get("ollama_base_url") or DEFAULT_OLLAMA_BASE_URL)
    return configured.rstrip("/")


def ollama_auto_start() -> bool:
    """Return whether RAE may start an installed Ollama daemon."""

    env = os.environ.get("RAE_OLLAMA_AUTO_START")
    if env is not None:
        return env.strip().lower() not in {"0", "false", "no", "off"}
    return bool(_config_manager_snapshot().get("ollama_auto_start", True))


def _context_length(show: dict[str, Any]) -> int:
    """Read the architecture-specific context window returned by /api/show."""

    model_info = show.get("model_info") or {}
    if not isinstance(model_info, dict):
        return 0
    architecture = str(model_info.get("general.architecture") or "").strip()
    keys = [f"{architecture}.context_length"] if architecture else []
    keys.extend(key for key in model_info if str(key).endswith(".context_length") and key not in keys)
    for key in keys:
        try:
            return int(model_info[key])
        except (KeyError, TypeError, ValueError):
            continue
    return 0


def _parse_model(tag: dict[str, Any], show: dict[str, Any]) -> OllamaModel:
    """Merge list metadata from /api/tags with capabilities from /api/show."""

    name = str(tag.get("name") or tag.get("model") or "").strip()
    details = show.get("details") or {}
    if not isinstance(details, dict):
        details = {}
    return OllamaModel(
        name=name,
        size=int(tag.get("size") or 0),
        capabilities=tuple(str(value) for value in show.get("capabilities") or ()),
        context_length=_context_length(show),
        parameter_size=str(details.get("parameter_size") or ""),
    )


async def _load_models(client: httpx.AsyncClient, base_url: str, payload: dict[str, Any]) -> tuple[OllamaModel, ...]:
    """Enrich every installed model with its authoritative /api/show metadata."""

    tags = [raw for raw in payload.get("models", []) if isinstance(raw, dict) and str(raw.get("name") or raw.get("model") or "").strip()]

    async def load(tag: dict[str, Any]) -> OllamaModel:
        name = str(tag.get("name") or tag.get("model")).strip()
        response = await client.post("/api/show", json={"model": name})
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise OllamaSetupError(f"Ollama at {base_url} returned HTTP {e.response.status_code} for /api/show ({name}).") from e
        show = response.json()
        if not isinstance(show, dict):
            raise OllamaSetupError(f"Ollama returned invalid /api/show metadata for {name!r}.")
        return _parse_model(tag, show)

    return tuple(await asyncio.gather(*(load(tag) for tag in tags)))


def _server_address(base_url: str) -> tuple[str, int]:
    parsed = urlparse(base_url)
    host = parsed.hostname
    if parsed.scheme != "http" or not host or parsed.path not in {"", "/"}:
        raise OllamaSetupError(f"Cannot auto-start Ollama for {base_url!r}; use a plain local http URL.")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise OllamaSetupError(f"Refusing to auto-start Ollama on non-loopback host {host!r}.")
    try:
        port = parsed.port or 80
    except ValueError as e:
        raise OllamaSetupError(f"Invalid Ollama URL {base_url!r}: {e}") from e
    return host, port


def _managed_context_length(base_url: str) -> int | None:
    """Return the configured context window for RAE's live managed daemon."""

    with _PROCESS_LOCK:
        if _PROCESS is not None and _PROCESS.poll() is None and _PROCESS_URL == base_url:
            return _PROCESS_CONTEXT_LENGTH
    return None


def _start_managed_server(base_url: str) -> tuple[subprocess.Popen[bytes], bool]:
    global _ATEXIT_REGISTERED, _PROCESS, _PROCESS_CONTEXT_LENGTH, _PROCESS_URL

    with _PROCESS_LOCK:
        if _PROCESS is not None and _PROCESS.poll() is None:
            if _PROCESS_URL != base_url:
                raise OllamaSetupError(f"RAE already manages Ollama at {_PROCESS_URL}; it cannot also start {base_url}.")
            return _PROCESS, False

        host, port = _server_address(base_url)
        executable = shutil.which("ollama")
        if executable is None:
            raise OllamaSetupError("Ollama is not running and the `ollama` command is not installed. Install it from https://ollama.com/download.")

        child_env = os.environ.copy()
        child_env["OLLAMA_HOST"] = f"{host}:{port}"
        child_env["OLLAMA_CONTEXT_LENGTH"] = str(MIN_OPENCODE_CONTEXT)
        try:
            process = subprocess.Popen(
                [executable, "serve"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=child_env,
                start_new_session=True,
            )
        except OSError as e:
            raise OllamaSetupError(f"Could not start `ollama serve`: {e}") from e

        _PROCESS = process
        _PROCESS_URL = base_url
        _PROCESS_CONTEXT_LENGTH = MIN_OPENCODE_CONTEXT
        if not _ATEXIT_REGISTERED:
            atexit.register(stop_managed_ollama_server)
            _ATEXIT_REGISTERED = True
        return process, True


async def ensure_ollama_models(*, timeout: float = _START_TIMEOUT_SECONDS) -> OllamaStatus:
    """Reuse Ollama or start an installed daemon, then return model metadata."""

    base_url = ollama_base_url()
    async with httpx.AsyncClient(base_url=base_url, timeout=2.0) as client:
        try:
            response = await client.get("/api/tags")
            response.raise_for_status()
            return OllamaStatus(
                base_url=base_url,
                models=await _load_models(client, base_url, response.json()),
                allocated_context_length=_managed_context_length(base_url),
            )
        except httpx.HTTPStatusError as e:
            raise OllamaSetupError(f"Ollama at {base_url} returned HTTP {e.response.status_code} for /api/tags.") from e
        except httpx.RequestError as initial_error:
            if not ollama_auto_start():
                raise OllamaSetupError(
                    f"Ollama is not responding at {base_url} and automatic startup is disabled. Run `ollama serve` first."
                ) from initial_error

        process, started = _start_managed_server(base_url)
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise OllamaSetupError(f"`ollama serve` exited with status {process.returncode} before becoming healthy.")
            try:
                response = await client.get("/api/tags")
                response.raise_for_status()
                return OllamaStatus(
                    base_url=base_url,
                    models=await _load_models(client, base_url, response.json()),
                    started=started,
                    allocated_context_length=_managed_context_length(base_url),
                )
            except httpx.HTTPStatusError as e:
                if started:
                    stop_managed_ollama_server()
                raise OllamaSetupError(f"Ollama at {base_url} returned HTTP {e.response.status_code} for /api/tags.") from e
            except httpx.RequestError as e:
                last_error = e
                await asyncio.sleep(0.25)

    if started:
        stop_managed_ollama_server()
    raise OllamaSetupError(f"Timed out after {timeout:.0f}s waiting for Ollama at {base_url}.") from last_error


async def prepare_ollama_model(model_name: str) -> OllamaProviderSetup:
    """Validate that an installed model can drive the OpenCode agent loop."""

    status = await ensure_ollama_models()
    selected = next((model for model in status.models if model.name == model_name), None)
    if selected is None:
        available = ", ".join(model.name for model in status.models) or "none"
        raise OllamaSetupError(
            f"Ollama model {model_name!r} is not installed. Installed models: {available}. Pull it explicitly with `ollama pull {model_name}`."
        )
    if not selected.supports_tools:
        raise OllamaSetupError(f"Ollama model {model_name!r} does not advertise tool calling, which RAE requires.")
    if selected.context_length < MIN_OPENCODE_CONTEXT:
        raise OllamaSetupError(f"Ollama model {model_name!r} has a {selected.context_length:,}-token context; OpenCode requires at least 65,536.")
    return OllamaProviderSetup(status=status, model=selected)


def opencode_ollama_env(setup: OllamaProviderSetup) -> dict[str, str]:
    """Build inline OpenCode config without overwriting a user's config file."""

    raw = os.environ.get("OPENCODE_CONFIG_CONTENT", "").strip()
    try:
        config = json.loads(raw) if raw else {}
    except json.JSONDecodeError as e:
        raise OllamaSetupError(f"OPENCODE_CONFIG_CONTENT is not valid JSON: {e}") from e
    if not isinstance(config, dict):
        raise OllamaSetupError("OPENCODE_CONFIG_CONTENT must contain a JSON object.")

    providers = config.setdefault("provider", {})
    if not isinstance(providers, dict):
        raise OllamaSetupError("OPENCODE_CONFIG_CONTENT field 'provider' must be a JSON object.")
    ollama = providers.setdefault("ollama", {})
    if not isinstance(ollama, dict):
        raise OllamaSetupError("OPENCODE_CONFIG_CONTENT field 'provider.ollama' must be a JSON object.")
    ollama["npm"] = "@ai-sdk/openai-compatible"
    ollama["name"] = "Ollama"
    options = ollama.setdefault("options", {})
    if not isinstance(options, dict):
        raise OllamaSetupError("OPENCODE_CONFIG_CONTENT field 'provider.ollama.options' must be a JSON object.")
    options["baseURL"] = f"{setup.status.base_url}/v1"
    models = ollama.setdefault("models", {})
    if not isinstance(models, dict):
        raise OllamaSetupError("OPENCODE_CONFIG_CONTENT field 'provider.ollama.models' must be a JSON object.")
    for model in setup.status.compatible_models:
        context_length = model.context_length
        if setup.status.allocated_context_length is not None:
            context_length = min(context_length, setup.status.allocated_context_length)
        models[model.name] = {
            "name": model.name,
            "limit": {
                "context": context_length,
                "output": min(context_length, 8192),
            },
        }
    config["small_model"] = f"ollama/{setup.model.name}"
    return {"OPENCODE_CONFIG_CONTENT": json.dumps(config, separators=(",", ":"), sort_keys=True)}


async def validate_opencode_ollama_provider(client: httpx.AsyncClient, model_name: str) -> None:
    """Ensure a reused OpenCode server already exposes the selected Ollama model."""

    response = await client.get("/config", timeout=5.0)
    response.raise_for_status()
    config = response.json()
    if not isinstance(config, dict):
        raise OllamaSetupError("OpenCode returned an invalid configuration response.")
    model_config = ((config.get("provider") or {}).get("ollama") or {}).get("models") or {}
    if model_name not in model_config:
        raise OllamaSetupError(
            "The existing OpenCode server is not configured for "
            f"ollama/{model_name}. Stop it so RAE can start a configured server, or restart it with `ollama launch opencode`."
        )


def stop_managed_ollama_server() -> None:
    """Stop the Ollama child process started by RAE, if any."""

    global _PROCESS, _PROCESS_CONTEXT_LENGTH, _PROCESS_URL

    with _PROCESS_LOCK:
        process = _PROCESS
        _PROCESS = None
        _PROCESS_URL = None
        _PROCESS_CONTEXT_LENGTH = None

    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
    except OSError:
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
