"""OpenCode server discovery and managed startup.

Reverse API Engineer reuses an already-running OpenCode server when possible.
When the configured local server is unavailable, it can start the latest npm
release through ``npx`` and keep that process alive for the current RAE run.
"""

from __future__ import annotations

import atexit
import os
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx2 as httpx

from .utils import get_config_path

DEFAULT_OPENCODE_BASE_URL = "http://127.0.0.1:4096"
DEFAULT_OPENCODE_PACKAGE = "opencode-ai@latest"
TESTED_OPENCODE_VERSION = (1, 18, 4)
_START_TIMEOUT_SECONDS = 120.0

_PROCESS: subprocess.Popen[bytes] | None = None
_PROCESS_URL: str | None = None
_PROCESS_ENV_OVERRIDES: dict[str, str] = {}
_PROCESS_LOCK = threading.Lock()
_ATEXIT_REGISTERED = False


class OpenCodeSetupError(RuntimeError):
    """Raised when a local OpenCode server cannot be prepared."""


@dataclass(frozen=True)
class OpenCodeServerStatus:
    """Result of locating or starting the OpenCode server."""

    health: dict[str, Any]
    started: bool = False
    package: str | None = None
    version_warning: str | None = None


def _parse_version(value: object) -> tuple[int, int, int] | None:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", str(value or "").strip())
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())


def _format_version(version: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in version)


def opencode_version_warning(health: dict[str, Any]) -> str | None:
    """Warn about versions older than the server tested with this RAE release."""

    raw_version = health.get("version")
    version = _parse_version(raw_version)
    if version is None:
        return "OpenCode did not report a parseable version; compatibility will be checked through its APIs."
    if version < TESTED_OPENCODE_VERSION:
        tested = _format_version(TESTED_OPENCODE_VERSION)
        return (
            f"OpenCode v{raw_version} is older than RAE's tested v{tested}; required APIs will be checked before use. "
            "Stop the existing server to let RAE use opencode-ai@latest."
        )
    return None


def _tool_capable(model: dict[str, Any]) -> bool:
    capabilities = model.get("capabilities")
    return not isinstance(capabilities, dict) or capabilities.get("toolcall") is not False


def _active(model: dict[str, Any]) -> bool:
    return str(model.get("status") or "active").casefold() == "active"


def opencode_model_is_selectable(model: object) -> bool:
    """Return whether a catalog model is active and supports the tools RAE needs."""
    return isinstance(model, dict) and _active(model) and _tool_capable(model)


def opencode_model_is_free(provider_id: str, model_id: str, model: dict[str, Any]) -> bool:
    """Return whether a catalog entry is explicitly a free OpenCode model."""
    cost = model.get("cost")
    if not isinstance(cost, dict):
        return model_id.casefold().endswith("-free")
    input_cost = cost.get("input")
    output_cost = cost.get("output")
    return (input_cost == 0 and output_cost == 0) and (
        provider_id == "opencode" or model_id.casefold().endswith("-free")
    )


def _model_references(
    providers: list[dict[str, Any]],
    defaults: dict[str, Any],
    *,
    provider_id: str | None = None,
    free_only: bool = False,
    limit: int = 5,
) -> list[str]:
    references: list[str] = []
    for provider in providers:
        current_provider = str(provider.get("id") or "")
        if not current_provider or (provider_id is not None and current_provider != provider_id):
            continue
        models = provider.get("models")
        if not isinstance(models, dict):
            continue
        ordered_ids = list(models)
        default_model = defaults.get(current_provider)
        if default_model in models:
            ordered_ids.remove(default_model)
            ordered_ids.insert(0, default_model)
        for model_id in ordered_ids:
            model = models.get(model_id)
            if not opencode_model_is_selectable(model):
                continue
            if free_only and not opencode_model_is_free(current_provider, str(model_id), model):
                continue
            reference = f"{current_provider}/{model_id}"
            if reference not in references:
                references.append(reference)
            if len(references) == limit:
                return references
    return references


async def get_opencode_model_catalog(client: httpx.AsyncClient) -> dict[str, Any]:
    """Return OpenCode's provider/model catalog or raise an actionable setup error."""
    try:
        response = await client.get("/config/providers", timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise
        raise OpenCodeSetupError(
            f"OpenCode could not provide its model catalog (HTTP {e.response.status_code}). "
            "This server is incompatible because RAE requires /config/providers. "
            "Stop it so RAE can start opencode-ai@latest."
        ) from e
    except httpx.RequestError as e:
        raise OpenCodeSetupError(f"Could not read the OpenCode model catalog: {e}") from e

    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("providers"), list):
        raise OpenCodeSetupError("OpenCode returned an invalid model catalog from /config/providers.")
    return payload


async def validate_opencode_model(client: httpx.AsyncClient, provider_id: str, model_id: str) -> None:
    """Validate the configured pair before creating a session or starting agent work."""

    payload = await get_opencode_model_catalog(client)
    providers = [provider for provider in payload["providers"] if isinstance(provider, dict)]
    defaults = payload.get("default") if isinstance(payload.get("default"), dict) else {}
    provider = next((item for item in providers if item.get("id") == provider_id), None)
    free_models = _model_references(providers, defaults, free_only=True)
    free_hint = f" Free options currently available: {', '.join(free_models)}." if free_models else ""

    if provider is None:
        available = ", ".join(str(item.get("id")) for item in providers if item.get("id")) or "none"
        raise OpenCodeSetupError(
            f"Invalid OpenCode model pairing: provider {provider_id!r} is not connected. "
            f"Connected providers: {available}.{free_hint} Change OpenCode Provider and OpenCode Model in /settings."
        )

    models = provider.get("models")
    models = models if isinstance(models, dict) else {}
    model = models.get(model_id)
    if not isinstance(model, dict):
        suggestions = _model_references(providers, defaults, provider_id=provider_id)
        suggestion_hint = f" Try: {', '.join(suggestions)}." if suggestions else ""
        raise OpenCodeSetupError(
            f"Invalid OpenCode model pairing: {provider_id}/{model_id} is not available."
            f"{suggestion_hint}{free_hint} Change OpenCode Model in /settings."
        )
    if not _tool_capable(model):
        suggestions = _model_references(providers, defaults, provider_id=provider_id)
        suggestion_hint = f" Try: {', '.join(suggestions)}." if suggestions else ""
        raise OpenCodeSetupError(
            f"OpenCode model {provider_id}/{model_id} does not support tool calling, which RAE requires."
            f"{suggestion_hint}{free_hint}"
        )


def _config_manager_snapshot() -> dict[str, Any]:
    """Load config defaults merged with the user's RAE config."""

    try:
        from .config import ConfigManager

        return ConfigManager(get_config_path()).config.copy()
    except Exception:
        return {}


def opencode_base_url() -> str:
    """Return the OpenCode server URL, with an environment override."""

    env = os.environ.get("OPENCODE_BASE_URL", "").strip()
    if env:
        return env.rstrip("/")
    configured = str(_config_manager_snapshot().get("opencode_base_url") or DEFAULT_OPENCODE_BASE_URL)
    return configured.rstrip("/")


def opencode_npx_package() -> str:
    """Return the npm package used for managed OpenCode startup."""

    env = os.environ.get("RAE_OPENCODE_PACKAGE", "").strip()
    if env:
        return env
    return str(_config_manager_snapshot().get("opencode_npx_package") or DEFAULT_OPENCODE_PACKAGE)


def opencode_auto_start() -> bool:
    """Return whether RAE may start OpenCode when no server is listening."""

    env = os.environ.get("RAE_OPENCODE_AUTO_START")
    if env is not None:
        return env.strip().lower() not in {"0", "false", "no", "off"}
    return bool(_config_manager_snapshot().get("opencode_auto_start", True))


def _server_address(base_url: str) -> tuple[str, int]:
    parsed = urlparse(base_url)
    host = parsed.hostname
    if parsed.scheme != "http" or not host or parsed.path not in {"", "/"}:
        raise OpenCodeSetupError(f"Cannot auto-start OpenCode for {base_url!r}. Use a plain local http URL or start the custom server yourself.")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise OpenCodeSetupError(f"Refusing to auto-start OpenCode on non-loopback host {host!r}. Start that server yourself or disable auto-start.")
    try:
        port = parsed.port or 80
    except ValueError as e:
        raise OpenCodeSetupError(f"Invalid OpenCode server URL {base_url!r}: {e}") from e
    return host, port


def _start_managed_server(
    base_url: str,
    env_overrides: Mapping[str, str] | None = None,
) -> tuple[subprocess.Popen[bytes], str, bool]:
    """Start the configured OpenCode npm package once for this process."""

    global _ATEXIT_REGISTERED, _PROCESS, _PROCESS_ENV_OVERRIDES, _PROCESS_URL

    desired_env = dict(env_overrides or {})

    with _PROCESS_LOCK:
        if _PROCESS is not None and _PROCESS.poll() is None:
            if _PROCESS_URL != base_url:
                raise OpenCodeSetupError(f"RAE already manages OpenCode at {_PROCESS_URL}; it cannot also start {base_url} in the same process.")
            if _PROCESS_ENV_OVERRIDES != desired_env:
                raise OpenCodeSetupError("The managed OpenCode server needs different provider configuration; restart it and retry.")
            return _PROCESS, opencode_npx_package(), False

        host, port = _server_address(base_url)
        npx = shutil.which("npx")
        if npx is None or shutil.which("node") is None:
            raise OpenCodeSetupError(
                "OpenCode is not running and Node.js/npx is unavailable. Install Node.js 20+ or start `opencode serve` manually."
            )

        package = opencode_npx_package()
        argv = [npx, "-y", package, "serve", "--hostname", host, "--port", str(port)]
        child_env = os.environ.copy()
        child_env.update(desired_env)
        try:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=child_env,
                start_new_session=True,
            )
        except OSError as e:
            raise OpenCodeSetupError(f"Could not start `{package}` through npx: {e}") from e

        _PROCESS = process
        _PROCESS_URL = base_url
        _PROCESS_ENV_OVERRIDES = desired_env
        if not _ATEXIT_REGISTERED:
            atexit.register(stop_managed_opencode_server)
            _ATEXIT_REGISTERED = True
        return process, package, True


async def ensure_opencode_server(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    env_overrides: Mapping[str, str] | None = None,
    timeout: float = _START_TIMEOUT_SECONDS,
) -> OpenCodeServerStatus:
    """Reuse a healthy server or start the configured OpenCode release locally."""

    try:
        response = await client.get("/global/health", timeout=2.0)
        response.raise_for_status()
        health = response.json()
        if not isinstance(health, dict):
            raise OpenCodeSetupError("OpenCode returned an invalid health response.")
        version_warning = opencode_version_warning(health)
        desired_env = dict(env_overrides or {})
        with _PROCESS_LOCK:
            restart_managed = _PROCESS is not None and _PROCESS.poll() is None and _PROCESS_URL == base_url and _PROCESS_ENV_OVERRIDES != desired_env
        if not restart_managed:
            return OpenCodeServerStatus(health=health, version_warning=version_warning)
        stop_managed_opencode_server()
    except httpx.HTTPStatusError:
        raise
    except httpx.RequestError as initial_error:
        if not opencode_auto_start():
            raise OpenCodeSetupError(
                f"OpenCode is not responding at {base_url} and automatic startup is disabled. Run `opencode serve` first."
            ) from initial_error

    process, package, started = _start_managed_server(base_url, env_overrides)
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise OpenCodeSetupError(f"`npx -y {package} serve` exited with status {process.returncode} before becoming healthy.")
        try:
            response = await client.get("/global/health", timeout=2.0)
            response.raise_for_status()
            health = response.json()
            if not isinstance(health, dict):
                raise OpenCodeSetupError("OpenCode returned an invalid health response.")
            try:
                version_warning = opencode_version_warning(health)
            except OpenCodeSetupError:
                if started:
                    stop_managed_opencode_server()
                raise
            return OpenCodeServerStatus(
                health=health,
                started=started,
                package=package,
                version_warning=version_warning,
            )
        except httpx.HTTPStatusError:
            if started:
                stop_managed_opencode_server()
            raise
        except httpx.RequestError as e:
            last_error = e
            import asyncio

            await asyncio.sleep(0.25)

    if started:
        stop_managed_opencode_server()
    raise OpenCodeSetupError(f"Timed out after {timeout:.0f}s waiting for `npx -y {package} serve` at {base_url}.") from last_error


def stop_managed_opencode_server() -> None:
    """Stop the OpenCode child process started by RAE, if any."""

    global _PROCESS, _PROCESS_ENV_OVERRIDES, _PROCESS_URL

    with _PROCESS_LOCK:
        process = _PROCESS
        _PROCESS = None
        _PROCESS_URL = None
        _PROCESS_ENV_OVERRIDES = {}

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
