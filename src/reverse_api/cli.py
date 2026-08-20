import asyncio
import json
import os
import random
import sys
from contextlib import contextmanager
from pathlib import Path

import click
import questionary
import setproctitle
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style as PtStyle
from questionary import Choice
from rich.console import Console
from rich.markup import escape

from . import __version__, cloud
from .config import DEFAULT_OPENCODE_MODEL, DEFAULT_OPENCODE_PROVIDER, ConfigManager
from .engineer import run_reverse_engineering
from .messages import MessageStore
from .session import SessionManager
from .tui import (
    ERROR_CTA,
    MODE_COLORS,
    THEME_DIM,
    THEME_PRIMARY,
    THEME_SECONDARY,
    display_banner,
    display_footer,
    get_model_choices,
)
from .utils import (
    check_for_updates,
    discover_scripts,
    generate_folder_name,
    generate_run_id,
    get_base_output_dir,
    get_config_path,
    get_har_dir,
    get_history_path,
    get_messages_path,
    get_timestamp,
    resolve_run,
)

setproctitle.setproctitle("reverse-api-engineer")
setproctitle.setthreadtitle("reverse-api-engineer")

console = Console()
config_manager = ConfigManager(get_config_path())
session_manager = SessionManager(get_history_path())


def _format_ollama_size(size: int) -> str:
    if size < 1024:
        return "cloud"
    return f"{size / (1024**3):.1f} GB"


def _select_ollama_model_for_settings() -> str | None:
    """Discover installed agent-capable Ollama models and let the user choose."""

    from .ollama_runtime import OllamaSetupError, ensure_ollama_models

    try:
        status = asyncio.run(ensure_ollama_models())
    except OllamaSetupError as e:
        console.print(f" [yellow]error:[/yellow] {escape(str(e))}\n")
        return None

    models = status.compatible_models
    if not models:
        console.print(" [yellow]error:[/yellow] no installed Ollama model supports tools with at least 64k context")
        console.print(" [dim]Pull a compatible model explicitly, then retry. RAE will not download multi-GB models silently.[/dim]\n")
        return None
    if len(models) == 1:
        console.print(f" [dim]using the only compatible Ollama model: {models[0].name}[/dim]")
        return models[0].name

    choices = [
        Choice(
            title=(
                f"{model.name}  ({model.parameter_size or 'unknown'}, {_format_ollama_size(model.size)}, "
                f"{model.context_length // 1024}k context)"
            ),
            value=model.name,
        )
        for model in models
    ]
    choices.append(Choice(title="back", value="back"))
    selected = questionary.select(
        " > ollama model",
        choices=choices,
        pointer=">",
        qmark="",
        style=questionary.Style(
            [
                ("pointer", f"fg:{THEME_SECONDARY} bold"),
                ("highlighted", f"fg:{THEME_SECONDARY} bold"),
            ]
        ),
    ).ask()
    return None if selected in {None, "back"} else str(selected)


def default_model_for_configured_sdk(sdk: str | None = None) -> str:
    """Return the configured default model id for the given SDK (or current config SDK)."""
    s = (sdk or config_manager.get("sdk", "claude") or "claude").lower()
    if s == "opencode":
        return config_manager.get("opencode_model", DEFAULT_OPENCODE_MODEL)
    if s == "copilot":
        return config_manager.get("copilot_model", "gpt-5")
    if s == "cursor":
        return config_manager.get("cursor_model", "composer-2.5")
    return config_manager.get("claude_code_model", "claude-sonnet-4-6")


async def _load_opencode_catalog_for_settings() -> dict:
    """Start or reuse OpenCode and load its live provider/model catalog."""
    import httpx

    from .opencode_runtime import (
        ensure_opencode_server,
        get_opencode_model_catalog,
        opencode_base_url,
    )

    base_url = opencode_base_url()
    password = os.environ.get("OPENCODE_SERVER_PASSWORD")
    username = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode")
    auth = httpx.BasicAuth(username, password) if password else None
    async with httpx.AsyncClient(base_url=base_url, timeout=120.0, auth=auth) as client:
        await ensure_opencode_server(client, base_url=base_url)
        return await get_opencode_model_catalog(client)


def _select_opencode_pair_for_settings(mode_color=THEME_PRIMARY) -> tuple[str, str] | None:
    """Select a valid tool-capable provider/model pair from the live OpenCode catalog."""
    from .opencode_runtime import opencode_model_is_free, opencode_model_is_selectable

    try:
        with console.status(" Loading OpenCode providers and models...", spinner="dots"):
            catalog = asyncio.run(_load_opencode_catalog_for_settings())
    except Exception as e:
        response = getattr(e, "response", None)
        if getattr(response, "status_code", None) == 401:
            console.print(
                " [yellow]error:[/yellow] OpenCode authentication failed. "
                "Set OPENCODE_SERVER_PASSWORD (and OPENCODE_SERVER_USERNAME when customized).\n"
            )
        else:
            console.print(f" [yellow]error:[/yellow] could not load OpenCode providers and models: {escape(str(e))}\n")
        return None

    providers = [provider for provider in catalog.get("providers", []) if isinstance(provider, dict)]
    defaults = catalog.get("default") if isinstance(catalog.get("default"), dict) else {}
    selectable = []
    for provider in providers:
        models = provider.get("models")
        if provider.get("id") and isinstance(models, dict) and any(opencode_model_is_selectable(model) for model in models.values()):
            selectable.append(provider)

    style = questionary.Style(
        [
            ("pointer", f"fg:{mode_color} bold"),
            ("highlighted", f"fg:{mode_color} bold"),
        ]
    )
    current_provider = config_manager.get("opencode_provider", "")
    provider_choices = []
    for provider in selectable:
        provider_id = str(provider["id"])
        provider_name = str(provider.get("name") or "")
        title = (
            f"{provider_id} — {provider_name}"
            if provider_name and provider_name != provider_id
            else provider_id
        )
        provider_choices.append(Choice(title=title, value=provider_id))
    provider_ids = {str(provider["id"]) for provider in selectable}
    if "ollama" not in provider_ids:
        provider_choices.append(Choice(title="ollama — installed local models", value="ollama"))
        provider_ids.add("ollama")
    provider_choices.append(Choice(title="back", value="back"))
    provider_id = questionary.select(
        " > opencode provider",
        choices=provider_choices,
        default=current_provider if current_provider in provider_ids else None,
        pointer=">",
        qmark="",
        style=style,
        use_search_filter=True,
        use_jk_keys=False,
    ).ask()
    if provider_id is None or provider_id == "back":
        return None
    if provider_id == "ollama":
        model_id = _select_ollama_model_for_settings()
        return ("ollama", model_id) if model_id else None

    provider = next(item for item in selectable if item.get("id") == provider_id)
    models = provider["models"]
    current_model = config_manager.get("opencode_model", "") if provider_id == current_provider else ""
    default_model = str(defaults.get(provider_id) or "")
    model_ids = [str(model_id) for model_id, model in models.items() if opencode_model_is_selectable(model)]
    model_ids.sort(key=lambda model_id: (model_id not in {current_model, default_model}, model_id))
    model_choices = []
    for model_id in model_ids:
        model = models[model_id]
        model_name = str(model.get("name") or "")
        title = f"{model_id} — {model_name}" if model_name and model_name != model_id else model_id
        markers = []
        if opencode_model_is_free(provider_id, model_id, model):
            markers.append("free")
        if model_id == default_model:
            markers.append("default")
        if markers:
            title += f"  ({', '.join(markers)})"
        model_choices.append(Choice(title=title, value=model_id))
    model_choices.append(Choice(title="back", value="back"))
    selected_default = None
    if current_model in model_ids:
        selected_default = current_model
    elif default_model in model_ids:
        selected_default = default_model
    model_id = questionary.select(
        " > opencode model",
        choices=model_choices,
        default=selected_default,
        pointer=">",
        qmark="",
        style=style,
        use_search_filter=True,
        use_jk_keys=False,
    ).ask()
    if model_id is None or model_id == "back":
        return None
    return str(provider_id), str(model_id)


# Schema version for --json outputs. Wrappers can query it via
# `reverse-api-engineer --json-schema-version`.
AGENT_JSON_SCHEMA_VERSION = 1

# Map of stable usage keys → SDK-specific candidates (first match wins).
# Lets `agent --json` and `engineer --json` emit a stable cost/token shape
# regardless of which SDK (Claude / OpenCode / Copilot) ran underneath.
_STABLE_USAGE_KEYS: dict[str, tuple[str, ...]] = {
    "input_tokens": ("input_tokens",),
    "output_tokens": ("output_tokens",),
    "cache_read_tokens": ("cache_read_input_tokens", "cache_read_tokens"),
    "cache_write_tokens": ("cache_creation_input_tokens", "cache_write_tokens"),
    "total_cost_usd": ("estimated_cost_usd", "total_cost_usd", "total_cost"),
}


def _normalize_usage(raw: dict | None) -> dict:
    """Return a stable subset of usage fields, keeping the SDK-native dict under .raw.

    Wrappers can rely on the top-level keys; per-SDK extras stay under raw.
    """
    if not raw or not isinstance(raw, dict):
        return {}
    out: dict = {}
    for stable_key, candidates in _STABLE_USAGE_KEYS.items():
        for c in candidates:
            if c in raw:
                out[stable_key] = raw[c]
                break
    out["raw"] = raw
    return out


# Machine-readable error categories. Wrappers can react differently to each
# without pattern-matching on the human-readable `error` string.
ERROR_KINDS = (
    "misuse",            # user input invalid / missing required arg
    "config_invalid",    # config file or env var malformed
    "permission_denied", # filesystem / API perm denied
    "network",           # DNS / TCP / TLS / timeout
    "engine_failure",    # SDK or capture engine crashed mid-run
    "interrupted",       # KeyboardInterrupt / SIGINT
    "unknown",           # default fallback
)


def _format_error_message(error: str | BaseException | None) -> str | None:
    """Render an exception or string into a human-readable error message.

    KeyboardInterrupt has no useful str() — we return the conventional
    "interrupted" so downstream wrappers can match on a stable message.
    Empty exception messages fall back to the class name.
    """
    if error is None:
        return None
    if isinstance(error, KeyboardInterrupt):
        return "interrupted"
    if isinstance(error, BaseException):
        return str(error) or type(error).__name__
    return error


def _classify_error(error: str | BaseException | None, *, default: str = "unknown") -> str | None:
    """Map an Exception or human error message to one of the ERROR_KINDS.

    Callers may pass a stronger hint by setting `default` (e.g. `misuse` from
    a CLI argument check, before any exception).
    """
    if error is None:
        return None
    if isinstance(error, BaseException):
        if isinstance(error, KeyboardInterrupt):
            return "interrupted"
        if isinstance(error, PermissionError):
            return "permission_denied"
        if isinstance(error, (ConnectionError, TimeoutError)):
            return "network"
        msg = str(error)
    else:
        msg = error
    low = msg.lower()
    if "permission denied" in low or "errno 13" in low:
        return "permission_denied"
    if "interrupted" in low:
        return "interrupted"
    if "is required" in low or "missing required" in low or "no such option" in low or "in non-interactive" in low:
        return "misuse"
    if any(kw in low for kw in ("connection refused", "timeout", "timed out", "dns", "network", "unreachable", "ssl")):
        return "network"
    if "not found" in low or "no run" in low or "produced no run" in low or "produced no result" in low:
        return "engine_failure"
    return default


@contextmanager
def _quiet_consoles_for_json():
    """Reserve stdout for the final JSON payload; route Rich output to stderr.

    Yields the original stdout file object so the caller can write JSON to it
    after the wrapped block exits cleanly. Rich Console.file is a property that
    lazily resolves to sys.stdout, so we save/restore the underlying _file slot
    rather than the resolved file object.
    """
    real_stdout = sys.stdout
    redirected_consoles: list[tuple[Console, object]] = []
    sys.stdout = sys.stderr
    for mod_name, mod in list(sys.modules.items()):
        if not mod_name.startswith("reverse_api") or mod is None:
            continue
        candidate = getattr(mod, "console", None)
        if isinstance(candidate, Console):
            redirected_consoles.append((candidate, candidate._file))
            candidate.file = sys.stderr
    try:
        yield real_stdout
    finally:
        sys.stdout = real_stdout
        for c, original_inner in redirected_consoles:
            c._file = original_inner


def _write_json_stdout(real_stdout, payload: dict, *, json_stream: bool) -> None:
    """Write final CLI JSON payload (single doc or NDJSON terminal event)."""
    out = {"event": "result", **payload} if json_stream else payload
    real_stdout.write(json.dumps(out) + "\n")
    real_stdout.flush()


def _build_dry_run_payload(
    *,
    prompt: str | None,
    url: str | None,
    model: str | None,
    output_dir: str | None,
    headless: bool,
) -> dict:
    """Validate config / env / deps without launching a browser.

    Returns a payload with the same top-level shape as `_build_agent_payload`
    plus a `checks` array (each item: name, status: ok|warn|error, message)
    and a `would_run` sub-object showing what an actual `agent` invocation
    would do with these inputs. Status is `error` if any check is `error`,
    otherwise `ok`. Misuse errors (missing prompt) get `error_kind=misuse`;
    runtime issues (missing API key, missing node) get `config_invalid`.
    """
    import shutil
    import subprocess

    from .agent_browser import check_agent_browser_runtime

    checks: list[dict] = []
    agent_provider = config_manager.get("agent_provider", "auto")
    global_agent_browser = shutil.which("agent-browser")

    # 1. Prompt
    if not prompt or not prompt.strip():
        checks.append({"name": "prompt", "status": "error", "message": "--prompt is required"})
    else:
        checks.append({"name": "prompt", "status": "ok", "message": f"{len(prompt)} chars"})

    # 2. URL (optional, but if given it must look reasonable)
    if url:
        if url.startswith("http://") or url.startswith("https://"):
            checks.append({"name": "url", "status": "ok", "message": url})
        else:
            checks.append({
                "name": "url",
                "status": "error",
                "message": f"url must start with http:// or https://, got {url!r}",
            })
    else:
        checks.append({"name": "url", "status": "ok", "message": "(none — agent will pick a start)"})

    # 3. Agent provider
    if agent_provider in ("auto", "chrome-mcp", "agent-browser"):
        checks.append({"name": "agent_provider", "status": "ok", "message": agent_provider})
    else:
        checks.append({
            "name": "agent_provider",
            "status": "error",
            "message": f"unknown agent_provider {agent_provider!r}; expected 'auto', 'chrome-mcp', or 'agent-browser'",
        })

    # 4. SDK + API key presence (we only check env var existence, not validity)
    sdk = config_manager.get("sdk", "claude")
    sdk_env_var = {
        "claude": "ANTHROPIC_API_KEY",
        "opencode": "OPENCODE_API_KEY",
        "copilot": "GITHUB_COPILOT_TOKEN",
        "cursor": "CURSOR_API_KEY",
    }.get(sdk)
    if sdk_env_var is None:
        checks.append({
            "name": "sdk",
            "status": "error",
            "message": f"unknown sdk {sdk!r}; expected 'claude', 'opencode', 'copilot', or 'cursor'",
        })
    elif not os.environ.get(sdk_env_var):
        checks.append({
            "name": f"sdk:{sdk}",
            "status": "warn",
            "message": f"{sdk_env_var} not set in env (the SDK may still resolve auth via a config file)",
        })
    else:
        checks.append({"name": f"sdk:{sdk}", "status": "ok", "message": f"{sdk_env_var} present"})

    # 5. Node.js + npx — MCP providers need both; agent-browser with a global binary does not.
    node = shutil.which("node")
    needs_node_for_browser = agent_provider != "agent-browser" or global_agent_browser is None
    if node is None:
        if needs_node_for_browser:
            checks.append({
                "name": "node",
                "status": "error",
                "message": "node not found in PATH; required for agent-mode browser tooling "
                "(MCP browser servers plus Vercel agent-browser install/bootstrap)",
            })
        else:
            checks.append({
                "name": "node",
                "status": "ok",
                "message": "not on PATH (optional while global `agent-browser` is installed)",
            })
    else:
        try:
            ver = subprocess.run(
                [node, "--version"], capture_output=True, text=True, timeout=5
            ).stdout.strip()
            checks.append({"name": "node", "status": "ok", "message": ver})
        except Exception as e:
            checks.append({"name": "node", "status": "warn", "message": f"could not query version: {e}"})

    npx = shutil.which("npx")
    needs_npx_for_browser = agent_provider in ("auto", "chrome-mcp") or (
        agent_provider == "agent-browser" and global_agent_browser is None
    )
    if npx is None:
        if needs_npx_for_browser:
            checks.append({
                "name": "npx",
                "status": "error",
                "message": "npx not found in PATH; required so npm can spawn MCP helpers and "
                "fetch/run the pinned agent-browser CLI when no global binary is present",
            })
        else:
            checks.append({
                "name": "npx",
                "status": "ok",
                "message": "not on PATH (optional while global `agent-browser` is installed)",
            })
    else:
        checks.append({"name": "npx", "status": "ok", "message": npx})

    # 6. Headed chrome-mcp requires the user has a real Chrome with auto-connect
    if agent_provider == "chrome-mcp" and not headless:
        checks.append({
            "name": "chrome-mcp:auto-connect",
            "status": "warn",
            "message": "chrome-mcp without --headless requires Chrome 146+ with auto-connect enabled at chrome://inspect/#remote-debugging — this is not auto-checkable",
        })

    # 7. agent-browser CLI: read-only validation (no npm install during dry-run).
    if agent_provider == "agent-browser":
        ab_setup = check_agent_browser_runtime()
        parts: list[str] = []
        if ab_setup.error:
            parts.append(ab_setup.error)
        elif ab_setup.ok:
            parts.append("`agent-browser` CLI reachable (`--help` OK)")
        if ab_setup.notices:
            parts.extend(ab_setup.notices)
        checks.append({
            "name": "agent-browser:cli",
            "status": "error" if not ab_setup.ok else "ok",
            "message": " | ".join(parts) if parts else "configured",
        })

    # 8. Output dir writability — probe with a unique filename so we never
    # clobber a real user file (a fixed name like `.dry_run_write_probe`
    # could legitimately exist in someone's output dir).
    import secrets

    base = Path(output_dir or config_manager.get("output_dir") or "~/.reverse-api/runs").expanduser()
    try:
        base.mkdir(parents=True, exist_ok=True)
        probe = base / f".rae_dry_run_probe_{os.getpid()}_{secrets.token_hex(4)}"
        # If somehow this exact filename already exists, refuse to touch it.
        if probe.exists():
            raise FileExistsError(f"unique probe path collision: {probe}")
        probe.write_text("")
        probe.unlink()
        checks.append({"name": "output_dir", "status": "ok", "message": str(base)})
    except Exception as e:
        checks.append({
            "name": "output_dir",
            "status": "error",
            "message": f"{base}: {e}",
        })

    # Aggregate
    has_error = any(c["status"] == "error" for c in checks)
    final_error = None
    error_kind = None
    if has_error:
        first_err = next(c for c in checks if c["status"] == "error")
        final_error = f"{first_err['name']}: {first_err['message']}"
        # Misuse for prompt/url; config_invalid otherwise
        error_kind = "misuse" if first_err["name"] in ("prompt", "url") else "config_invalid"

    # `would_run.model` resolution mirrors the live capture path: each SDK
    # has its own model config key, so picking `claude_code_model` for an
    # opencode/copilot session would misreport what would actually run.
    sdk_model_key = {
        "claude": "claude_code_model",
        "opencode": "opencode_model",
        "copilot": "copilot_model",
        "cursor": "cursor_model",
    }.get(sdk, "claude_code_model")
    sdk_default_model = {
        "claude": "claude-sonnet-4-6",
        "opencode": "claude-opus-4-6",
        "copilot": "gpt-5",
        "cursor": "composer-2.5",
    }.get(sdk, "claude-sonnet-4-6")
    resolved_model = model or config_manager.get(sdk_model_key, sdk_default_model)

    return {
        "schema_version": AGENT_JSON_SCHEMA_VERSION,
        "status": "error" if has_error else "ok",
        "run_id": None,
        "prompt": prompt,
        "url": url,
        "mode": "dry-run",
        "har_path": None,
        "script_path": None,
        "usage": {},
        "error": final_error,
        "error_kind": error_kind,
        "would_run": {
            "agent_provider": agent_provider,
            "sdk": sdk,
            "model": resolved_model,
            "output_dir": str(base),
            "headless": headless,
        },
        "checks": checks,
    }


def _build_agent_payload(
    result: dict | None,
    *,
    prompt: str | None,
    url: str | None,
    output_dir: str | None = None,
    error: str | BaseException | None = None,
    error_kind_hint: str = "unknown",
) -> dict:
    """Normalize an agent capture result into a stable JSON shape.

    `output_dir` must match the value passed to the underlying capture so the
    HAR path is resolved against the user's chosen run root, not the default.
    """
    result = result or {}
    run_id = result.get("run_id")
    inner_error = result.get("error")
    final_error_obj = error if error is not None else inner_error
    if final_error_obj is None and not run_id:
        final_error_obj = "agent capture produced no run"
    error_str = _format_error_message(final_error_obj)
    error_kind = _classify_error(final_error_obj, default=error_kind_hint) if final_error_obj else None
    har_path = None
    if run_id:
        candidate = get_har_dir(run_id, output_dir) / "recording.har"
        har_path = str(candidate) if candidate.exists() else None
    return {
        "schema_version": AGENT_JSON_SCHEMA_VERSION,
        "status": "error" if error_str else "ok",
        "run_id": run_id,
        "prompt": prompt,
        "url": url,
        "mode": result.get("mode"),
        "har_path": har_path,
        "script_path": result.get("script_path"),
        "usage": _normalize_usage(result.get("usage")),
        "error": error_str,
        "error_kind": error_kind,
    }


def _build_engineer_payload(
    result: dict | None,
    *,
    run_id: str,
    prompt: str | None,
    fresh: bool,
    error: str | BaseException | None = None,
    error_kind_hint: str = "unknown",
) -> dict:
    """Normalize an engineer-mode result into a stable JSON shape.

    Mirrors `_build_agent_payload`'s contract minus the agent-specific fields
    (no `url`, no `mode`, no `har_path`). `prompt` is the value the user passed
    to --prompt (which may have been used as either a full replacement or as
    additional instructions depending on --fresh).
    """
    result = result if isinstance(result, dict) else {}
    inner_error = result.get("error")
    final_error_obj = error if error is not None else inner_error
    if final_error_obj is None and not result:
        final_error_obj = "engineering produced no result"
    error_str = _format_error_message(final_error_obj)
    error_kind = _classify_error(final_error_obj, default=error_kind_hint) if final_error_obj else None
    return {
        "schema_version": AGENT_JSON_SCHEMA_VERSION,
        "status": "error" if error_str else "ok",
        "run_id": run_id,
        "prompt": prompt,
        "fresh": fresh,
        "script_path": result.get("script_path"),
        "usage": _normalize_usage(result.get("usage")),
        "error": error_str,
        "error_kind": error_kind,
    }


def _build_run_payload(
    *,
    identifier: str,
    run_id: str | None = None,
    script_path: str | None = None,
    script_args: tuple[str, ...] | list[str] = (),
    returncode: int | None = None,
    stdout: str | None = None,
    stderr: str | None = None,
    scripts: list[Path] | None = None,
    error: str | BaseException | None = None,
    error_kind_hint: str = "unknown",
) -> dict:
    """Normalize `run --json` output into a stable machine-readable shape."""
    error_str = _format_error_message(error)
    if error_str is None and returncode not in (None, 0):
        error_str = f"script exited with code {returncode}"
    error_kind = _classify_error(error, default=error_kind_hint) if error_str else None
    if error_str and error is None:
        error_kind = error_kind_hint
    return {
        "schema_version": AGENT_JSON_SCHEMA_VERSION,
        "status": "error" if error_str else "ok",
        "identifier": identifier,
        "run_id": run_id,
        "script_path": script_path,
        "script_args": list(script_args),
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "scripts": [
            {
                "name": p.name,
                "path": str(p),
                "size": p.stat().st_size if p.exists() else None,
                "modified": p.stat().st_mtime if p.exists() else None,
            }
            for p in (scripts or [])
        ],
        "error": error_str,
        "error_kind": error_kind,
    }


def _write_json_event(real_stdout, payload: dict) -> None:
    real_stdout.write(json.dumps(payload) + "\n")
    real_stdout.flush()


# Mode definitions
MODES = ["agent", "manual", "engineer", "collector"]
MODE_DESCRIPTIONS = {
    "manual": "full pipeline",
    "engineer": "reverse engineer only",
    "agent": "autonomous agent + capture",
    "collector": "ai-powered data collection",
}

AGENT_TASK_SUGGESTIONS = [
    "Go to github.com/trending and capture the top 10 trending repos' API calls",
    "Navigate to news.ycombinator.com, browse the front page and capture API interactions",
    "Go to weather.com, search for New York weather and capture the forecast API",
    "Visit reddit.com/r/programming, browse posts and capture the Reddit API calls",
    "Go to maps.google.com, search for restaurants near Times Square and capture API calls",
    "Navigate to twitter.com/explore and capture trending topics API interactions",
    "Go to amazon.com, search for 'mechanical keyboard' and capture product search API",
    "Visit spotify.com/search, search for an artist and capture the search API",
    "Navigate to stackoverflow.com, search for 'python async' and capture the search API",
    "Go to npmjs.com, search for 'express' and capture the package registry API",
    "Visit producthunt.com and capture the feed/listing API calls",
    "Go to crunchbase.com and browse company profiles to capture their API",
    "Navigate to linkedin.com/jobs, search for 'software engineer' and capture job search API",
    "Go to airbnb.com, search for stays in Paris and capture the listing search API",
    "Visit imdb.com, search for a movie and capture the title/search API calls",
    "Go to wolframalpha.com, run a query and capture the computation API",
    "Navigate to booking.com, search for hotels in Tokyo and capture the search API",
    "Go to zillow.com, search for homes in San Francisco and capture the listing API",
    "Visit translate.google.com, translate a paragraph and capture the translation API",
    "Go to unsplash.com, search for 'mountains' and capture the photo search API",
]


def prompt_interactive_options(
    prompt: str | None = None,
    url: str | None = None,
    reverse_engineer: bool | None = None,
    model: str | None = None,
    current_mode: str = "agent",
) -> dict:
    """Prompt user for essential options interactively (Browgents style).

    Shift+Tab cycles through modes: manual ↔ engineer ↔ agent
    """

    # Slash command completer
    commands = [
        "/settings",
        "/history",
        "/messages",
        "/cloud",
        "/help",
        "/exit",
        "/quit",
        "/commands",
    ]

    class EnhancedCompleter(Completer):
        """Autocomplete for slash commands and run IDs."""

        def get_completions(self, document, complete_event):
            text = document.text_before_cursor

            # Slash command completion
            if text.startswith("/"):
                # Check if we're after /messages command
                if text.startswith("/messages "):
                    # Run ID completion for /messages
                    run_id_prefix = text[10:]  # Everything after "/messages "
                    for run_id in self._get_run_ids():
                        if run_id.startswith(run_id_prefix):
                            yield Completion(
                                run_id,
                                start_position=-len(run_id_prefix),
                                display_meta=self._get_run_meta(run_id),
                            )
                elif " " not in text:
                    # Regular slash command completion (no space yet)
                    for cmd in commands:
                        if cmd.startswith(text):
                            yield Completion(cmd, start_position=-len(text))
            # Run-id completion in engineer mode
            elif mode_state["mode"] == "engineer" and text:
                for run_id in self._get_run_ids():
                    if run_id.startswith(text):
                        yield Completion(
                            run_id,
                            start_position=-len(text),
                            display_meta=self._get_run_meta(run_id),
                        )

        def _get_run_ids(self):
            """Get all run IDs from history (newest first)."""
            try:
                history = session_manager.get_history(limit=50)
                return [run["run_id"] for run in history]
            except Exception:
                return []

        def _get_run_meta(self, run_id):
            """Get metadata for a run ID (timestamp + prompt snippet)."""
            try:
                run = session_manager.get_run(run_id)
                if run:
                    timestamp = run.get("timestamp", "")[:16]  # YYYY-MM-DD HH:MM
                    prompt = run.get("prompt", "")[:30]
                    return f"[{timestamp}] {prompt}"
            except Exception:
                pass
            return ""

    command_completer = EnhancedCompleter()

    # Track mode state (mutable container for closure)
    mode_state = {"mode": current_mode, "mode_index": MODES.index(current_mode)}

    # Create key bindings for mode cycling and autocomplete
    kb = KeyBindings()

    @kb.add("s-tab")  # Shift+Tab
    def cycle_mode(event):
        """Cycle to next mode."""
        mode_state["mode_index"] = (mode_state["mode_index"] + 1) % len(MODES)
        mode_state["mode"] = MODES[mode_state["mode_index"]]
        # Force prompt refresh by invalidating the app
        event.app.invalidate()

    @kb.add("right")  # Right arrow
    def accept_completion(event):
        """Accept the current autocomplete suggestion with right arrow."""
        buff = event.app.current_buffer
        if buff.complete_state:
            # Save the current completion before closing
            completion = buff.complete_state.current_completion
            if completion:
                buff.apply_completion(completion)
            else:
                # No completion selected, just move cursor right
                buff.cursor_right()
        else:
            # If no completion, just move cursor right
            buff.cursor_right()

    @kb.add("c-r")  # Ctrl+R: random task suggestion (agent mode)
    def random_suggestion(event):
        """Fill prompt with a random task suggestion for agent mode."""
        if mode_state["mode"] == "agent":
            suggestion = random.choice(AGENT_TASK_SUGGESTIONS)
            buff = event.app.current_buffer
            buff.text = suggestion
            buff.cursor_position = len(suggestion)

    def get_prompt():
        """Generate prompt with current mode indicator."""
        mode = mode_state["mode"]
        mode_color = MODE_COLORS.get(mode, THEME_PRIMARY)

        return HTML(f'<style fg="{mode_color}">[{mode}]</style> <style fg="{mode_color}" bold="true">&gt;</style> ')

    if prompt is None:
        pt_style = PtStyle.from_dict(
            {
                "prompt": f"{THEME_PRIMARY} bold",
                "": THEME_SECONDARY,
            }
        )

        session = PromptSession(
            message=get_prompt,  # Dynamic prompt function
            completer=command_completer,
            auto_suggest=AutoSuggestFromHistory(),
            complete_while_typing=True,
            style=pt_style,
            key_bindings=kb,
        )

        prompt = session.prompt()

    if prompt is None:  # Handle Ctrl+D or Ctrl+C if not caught
        raise click.Abort()

    prompt = prompt.strip()
    if not prompt:
        return {"command": "/empty", "mode": mode_state["mode"]}

    if prompt.startswith("/"):
        return {"command": prompt.lower(), "mode": mode_state["mode"]}

    # Return mode in all cases
    result_mode = mode_state["mode"]

    # Engineer mode: prompt is the run_id
    if result_mode == "engineer":
        _sdk = config_manager.get("sdk", "claude")
        resolved = model or default_model_for_configured_sdk(_sdk)
        return {
            "mode": result_mode,
            "run_id": prompt,
            "model": resolved,
        }

    # Agent mode: autonomous browser, no URL needed (agent navigates on its own)
    if result_mode == "agent":
        if model is None:
            _sdk = config_manager.get("sdk", "claude")
            model = default_model_for_configured_sdk(_sdk)

        mode_color = MODE_COLORS.get("agent", THEME_PRIMARY)
        console = Console()
        console.print(f"  [{mode_color}]autonomous[/{mode_color}] [dim]agent will navigate on its own[/dim]")

        return {
            "mode": result_mode,
            "prompt": prompt,
            "url": url if url else None,
            "reverse_engineer": False,  # Agent mode doesn't auto-reverse engineer
            "model": model,
        }

    # Collector mode: just needs prompt
    if result_mode == "collector":
        if model is None:
            model = config_manager.get("collector_model", "claude-sonnet-4-6")

        return {
            "mode": result_mode,
            "prompt": prompt,
            "model": model,
        }

    # Manual mode: need URL
    if url is None:
        try:
            url = questionary.text(
                " > url",
                instruction="(Enter for none)",
                qmark="",
                style=questionary.Style(
                    [
                        ("question", f"fg:{THEME_SECONDARY}"),
                        ("instruction", f"fg:{THEME_DIM} italic"),
                    ]
                ),
            ).ask()
            if url is None:  # questionary returns None on Ctrl+C
                raise click.Abort()
        except KeyboardInterrupt:
            raise click.Abort()

    # Use settings defaults for the rest
    if reverse_engineer is None:
        reverse_engineer = True

    if model is None:
        _sdk = config_manager.get("sdk", "claude")
        model = default_model_for_configured_sdk(_sdk)

    return {
        "mode": result_mode,
        "prompt": prompt,
        "url": url if url else None,
        "reverse_engineer": reverse_engineer,
        "model": model,
    }


CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@click.group(invoke_without_command=True, context_settings=CONTEXT_SETTINGS)
@click.pass_context
@click.version_option(version=__version__)
@click.option(
    "--json-schema-version",
    "show_schema_version",
    is_flag=True,
    help="Print the agent/engineer JSON schema_version this binary emits and exit.",
)
def main(ctx: click.Context, show_schema_version: bool):
    """reverse-api-engineer: reverse engineer apis.

    Run without a subcommand to start the interactive REPL; use agent, manual,
    engineer, or collector mode interactively.

    Scripted flags are subcommand-specific: agent, engineer, and run support
    --json, --json-stream, and --no-interactive; list/show support --json.
    See `<cmd> --help` for details. Wrappers that need to gate on the payload
    schema can call `reverse-api-engineer
    --json-schema-version`.
    """
    if show_schema_version:
        click.echo(str(AGENT_JSON_SCHEMA_VERSION))
        ctx.exit(0)

    if ctx.invoked_subcommand is None:
        # Refuse to drop into the prompt_toolkit REPL when stdin is not a TTY:
        # without an interactive terminal the REPL would block on stdin
        # forever (e.g. CI invocations, agent wrappers that forgot the
        # subcommand). Print --help to stderr and exit 2 (misuse).
        if not sys.stdin.isatty():
            click.echo(ctx.get_help(), err=True)
            click.echo(
                "\nerror: no subcommand given and stdin is not a TTY; "
                "the interactive REPL requires a terminal.",
                err=True,
            )
            sys.exit(2)
        repl_loop()


def repl_loop():
    """Main interactive loop for the CLI."""
    from concurrent.futures import ThreadPoolExecutor

    # Start update check in background to avoid blocking startup
    update_executor = ThreadPoolExecutor(max_workers=1)
    update_future = update_executor.submit(check_for_updates)

    # Get current SDK and model from config
    sdk = config_manager.get("sdk", "claude")
    model = default_model_for_configured_sdk(sdk)

    display_banner(console, sdk=sdk, model=model)
    console.print("  [dim]shift+tab to cycle modes | ctrl+r for random task (agent)[/dim]")
    display_footer(console)

    # Show update message if background check has completed
    try:
        update_msg = update_future.result(timeout=0.5)
        if update_msg:
            console.print(f"  [yellow]{update_msg}[/yellow]")
            console.print()
    except Exception:
        pass  # Timed out or failed — don't block startup
    finally:
        update_executor.shutdown(wait=False)

    current_mode = "agent"

    while True:
        try:
            options = prompt_interactive_options(current_mode=current_mode)

            # Update current mode for next iteration
            current_mode = options.get("mode", "agent")

            if "command" in options:
                cmd = options["command"]
                mode_color = MODE_COLORS.get(current_mode, THEME_PRIMARY)

                if cmd == "/empty":
                    continue
                if cmd == "/exit" or cmd == "/quit":
                    return  # Exit the loop and return to main
                elif cmd == "/settings":
                    handle_settings(mode_color)
                elif cmd == "/history":
                    handle_history(mode_color)
                elif cmd == "/cloud":
                    _print_cloud_overview()
                elif cmd == "/help" or cmd == "/commands":
                    handle_help(mode_color)
                elif cmd.startswith("/messages"):
                    parts = cmd.split(maxsplit=1)
                    if len(parts) > 1:
                        handle_messages(parts[1].strip(), mode_color)
                    else:
                        console.print(" [red]usage:[/red] /messages <run_id>")
                else:
                    # Unknown command - show error and available commands
                    console.print(f" [red]Unknown command:[/red] {cmd}")
                    console.print(" [dim]Available commands: /settings, /history, /messages, /cloud, /help, /commands, /exit[/dim]")
                continue

            mode = options.get("mode", "agent")

            # Handle different modes
            if mode == "engineer":
                raw_input = options.get("run_id")

                if not raw_input:
                    console.print(" [dim]Usage:[/dim] <run_id> (switch context)")
                    console.print(" [dim]       [/dim] <prompt> (re-engineer the latest run)")
                    continue

                # Two cases: input matches a known run_id (switch context) or
                # it's free text (additive instructions on the latest run).
                if session_manager.get_run(raw_input):
                    target_run_id = raw_input
                    add_instr = None
                else:
                    latest = session_manager.get_history(limit=1)
                    if not latest:
                        console.print(" [red]error:[/red] no runs found in history")
                        continue
                    target_run_id = latest[0]["run_id"]
                    add_instr = raw_input

                run_engineer(
                    target_run_id,
                    model=options.get("model"),
                    additional_instructions=add_instr,
                )
                continue

            if mode == "agent":
                # Agent mode: run autonomous browser agent
                run_agent_capture(
                    prompt=options["prompt"],
                    url=options.get("url"),
                    model=options.get("model"),
                )
                continue

            if mode == "collector":
                # Collector mode: AI-powered data collection
                run_collector(
                    prompt=options["prompt"],
                    model=options.get("model"),
                )
                continue

            # Manual mode: run browser capture
            run_manual_capture(
                prompt=options["prompt"],
                url=options["url"],
                reverse_engineer=options["reverse_engineer"],
                model=options["model"],
            )

        except (click.Abort, KeyboardInterrupt):
            console.print("\n [dim]terminated[/dim]")
            return
        except Exception as e:
            console.print(f" [red]error:[/red] {escape(str(e))}")
            console.print(f" [dim]{ERROR_CTA}[/dim]")


def handle_settings(mode_color=THEME_PRIMARY):
    """Keep the settings menu open until the user explicitly goes back."""
    while _handle_settings_action(mode_color):
        pass


def _handle_settings_action(mode_color=THEME_PRIMARY) -> bool:
    """Display and manage settings with improved layout and descriptions."""
    from rich.table import Table

    console.print()

    # Create a table for current configuration
    config_table = Table(show_header=False, box=None, padding=(0, 1))
    config_table.add_column(style="dim", justify="left")
    config_table.add_column(style=mode_color, justify="left")

    # Sort config items alphabetically by key
    for k, v in sorted(config_manager.config.items()):
        display_val = str(v) if v is not None else "default"
        # Make the key more readable
        key_display = k.replace("_", " ").title()
        config_table.add_row(key_display, display_val)

    # Display in a clean format
    console.print(" [bold white]Settings[/bold white] [dim]Current Configuration[/dim]")
    console.print(config_table)
    console.print()

    # Settings menu (sorted alphabetically)
    choices = [
        Choice(title="Agent Provider", value="agent_provider"),
        Choice(title="Claude Code Model", value="claude_code_model"),
        Choice(title="Cloud Suggestions", value="cloud_suggestions"),
        Choice(title="Copilot Model", value="copilot_model"),
        Choice(title="Cursor Model", value="cursor_model"),
        Choice(title="Cursor Web Search", value="cursor_web_search"),
        Choice(title="OpenCode Provider / Model", value="opencode_pair"),
        Choice(title="Output Directory", value="output_dir"),
        Choice(title="Output Language", value="output_language"),
        Choice(title="Real-time Sync", value="real_time_sync"),
        Choice(title="SDK", value="sdk"),
        Choice(title="Back", value="back"),
    ]

    action = questionary.select(
        "    ",  # Add padding via the question prompt
        choices=choices,
        pointer=">",
        qmark="",
        style=questionary.Style(
            [
                ("pointer", f"fg:{mode_color} bold"),
                ("highlighted", f"fg:{mode_color} bold"),
                ("selected", "fg:white"),
                ("question", ""),  # Hide the question text styling
            ]
        ),
    ).ask()

    if action is None or action == "back":
        return False  # Exit settings to main prompt

    if action == "claude_code_model":
        model_choices = [Choice(title=c["name"].lower(), value=c["value"]) for c in get_model_choices()]
        model_choices.append(Choice(title="back", value="back"))
        model = questionary.select(
            "",
            choices=model_choices,
            pointer=">",
            qmark="",
            style=questionary.Style(
                [
                    ("pointer", f"fg:{mode_color} bold"),
                    ("highlighted", f"fg:{mode_color} bold"),
                ]
            ),
        ).ask()
        if model and model != "back":
            config_manager.set("claude_code_model", model)
            console.print(f" [dim]updated[/dim] {model}\n")

    elif action == "sdk":
        sdk_choices = [
            Choice(title="claude", value="claude"),
            Choice(title="copilot", value="copilot"),
            Choice(title="cursor", value="cursor"),
            Choice(title="opencode", value="opencode"),
            Choice(title="back", value="back"),
        ]
        sdk = questionary.select(
            "",
            choices=sdk_choices,
            pointer=">",
            qmark="",
            style=questionary.Style(
                [
                    ("pointer", f"fg:{mode_color} bold"),
                    ("highlighted", f"fg:{mode_color} bold"),
                ]
            ),
        ).ask()
        if sdk and sdk != "back":
            config_manager.set("sdk", sdk)
            console.print(f" [dim]updated[/dim] sdk: {sdk}\n")

    elif action == "output_language":
        lang_choices = [
            Choice(title="python", value="python"),
            Choice(title="javascript", value="javascript"),
            Choice(title="typescript", value="typescript"),
            Choice(title="go", value="go"),
            Choice(title="java", value="java"),
            Choice(title="csharp", value="csharp"),
            Choice(title="php", value="php"),
            Choice(title="ruby", value="ruby"),
            Choice(title="c", value="c"),
            Choice(title="back", value="back"),
        ]
        lang = questionary.select(
            "",
            choices=lang_choices,
            pointer=">",
            qmark="",
            style=questionary.Style(
                [
                    ("pointer", f"fg:{mode_color} bold"),
                    ("highlighted", f"fg:{mode_color} bold"),
                ]
            ),
        ).ask()
        if lang and lang != "back":
            config_manager.set("output_language", lang)
            console.print(f" [dim]updated[/dim] output language: {lang}\n")

    elif action == "agent_provider":
        provider_choices = [
            Choice(title="auto (Playwright MCP)", value="auto"),
            Choice(title="chrome-mcp (Chrome DevTools MCP)", value="chrome-mcp"),
            Choice(title="agent-browser (Vercel CLI via shell/Bash)", value="agent-browser"),
            Choice(title="back", value="back"),
        ]
        provider = questionary.select(
            "",
            choices=provider_choices,
            pointer=">",
            qmark="",
            style=questionary.Style(
                [
                    ("pointer", f"fg:{mode_color} bold"),
                    ("highlighted", f"fg:{mode_color} bold"),
                ]
            ),
        ).ask()
        if provider and provider != "back":
            config_manager.set("agent_provider", provider)
            console.print(f" [dim]updated[/dim] agent provider: {provider}")
            if provider == "agent-browser":
                console.print()
                console.print(
                    " [dim]Browsing runs through Vercel's agent-browser CLI (not an MCP shim).[/dim]"
                )
                console.print(
                    " [dim]On first agent run RAE installs the CLI with `npm install -g <pin>` when "
                    "`agent-browser` is missing (you’ll see a banner), then reuses the global shim.[/dim]"
                )
                console.print(
                    " [dim]Pin via `agent_browser_npx_package` in config or `RAE_AGENT_BROWSER_PACKAGE` env.[/dim]"
                )
                console.print(
                    " [dim]Extra operator hints (cloud backends, corp proxy…): "
                    "`agent_browser_notes` or `RAE_AGENT_BROWSER_NOTES`.[/dim]"
                )
                console.print(
                    " [dim]Chrome download: `agent-browser install` once (add `--with-deps` on Linux).[/dim]"
                )
                console.print()
            elif provider == "chrome-mcp":
                console.print()
                console.print(" [dim]chrome devtools mcp setup:[/dim]")
                console.print(" [dim] 1. open chrome (version 146 or newer)[/dim]")
                console.print(" [dim] 2. go to chrome://inspect/#remote-debugging[/dim]")
                console.print(' [dim] 3. click "Enable auto-connect"[/dim]')
                console.print(" [dim] 4. node.js v20.19+ required[/dim]")
                console.print()
                console.print(" [dim]the agent will connect to your real chrome browser.[/dim]")
                console.print(" [dim]existing sessions, cookies, and auth will be available.[/dim]")
                console.print(" [dim]avoid browsing sensitive sites while the agent is active.[/dim]")
            console.print()

    elif action == "opencode_pair":
        pair = _select_opencode_pair_for_settings(mode_color)
        if pair is not None:
            provider_id, model_id = pair
            config_manager.update({"opencode_provider": provider_id, "opencode_model": model_id})
            console.print(f" [dim]updated[/dim] opencode: {provider_id}/{model_id}\n")

    elif action == "copilot_model":
        current = config_manager.get("copilot_model", "gpt-5")
        new_model = questionary.text(
            " > copilot model",
            default=current or "gpt-5",
            instruction="(e.g., 'gpt-5', 'gpt-4.1')",
            qmark="",
            style=questionary.Style(
                [
                    ("question", f"fg:{THEME_SECONDARY}"),
                    ("instruction", f"fg:{THEME_DIM} italic"),
                ]
            ),
        ).ask()
        if new_model is not None:
            new_model = new_model.strip()
            if not new_model:
                console.print(" [yellow]error:[/yellow] copilot model cannot be empty\n")
            else:
                config_manager.set("copilot_model", new_model)
                console.print(f" [dim]updated[/dim] copilot model: {new_model}\n")

    elif action == "cursor_model":
        current = config_manager.get("cursor_model", "composer-2.5")
        new_model = questionary.text(
            " > cursor model",
            default=current or "composer-2.5",
            instruction="(e.g., 'composer-2.5', 'composer-2' — see Cursor SDK docs)",
            qmark="",
            style=questionary.Style(
                [
                    ("question", f"fg:{THEME_SECONDARY}"),
                    ("instruction", f"fg:{THEME_DIM} italic"),
                ]
            ),
        ).ask()
        if new_model is not None:
            new_model = new_model.strip()
            if not new_model:
                console.print(" [yellow]error:[/yellow] cursor model cannot be empty\n")
            else:
                config_manager.set("cursor_model", new_model)
                console.print(f" [dim]updated[/dim] cursor model: {new_model}\n")

    elif action == "cursor_web_search":
        pick = questionary.select(
            "",
            choices=[
                Choice(title="On — WebFetch/WebSearch + plugins/team settings", value=True),
                Choice(title="Off — project + user Cursor settings only", value=False),
                Choice(title="back", value="back"),
            ],
            pointer=">",
            qmark="",
            style=questionary.Style(
                [
                    ("pointer", f"fg:{mode_color} bold"),
                    ("highlighted", f"fg:{mode_color} bold"),
                ]
            ),
        ).ask()
        if pick is not None and pick != "back":
            config_manager.set("cursor_web_search", pick)
            console.print(f" [dim]updated[/dim] cursor web search: {'on' if pick else 'off'}\n")

    elif action == "cloud_suggestions":
        console.print(
            "    [dim]Before a capture, check whether anything.notte.cc already hosts a\n"
            "    function for that site. Public lookup, no account. RAE_NO_CLOUD=1\n"
            "    overrides this setting.[/dim]\n"
        )
        cloud_choices = [
            Choice(title="Enabled", value=True),
            Choice(title="Disabled", value=False),
            Choice(title="Back", value="back"),
        ]
        choice = questionary.select(
            "",
            choices=cloud_choices,
            pointer=">",
            qmark="",
            style=questionary.Style(
                [
                    ("pointer", f"fg:{mode_color} bold"),
                    ("highlighted", f"fg:{mode_color} bold"),
                ]
            ),
        ).ask()
        if choice is not None and choice != "back":
            config_manager.set("cloud_suggestions", choice)
            status = "enabled" if choice else "disabled"
            console.print(f"    [dim]updated[/dim] cloud suggestions: {status}\n")

    elif action == "real_time_sync":
        current = config_manager.get("real_time_sync", True)
        sync_choices = [
            Choice(title="Enabled", value=True),
            Choice(title="Disabled", value=False),
            Choice(title="Back", value="back"),
        ]
        sync = questionary.select(
            "",
            choices=sync_choices,
            pointer=">",
            qmark="",
            style=questionary.Style(
                [
                    ("pointer", f"fg:{mode_color} bold"),
                    ("highlighted", f"fg:{mode_color} bold"),
                ]
            ),
        ).ask()
        if sync is not None and sync != "back":
            config_manager.set("real_time_sync", sync)
            status = "enabled" if sync else "disabled"
            console.print(f"    [dim]updated[/dim] real-time sync: {status}\n")

    elif action == "output_dir":
        current = config_manager.get("output_dir")
        new_dir = questionary.text(
            " > output directory",
            default=current or "",
            instruction="(Enter for default ~/.reverse-api/runs)",
            qmark="",
            style=questionary.Style(
                [
                    ("question", f"fg:{THEME_SECONDARY}"),
                    ("instruction", f"fg:{THEME_DIM} italic"),
                ]
            ),
        ).ask()
        if new_dir is not None:
            config_manager.set("output_dir", new_dir if new_dir.strip() else None)
            console.print(" [dim]updated[/dim] output directory\n")

    return True


def handle_history(mode_color=THEME_PRIMARY):
    """Display history of runs."""
    history = session_manager.get_history(limit=15)
    if not history:
        console.print(" [dim]> no logs found[/dim]")
        return

    choices = []
    for run in history:
        cost = run.get("usage", {}).get("estimated_cost_usd", 0)
        cost_str = f"${cost:.3f}" if cost > 0 else "-"
        title = f"{run['run_id']:12}  {run['prompt'][:40]:40}  {cost_str:>8}"
        choices.append(Choice(title=title, value=run["run_id"]))

    choices.append(Choice(title="back", value="back"))

    run_id = questionary.select(
        "",
        choices=choices,
        pointer=">",
        qmark="",
        style=questionary.Style(
            [
                ("pointer", f"fg:{mode_color} bold"),
                ("highlighted", f"fg:{mode_color} bold"),
                ("selected", "fg:white"),
            ]
        ),
    ).ask()

    if not run_id or run_id == "back":
        return

    run = session_manager.get_run(run_id)
    if run:
        from rich.table import Table

        # Create a formatted display of the run details
        details_table = Table(show_header=False, box=None, padding=(0, 1))
        details_table.add_column(style="dim", justify="left", width=20)
        details_table.add_column(style="white", justify="left")

        details_table.add_row("Run ID", run.get("run_id", "-"))
        details_table.add_row("Timestamp", run.get("timestamp", "-"))
        details_table.add_row("Prompt", run.get("prompt", "-"))
        details_table.add_row("Model", run.get("model", "-"))
        details_table.add_row("Mode", run.get("mode", "-"))

        usage = run.get("usage", {})
        if usage:
            cost = usage.get("estimated_cost_usd", 0)
            details_table.add_row("Cost", f"${cost:.4f}" if cost > 0 else "-")
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            if input_tokens or output_tokens:
                details_table.add_row("Tokens", f"{input_tokens:,} in / {output_tokens:,} out")

        console.print()
        console.print(" [bold white]Run Details[/bold white]")
        console.print(details_table)
        console.print()

        if questionary.confirm(" > recode?", qmark="").ask():
            model = run.get("model") or config_manager.get("claude_code_model", "claude-sonnet-4-6")
            run_engineer(run_id, model=model)
    else:
        console.print(" [dim]> not found[/dim]")


def handle_help(mode_color=THEME_PRIMARY):
    """Show enhanced help with command details and examples."""
    from rich.table import Table

    console.print()

    # Commands table
    commands_table = Table(show_header=False, box=None, padding=(0, 1))
    commands_table.add_column(style=f"{mode_color} bold", justify="left", width=20)
    commands_table.add_column(style="white", justify="left")

    commands_table.add_row(
        "/settings",
        "Configure model, SDK, agent provider, and sync settings\n[dim]Usage: /settings[/dim]",
    )
    commands_table.add_row("", "")  # Spacing

    commands_table.add_row(
        "/history",
        "View past runs with timestamps, costs, and status\n[dim]Usage: /history[/dim]",
    )
    commands_table.add_row("", "")

    commands_table.add_row(
        "/messages <run_id>",
        "View detailed message logs from a specific run\n[dim]Usage: /messages abc123[/dim]",
    )
    commands_table.add_row("", "")

    commands_table.add_row(
        "/cloud",
        "Show the hosted version and how to search its marketplace\n[dim]Usage: /cloud[/dim]",
    )
    commands_table.add_row(
        "/help or /commands",
        "Show this help message\n[dim]Usage: /help[/dim]",
    )
    commands_table.add_row("", "")

    commands_table.add_row("/exit or /quit", "Exit the application\n[dim]Usage: /exit[/dim]")

    console.print(" [bold white]Available Commands[/bold white]")
    console.print(commands_table)

    # Modes table
    console.print()
    modes_table = Table(show_header=False, box=None, padding=(0, 1))
    modes_table.add_column(style=f"{mode_color} bold", justify="left", width=15)
    modes_table.add_column(style="dim", justify="left")

    modes_table.add_row("agent", "Autonomous agent + capture")
    modes_table.add_row("manual", "Full pipeline: browser + reverse engineering")
    modes_table.add_row("engineer", "Reverse engineer only (enter run_id)")
    modes_table.add_row("collector", "AI-powered data collection")

    console.print(" [bold white]Modes[/bold white] [dim]Shift+Tab to cycle[/dim]")
    console.print(modes_table)
    console.print()


def handle_messages(run_id: str, mode_color=THEME_PRIMARY):
    """Display messages from a previous run."""
    from rich.table import Table

    store = MessageStore(run_id)
    messages = store.load()

    if not messages:
        console.print(f" [dim]>[/dim] [red]no messages found for run:[/red] {run_id}")
        return

    # Create header panel
    header_table = Table(show_header=False, box=None, padding=(0, 0))
    header_table.add_column(style="white", justify="left")
    header_table.add_row(f"Run ID: {run_id}")
    header_table.add_row(f"Total Messages: {len(messages)}")

    console.print()
    console.print(" [bold white]Message Log[/bold white]")
    console.print(header_table)
    console.print()

    for msg in messages:
        msg_type = msg.get("type", "unknown")
        content = msg.get("content", "")
        timestamp = msg.get("timestamp", "")[:19]  # Truncate to datetime

        if msg_type == "prompt":
            console.print(f" [dim]{timestamp}[/dim] [white]prompt[/white]")
            # Show first 200 chars of prompt
            display = str(content)[:200]
            if len(str(content)) > 200:
                display += "..."
            console.print(f"   [dim]{display}[/dim]")
        elif msg_type == "tool_start":
            name = content.get("name", "tool")
            console.print(f" [dim]{timestamp}[/dim] [white]{name.lower()}[/white]")
        elif msg_type == "tool_result":
            name = content.get("name", "tool")
            is_error = content.get("is_error", False)
            status = "[red]error[/red]" if is_error else "[dim]ok[/dim]"
            console.print(f" [dim]{timestamp}[/dim]   {status}")
        elif msg_type == "thinking":
            display = str(content)[:100].replace("\\n", " ")
            if len(str(content)) > 100:
                display += "..."
            console.print(f" [dim]{timestamp}  .. {display}[/dim]")
        elif msg_type == "error":
            console.print(f" [dim]{timestamp}[/dim] [red]error: {escape(str(content))}[/red]")
        elif msg_type == "result":
            console.print(f" [dim]{timestamp}[/dim] [white]complete[/white]")
            if isinstance(content, dict):
                script_path = content.get("script_path", "")
                if script_path:
                    console.print(f"   [dim]{script_path}[/dim]")

    console.print()


@main.command(
    epilog="""\b
Examples:
  reverse-api-engineer agent
  reverse-api-engineer agent -p "capture the jobs api" -u https://example.com --no-interactive
  reverse-api-engineer agent -p "capture the jobs api" --json | jq

\b
JSON output schema (--json):
  {
    "schema_version": 1,
    "status": "ok" | "error",
    "run_id": "<id>" | null,
    "prompt": "...",
    "url": "..." | null,
    "mode": "auto" | "chrome-mcp" | "agent-browser" | null,
    "har_path": "/abs/path/recording.har" | null,
    "script_path": "/abs/path/api_client.py" | null,
    "usage": {
      "input_tokens": ...,
      "output_tokens": ...,
      "cache_read_tokens": ...,
      "cache_write_tokens": ...,
      "total_cost_usd": ...,
      "raw": { ... }
    },
    "error": "<message>" | null,
    "error_kind": "misuse" | "config_invalid" | "permission_denied" | "network" | "engine_failure" | "interrupted" | "unknown" | null
  }

\b
Exit codes:
  0  success
  1  runtime error (capture or engineering failed)
  2  misuse (e.g. --prompt missing under --no-interactive / --json)
"""
)
@click.option("--prompt", "-p", default=None, help="Instruction for the autonomous agent.")
@click.option("--url", "-u", default=None, help="Optional starting URL.")
@click.option(
    "--model",
    "-m",
    type=click.Choice(["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5"]),
    default=None,
)
@click.option("--output-dir", "-o", default=None, help="Custom output directory.")
@click.option(
    "--no-interactive",
    is_flag=True,
    help="Fail fast instead of prompting for missing inputs (intended for scripted/agent usage).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit a single JSON result on stdout (logs go to stderr). Implies --no-interactive.",
)
@click.option(
    "--json-stream",
    "json_stream",
    is_flag=True,
    help="Emit NDJSON progress events on stdout during the run, then a final {\"event\":\"result\",...} line. Implies --no-interactive.",
)
@click.option(
    "--headless",
    is_flag=True,
    help="Launch the MCP-controlled browser in headless mode (required on machines without an X server). For chrome-mcp this drops --autoConnect since auto-connect requires a headed Chrome instance.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate prompt/url/config/env without launching the browser. Emits a manifest of what would run + check results. Implies --json. Exits 0 if all checks pass, 1 if any error.",
)
def agent(prompt, url, model, output_dir, no_interactive, as_json, json_stream, headless, dry_run):
    """Run autonomous agent browser session.

    Agent mode runs an integrated capture + reverse-engineering pipeline.
    """
    if dry_run:
        # --dry-run is fundamentally about emitting machine-parseable validation
        # results, so it implies --json (and therefore --no-interactive).
        with _quiet_consoles_for_json() as real_stdout:
            payload = _build_dry_run_payload(
                prompt=prompt, url=url, model=model, output_dir=output_dir, headless=headless
            )
        real_stdout.write(json.dumps(payload) + "\n")
        real_stdout.flush()
        sys.exit(0 if payload["status"] == "ok" else 1)

    no_interactive = no_interactive or as_json or json_stream
    machine_output = as_json or json_stream

    if no_interactive and not (prompt and prompt.strip()):
        if machine_output:
            misuse = _build_agent_payload(
                {},
                prompt=prompt,
                url=url,
                output_dir=output_dir,
                error="--prompt is required in non-interactive/--json mode",
                error_kind_hint="misuse",
            )
            if json_stream:
                misuse = {"event": "result", **misuse}
            click.echo(json.dumps(misuse))
        else:
            click.echo("error: --prompt is required when --no-interactive is set", err=True)
        sys.exit(2)

    # Either flag must suppress the post-generation follow-up prompt that would
    # otherwise block on stdin (`input("  > ")`) inside ClaudeAutoEngineer.
    interactive = not no_interactive

    if not machine_output:
        run_agent_capture(
            prompt=prompt,
            url=url,
            model=model,
            output_dir=output_dir,
            interactive=interactive,
            headless=headless,
        )
        return

    from .json_stream import make_json_stream_sink

    payload: dict
    with _quiet_consoles_for_json() as real_stdout:
        sink = (
            make_json_stream_sink(lambda line: (real_stdout.write(line + "\n"), real_stdout.flush()))
            if json_stream
            else None
        )
        try:
            result = run_agent_capture(
                prompt=prompt,
                url=url,
                model=model,
                output_dir=output_dir,
                interactive=interactive,
                headless=headless,
                json_event_sink=sink,
            )
            payload = _build_agent_payload(result, prompt=prompt, url=url, output_dir=output_dir)
        except KeyboardInterrupt as e:
            payload = _build_agent_payload(
                {}, prompt=prompt, url=url, output_dir=output_dir, error=e
            )
        except Exception as e:
            # Pass the exception object so _classify_error can use isinstance
            # (PermissionError → permission_denied, ConnectionError → network, ...)
            payload = _build_agent_payload(
                {}, prompt=prompt, url=url, output_dir=output_dir, error=e
            )

        _write_json_stdout(real_stdout, payload, json_stream=json_stream)
    sys.exit(0 if payload["status"] == "ok" else 1)


@main.group(invoke_without_command=True)
@click.pass_context
def marketplace(ctx: click.Context):
    """Browse ready-made API functions on the hosted marketplace.

    The marketplace behind anything.notte.cc holds functions other people
    already built. Searching it is public — no account, no API key — so it is
    worth a look before reverse-engineering a site from scratch.
    """
    if ctx.invoked_subcommand is None:
        _print_cloud_overview()


@marketplace.command("search")
@click.argument("query", required=False)
@click.option(
    "--site",
    default=None,
    help="Restrict to one site (URL or hostname). Only exact domain matches are returned.",
)
@click.option(
    "--category",
    default=None,
    help="Restrict to one marketplace category, e.g. Jobs, Finance, E-commerce.",
)
@click.option("--limit", "-n", default=5, show_default=True, help="Maximum results.")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit results as a single JSON document on stdout.",
)
def marketplace_search(query, site, category, limit, as_json):
    """Search the marketplace for an existing function.

    \b
    Examples:
      reverse-api-engineer marketplace search "nfl standings"
      reverse-api-engineer marketplace search --site https://www.nfl.com
      reverse-api-engineer marketplace search --category Jobs
      reverse-api-engineer marketplace search instagram --json | jq
    """
    if not query and not site and not category:
        if as_json:
            click.echo(json.dumps({"error": "provide a QUERY, --site, or --category", "results": []}))
            sys.exit(2)
        click.echo("error: provide a QUERY, --site, or --category", err=True)
        sys.exit(2)

    with console.status(" [dim]searching the marketplace...[/dim]", spinner="dots"):
        if site and not query and not category:
            # Domain-only lookups get the extra no-wrong-site guard.
            matches = cloud.search_for_site(site, limit=limit)
        else:
            matches = cloud.search(query, base_url=site, category=category, limit=limit)

    if as_json:
        click.echo(
            json.dumps(
                {
                    "query": query,
                    "site": site,
                    "category": category,
                    "count": len(matches),
                    "marketplace_url": cloud.MARKETPLACE_URL,
                    "results": [
                        {
                            "function_id": fn.function_id,
                            "label": fn.label,
                            "description": fn.description,
                            "domain": fn.domain,
                            "run_count": fn.run_count,
                            "url": fn.url,
                        }
                        for fn in matches
                    ],
                }
            )
        )
        return

    if not matches:
        console.print()
        console.print(" [dim]no hosted function matches that yet[/dim]")
        console.print(f" [dim]build one at {cloud.CLOUD_URL}, or capture it yourself with agent mode[/dim]")
        console.print()
        return

    console.print()
    for fn in matches:
        console.print(
            f" [white]{escape(fn.label)}[/white] [dim]{escape(fn.domain)} · {fn.run_count} runs[/dim]"
        )
        if fn.description:
            desc = fn.description.replace("\n", " ").strip()
            if len(desc) > 100:
                desc = desc[:97] + "..."
            console.print(f"   [dim]{escape(desc)}[/dim]")
        console.print(f"   [dim]{fn.url}[/dim]")
        console.print()


@main.command(
    epilog="""\b
Examples:
  reverse-api-engineer collector -p "collect companies hiring browser automation engineers"
  reverse-api-engineer collector
"""
)
@click.option("--prompt", "-p", default=None, help="Collection instructions.")
@click.option(
    "--model",
    "-m",
    type=click.Choice(["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5"]),
    default=None,
)
@click.option("--output-dir", "-o", default=None, help="Custom output directory for run metadata and messages.")
def collector(prompt, model, output_dir):
    """Run AI-powered data collection."""
    if prompt is None:
        if not sys.stdin.isatty():
            click.echo("error: --prompt is required when stdin is not a TTY", err=True)
            sys.exit(2)
        options = prompt_interactive_options(
            prompt=None,
            model=model,
            current_mode="collector",
        )
        if "command" in options:
            return
        prompt = options["prompt"]
        model = options.get("model") or model

    result = run_collector(prompt=prompt, model=model, output_dir=output_dir)
    if result is None or (isinstance(result, dict) and result.get("error")):
        sys.exit(1)


def run_manual_capture(prompt=None, url=None, reverse_engineer=True, model=None, output_dir=None):
    """Shared logic for manual capture."""
    output_dir = output_dir or config_manager.get("output_dir")

    # Manual mode drives a local Playwright browser, which ships in the optional
    # [manual] extra. Fail fast — before prompting the user or recording a run —
    # so a base-only install never leaves a phantom "manual" run in history.
    try:
        from .browser import ManualBrowser
    except ImportError as exc:
        raise click.ClickException(
            "Manual capture mode requires the Playwright browser stack, which is "
            "not installed by default. Install it with:\n\n"
            "    pip install 'reverse-api-engineer[manual]'\n"
            "    playwright install chromium\n\n"
            "(Agent mode does not need this.)"
        ) from exc

    if prompt is None:
        options = prompt_interactive_options(
            prompt=prompt,
            url=url,
            reverse_engineer=reverse_engineer,
            model=model,
        )
        if "command" in options:
            return  # Should not happen from here
        prompt = options["prompt"]
        url = options["url"]
        reverse_engineer = options["reverse_engineer"]
        model = options["model"]

    run_id = generate_run_id()
    timestamp = get_timestamp()
    sdk = config_manager.get("sdk", "claude")

    # Record initial session
    session_manager.add_run(
        run_id=run_id,
        prompt=prompt,
        timestamp=timestamp,
        url=url,
        model=model,
        mode="manual",  # Track mode in history
        sdk=sdk,
        paths={"har_dir": str(get_har_dir(run_id, output_dir))},
    )

    browser = ManualBrowser(run_id=run_id, prompt=prompt, output_dir=output_dir)
    har_path = browser.start(start_url=url)

    if reverse_engineer:
        result = run_engineer(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            model=model,
            output_dir=output_dir,
        )
        if result:
            sdk = config_manager.get("sdk", "claude")
            session_manager.update_run(
                run_id=run_id,
                sdk=sdk,
                usage=result.get("usage", {}),
                paths={"script_path": result.get("script_path")},
            )
    else:
        console.print(" [dim]>[/dim] [white]recording complete[/white]")
        console.print(f" [dim]>[/dim] [white]run_id: {run_id}[/white]")
        console.print(f" [dim]>[/dim] [dim]use 'reverse-api-engineer engineer {run_id}' to engineer later[/dim]\n")


def run_agent_capture(
    prompt=None,
    url=None,
    model=None,
    output_dir=None,
    interactive=True,
    headless=False,
    json_event_sink=None,
):
    """Shared logic for agent capture mode."""
    output_dir = output_dir or config_manager.get("output_dir")

    if prompt is None:
        options = prompt_interactive_options(
            prompt=prompt,
            url=url,
            reverse_engineer=False,
            model=model,
        )
        if "command" in options:
            return
        prompt = options["prompt"]
        url = options["url"]
        model = options["model"]

    agent_provider = config_manager.get("agent_provider", "auto")
    return run_auto_capture(
        prompt=prompt,
        url=url,
        model=model,
        output_dir=output_dir,
        agent_provider=agent_provider,
        interactive=interactive,
        headless=headless,
        json_event_sink=json_event_sink,
    )


def run_collector(prompt=None, model=None, output_dir=None):
    """Run AI-powered data collection with Collector class."""
    import asyncio

    from .collector import Collector

    # Generate run ID
    run_id = generate_run_id()
    output_dir = output_dir or config_manager.get("output_dir")

    # Use collector model from config if not specified
    if model is None:
        model = config_manager.get("collector_model", "claude-sonnet-4-6")

    # Initialize session
    session_manager.add_run(
        run_id=run_id,
        prompt=prompt or "",
        mode="collector",
        timestamp=get_timestamp(),
    )

    try:
        # Run collector
        collector = Collector(
            run_id=run_id,
            prompt=prompt or "",
            model=model,
            output_dir=output_dir,
        )

        result = asyncio.run(collector.run())

        if result and not result.get("error"):
            # Update session with results
            session_manager.update_run(
                run_id=run_id,
                sdk="claude",
                usage=result.get("usage", {}),
                paths={"output_path": result.get("output_path")},
            )
        return result
    except Exception as e:
        console.print(f" [red]collector error: {escape(str(e))}[/red]")
        console.print(f" [dim]{ERROR_CTA}[/dim]")
        import traceback

        traceback.print_exc()
        return {
            "run_id": run_id,
            "error": str(e) or type(e).__name__,
        }


def _print_cloud_overview():
    """Explain the hosted version. Backs both `/cloud` and the empty search."""
    console.print()
    console.print(f" [{THEME_SECONDARY}]anything[/{THEME_SECONDARY}] [dim]the hosted version of this tool[/dim]")
    console.print(" [dim]describe the task, get a deployed API function instead of a local file[/dim]")
    console.print()
    console.print(f" [dim]home[/dim]        [white]{cloud.CLOUD_URL}[/white]")
    console.print(f" [dim]marketplace[/dim] [white]{cloud.MARKETPLACE_URL}[/white] [dim]ready-made functions, no account needed[/dim]")
    console.print(f" [dim]mcp[/dim]         [white]{cloud.MCP_URL}[/white] [dim]point an agent here to search and run them[/dim]")
    console.print()
    console.print(" [dim]search from here:[/dim] [white]reverse-api-engineer marketplace search <query>[/white]")
    console.print()


def _render_marketplace_matches(matches, *, domain: str):
    """Show existing hosted functions for a site the user is about to capture."""
    plural = "function" if len(matches) == 1 else "functions"
    console.print()
    console.print(
        f" [{THEME_SECONDARY}]anything[/{THEME_SECONDARY}] [dim]already has[/dim] "
        f"[white]{len(matches)}[/white] [dim]{plural} for[/dim] [white]{domain}[/white]"
    )
    for fn in matches:
        console.print(f"   [dim]·[/dim] [white]{escape(fn.label)}[/white] [dim]({fn.run_count} runs)[/dim]")
        if fn.description:
            desc = fn.description.replace("\n", " ").strip()
            if len(desc) > 96:
                desc = desc[:93] + "..."
            console.print(f"     [dim]{escape(desc)}[/dim]")
        console.print(f"     [dim]{fn.url}[/dim]")
    console.print()


def _maybe_suggest_marketplace(url, *, interactive: bool) -> bool:
    """Offer an existing hosted function before capturing a site from scratch.

    Returns True when the user chose the marketplace instead, meaning the
    caller should abandon the capture. Never raises: a lookup problem must not
    cost someone their run.
    """
    if not url or not interactive:
        return False
    if not cloud.suggestions_enabled(config_manager):
        return False

    try:
        domain = cloud.registrable_domain(url)
        if not domain:
            return False
        # The lookup is usually instant but cold-starts at several seconds, so
        # show a spinner rather than an unexplained pause. Ctrl+C skips it.
        try:
            with console.status(f" [dim]checking if {domain} is already covered...[/dim]", spinner="dots"):
                matches = cloud.search_for_site(url)
        except KeyboardInterrupt:
            return False
        if not matches:
            return False

        _render_marketplace_matches(matches, domain=domain)

        # Default is No, so a bare enter carries on capturing — the suggestion
        # is an offer, not a toll gate.
        open_it = questionary.confirm(
            "Open the marketplace instead of capturing?",
            default=False,
            qmark="",
            style=questionary.Style([("question", "")]),
        ).ask()
    except Exception:
        return False

    if not open_it:
        return False

    target = cloud.cloud_link(matches[0].url, "cli_precapture")
    console.print(f" [dim]opening[/dim] [white]{matches[0].url}[/white]")
    try:
        import webbrowser

        webbrowser.open(target)
    except Exception:
        pass
    console.print(" [dim]capture skipped[/dim]")
    console.print()
    return True


def _print_cloud_deploy_hint():
    """One quiet line after a successful capture, pointing at the hosted path."""
    if not cloud.suggestions_enabled(config_manager):
        return
    console.print(
        f" [dim]want this hosted, scheduled, and repaired when the site changes? "
        f"{cloud.CLOUD_URL}[/dim]"
    )
    console.print()


def run_auto_capture(
    prompt=None,
    url=None,
    model=None,
    output_dir=None,
    agent_provider="auto",
    interactive=True,
    headless=False,
    json_event_sink=None,
):
    """Auto mode: LLM-driven browser automation + real-time reverse engineering."""
    output_dir = output_dir or config_manager.get("output_dir")

    if prompt is None:
        options = prompt_interactive_options(
            prompt=prompt,
            url=url,
            reverse_engineer=False,
            model=model,
        )
        if "command" in options:
            return
        prompt = options["prompt"]
        url = options.get("url")
        model = options["model"]

    # Before burning a capture run, check whether the site is already covered
    # by a hosted function. Skipped entirely when non-interactive or headless.
    if _maybe_suggest_marketplace(url, interactive=interactive and not headless):
        return None

    if agent_provider == "chrome-mcp" and not headless:
        console.print()
        console.print(" [dim]chrome devtools mcp (auto-connect)[/dim]")
        console.print(" [dim]controlling your real chrome browser[/dim]")
        console.print(" [dim]existing sessions, cookies, and auth available[/dim]")
        console.print()
        console.print(" [dim]auto-connect setup:[/dim]")
        console.print(" [dim] 1. chrome 146+ required[/dim]")
        console.print(" [dim] 2. go to chrome://inspect/#remote-debugging[/dim]")
        console.print(' [dim] 3. click "Enable auto-connect"[/dim]')
        console.print(" [dim] 4. node.js v20.19+[/dim]")
        console.print()
        console.print(" [dim]warning: the agent will execute actions on your browser[/dim]")
        console.print(" [dim]avoid browsing sensitive sites during the session[/dim]")
        console.print()
    elif agent_provider == "chrome-mcp" and headless:
        console.print()
        console.print(" [dim]chrome devtools mcp (headless)[/dim]")
        console.print(" [dim]auto-connect disabled — mcp will spawn its own headless chrome[/dim]")
        console.print()

    elif agent_provider == "agent-browser":
        console.print()
        console.print(
            " [dim]agent-browser: Vercel CLI via shell (Reverse API Engineer does not attach "
            "Playwright/Chrome browser MCP for this provider).[/dim]"
        )
        console.print(
            " [dim]Startup prefers PATH `agent-browser`, otherwise installs via "
            "`npm install -g <pin>` so Chromium pairs with a stable shim (with a banner); "
            "only falls back to `npx -y` if npm cannot run.[/dim]"
        )
        console.print(
            " [dim]First-time Chrome download: `agent-browser install` (add `--with-deps` on Linux).[/dim]"
        )
        console.print()

    sdk = config_manager.get("sdk", "claude")
    if model is None:
        model = default_model_for_configured_sdk(sdk)

    run_id = generate_run_id()
    timestamp = get_timestamp()

    if agent_provider == "chrome-mcp":
        mode_label = "chrome-mcp"
    elif agent_provider == "agent-browser":
        mode_label = "agent-browser"
    else:
        mode_label = "auto"
    session_manager.add_run(
        run_id=run_id,
        prompt=prompt,
        timestamp=timestamp,
        url=url,
        model=model,
        mode=mode_label,
        paths={"har_dir": str(get_har_dir(run_id, output_dir))},
    )

    try:
        output_language = config_manager.get("output_language", "python")
        if sdk == "opencode":
            from .auto_engineer import OpenCodeAutoEngineer

            engineer = OpenCodeAutoEngineer(
                run_id=run_id,
                prompt=prompt,
                output_dir=output_dir,
                agent_provider=agent_provider,
                opencode_provider=config_manager.get("opencode_provider", DEFAULT_OPENCODE_PROVIDER),
                opencode_model=model or config_manager.get("opencode_model", DEFAULT_OPENCODE_MODEL),
                enable_sync=config_manager.get("real_time_sync", False),
                sdk=sdk,
                output_language=output_language,
                interactive=interactive,
                headless=headless,
            )
        elif sdk == "copilot":
            from .auto_engineer import CopilotAutoEngineer

            engineer = CopilotAutoEngineer(
                run_id=run_id,
                prompt=prompt,
                copilot_model=model or config_manager.get("copilot_model", "gpt-5"),
                output_dir=output_dir,
                agent_provider=agent_provider,
                enable_sync=config_manager.get("real_time_sync", False),
                sdk=sdk,
                output_language=output_language,
                interactive=interactive,
                headless=headless,
            )
        elif sdk == "cursor":
            from .cursor_engineer import CursorAutoEngineer

            _cs = config_manager.get("cursor_setting_sources")
            _cursor_src = _cs if isinstance(_cs, list) and all(isinstance(x, str) for x in _cs) else None
            engineer = CursorAutoEngineer(
                run_id=run_id,
                prompt=prompt,
                output_dir=output_dir,
                agent_provider=agent_provider,
                enable_sync=config_manager.get("real_time_sync", False),
                sdk=sdk,
                output_language=output_language,
                interactive=interactive,
                headless=headless,
                cursor_model=model or config_manager.get("cursor_model", "composer-2.5"),
                cursor_web_search=bool(config_manager.get("cursor_web_search", True)),
                cursor_setting_sources=_cursor_src,
            )
        else:
            from .auto_engineer import ClaudeAutoEngineer

            engineer = ClaudeAutoEngineer(
                run_id=run_id,
                prompt=prompt,
                model=model or config_manager.get("claude_code_model", "claude-sonnet-4-6"),
                output_dir=output_dir,
                agent_provider=agent_provider,
                enable_sync=config_manager.get("real_time_sync", False),
                sdk=sdk,
                output_language=output_language,
                interactive=interactive,
                headless=headless,
            )

        if json_event_sink is not None:
            from .json_stream import attach_json_stream_to_engineer

            attach_json_stream_to_engineer(
                engineer,
                json_event_sink,
                mode=mode_label,
                url=url,
                command="agent",
            )

        # Start sync before analysis
        engineer.start_sync()

        interrupted = False
        try:
            result = asyncio.run(engineer.analyze_and_generate())
        except KeyboardInterrupt:
            result = None
            interrupted = True
        finally:
            # Always stop sync when done
            engineer.stop_sync()

        # Update session with results
        if result:
            session_manager.update_run(
                run_id=run_id,
                usage=result.get("usage", {}),
                paths={"script_path": result.get("script_path")},
            )
            if interactive and not interrupted and result.get("script_path"):
                _print_cloud_deploy_hint()

        return {
            "run_id": run_id,
            "mode": mode_label,
            "script_path": (result or {}).get("script_path"),
            "usage": (result or {}).get("usage", {}),
            **({"error": "interrupted"} if interrupted else {}),
        }

    except Exception as e:
        console.print(f" [red]auto mode error: {escape(str(e))}[/red]")
        console.print(f" [dim]{ERROR_CTA}[/dim]")
        import traceback

        traceback.print_exc()
        return {
            "run_id": run_id,
            "mode": mode_label,
            "script_path": None,
            "usage": {},
            "error": str(e),
        }


@main.command(
    epilog="""\b
Examples:
  reverse-api-engineer engineer abc123def456
  reverse-api-engineer engineer abc123def456 -p "add pagination support"
  reverse-api-engineer engineer abc123def456 --fresh -p "extract auth flow only"
  reverse-api-engineer engineer abc123def456 --json | jq

\b
JSON output schema (--json):
  {
    "schema_version": 1,
    "status": "ok" | "error",
    "run_id": "<id>",
    "prompt": "..." | null,
    "fresh": false,
    "script_path": "/abs/path/api_client.py" | null,
    "usage": {
      "input_tokens": ...,
      "output_tokens": ...,
      "cache_read_tokens": ...,
      "cache_write_tokens": ...,
      "total_cost_usd": ...,
      "raw": { ... }
    },
    "error": "<message>" | null,
    "error_kind": "misuse" | "config_invalid" | "permission_denied" | "network" | "engine_failure" | "interrupted" | "unknown" | null
  }

\b
Exit codes:
  0  success
  1  runtime error (engineering failed, run not found)
  2  misuse
"""
)
@click.argument("run_id", required=False)
@click.option(
    "--prompt",
    "-p",
    default=None,
    help=(
        "With --fresh: replace the captured run's original goal. "
        "Without --fresh: layered as additional instructions on top of the original prompt."
    ),
)
@click.option(
    "--fresh",
    is_flag=True,
    help="Ignore previously generated scripts and re-engineer from scratch.",
)
@click.option(
    "--model",
    "-m",
    type=click.Choice(["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5"]),
    default=None,
)
@click.option("--output-dir", "-o", default=None, help="Custom output directory.")
@click.option(
    "--no-interactive",
    is_flag=True,
    help="Reserved for symmetry with `agent`/`run`; engineer mode is non-interactive by design.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit a single JSON result on stdout (logs go to stderr). Implies --no-interactive.",
)
@click.option(
    "--json-stream",
    "json_stream",
    is_flag=True,
    help="Emit NDJSON progress events on stdout during the run, then a final {\"event\":\"result\",...} line. Implies --no-interactive.",
)
def engineer(run_id, prompt, fresh, model, output_dir, no_interactive, as_json, json_stream):
    """Run reverse engineering on a previous run."""
    # `run_id` is declared optional at the click level so that wrappers using
    # --json get a JSON misuse payload instead of Click's plain-text "missing
    # argument" error. We re-validate inline to preserve the same exit-2 UX
    # for non-JSON invocations.
    if not run_id:
        machine_output = as_json or json_stream
        if machine_output:
            misuse = _build_engineer_payload(
                None,
                run_id="",
                prompt=prompt,
                fresh=fresh,
                error="RUN_ID is required",
                error_kind_hint="misuse",
            )
            if json_stream:
                with _quiet_consoles_for_json() as real_stdout:
                    _write_json_stdout(real_stdout, misuse, json_stream=True)
            else:
                click.echo(json.dumps(misuse))
        else:
            click.echo("Usage: reverse-api-engineer engineer [OPTIONS] RUN_ID", err=True)
            click.echo("\nError: Missing argument 'RUN_ID'.", err=True)
        sys.exit(2)

    # --fresh treats --prompt as a full replacement of the original goal;
    # without --fresh, --prompt is additive so the captured run's context is preserved.
    main_prompt = prompt if fresh else None
    additional = prompt if (prompt and not fresh) else None
    # Either flag must suppress the post-generation follow-up prompt that
    # would otherwise block on stdin (`input("  > ")`) inside ClaudeEngineer.
    no_interactive = no_interactive or as_json or json_stream
    interactive = not no_interactive
    machine_output = as_json or json_stream

    if not machine_output:
        run_engineer(
            run_id,
            prompt=main_prompt,
            additional_instructions=additional,
            model=model,
            output_dir=output_dir,
            is_fresh=fresh,
            interactive=interactive,
        )
        return

    from .json_stream import make_json_stream_sink

    payload: dict
    with _quiet_consoles_for_json() as real_stdout:
        sink = (
            make_json_stream_sink(lambda line: (real_stdout.write(line + "\n"), real_stdout.flush()))
            if json_stream
            else None
        )
        try:
            result = run_engineer(
                run_id,
                prompt=main_prompt,
                additional_instructions=additional,
                model=model,
                output_dir=output_dir,
                is_fresh=fresh,
                interactive=interactive,
                json_event_sink=sink,
            )
            payload = _build_engineer_payload(result, run_id=run_id, prompt=prompt, fresh=fresh)
        except KeyboardInterrupt as e:
            payload = _build_engineer_payload(
                None, run_id=run_id, prompt=prompt, fresh=fresh, error=e
            )
        except Exception as e:
            # Pass the exception object so _classify_error can use isinstance.
            payload = _build_engineer_payload(
                None, run_id=run_id, prompt=prompt, fresh=fresh, error=e
            )

        _write_json_stdout(real_stdout, payload, json_stream=json_stream)
    sys.exit(0 if payload["status"] == "ok" else 1)


def run_engineer(
    run_id,
    har_path=None,
    prompt=None,
    model=None,
    output_dir=None,
    additional_instructions=None,
    is_fresh=False,
    output_mode="client",
    interactive=True,
    json_event_sink=None,
):
    """Shared logic for reverse engineering."""
    if not har_path or not prompt:
        # Load from history if possible
        run_data = session_manager.get_run(run_id)
        if not run_data:
            # Fallback to file search if not in history
            har_dir = get_har_dir(run_id, output_dir)
            har_path = har_dir / "recording.har"
            if not har_path.exists():
                console.print(f" [red]not found:[/red] {run_id}")
                return None
            if not prompt:
                prompt = "Reverse engineer captured APIs" if output_mode == "client" else "Generate OpenAPI documentation"
        else:
            if not prompt:
                prompt = run_data["prompt"]
            # Detect where it was saved
            paths = run_data.get("paths", {})
            har_dir = Path(paths.get("har_dir", get_har_dir(run_id, None)))
            har_path = har_dir / "recording.har"

    sdk = config_manager.get("sdk", "claude")
    enable_sync = config_manager.get("real_time_sync", True)
    output_language = config_manager.get("output_language", "python")

    if sdk == "opencode":
        result = run_reverse_engineering(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            model=model,
            output_dir=output_dir,
            sdk=sdk,
            opencode_provider=config_manager.get("opencode_provider", DEFAULT_OPENCODE_PROVIDER),
            opencode_model=config_manager.get("opencode_model", DEFAULT_OPENCODE_MODEL),
            enable_sync=enable_sync,
            additional_instructions=additional_instructions,
            is_fresh=is_fresh,
            output_language=output_language,
            output_mode=output_mode,
            interactive=interactive,
            json_event_sink=json_event_sink,
        )
    elif sdk == "copilot":
        result = run_reverse_engineering(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            model=model,
            output_dir=output_dir,
            sdk=sdk,
            copilot_model=config_manager.get("copilot_model", "gpt-5"),
            enable_sync=enable_sync,
            additional_instructions=additional_instructions,
            is_fresh=is_fresh,
            output_language=output_language,
            output_mode=output_mode,
            interactive=interactive,
            json_event_sink=json_event_sink,
        )
    elif sdk == "cursor":
        _cs = config_manager.get("cursor_setting_sources")
        _cursor_src = _cs if isinstance(_cs, list) and all(isinstance(x, str) for x in _cs) else None
        _cm = model or config_manager.get("cursor_model", "composer-2.5")
        result = run_reverse_engineering(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            model=_cm,
            output_dir=output_dir,
            sdk=sdk,
            cursor_model=_cm,
            cursor_web_search=bool(config_manager.get("cursor_web_search", True)),
            cursor_setting_sources=_cursor_src,
            enable_sync=enable_sync,
            additional_instructions=additional_instructions,
            is_fresh=is_fresh,
            output_language=output_language,
            output_mode=output_mode,
            interactive=interactive,
            json_event_sink=json_event_sink,
        )
    else:
        result = run_reverse_engineering(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            model=model or config_manager.get("claude_code_model", "claude-sonnet-4-6"),
            output_dir=output_dir,
            sdk=sdk,
            enable_sync=enable_sync,
            additional_instructions=additional_instructions,
            is_fresh=is_fresh,
            output_language=output_language,
            output_mode=output_mode,
            interactive=interactive,
            json_event_sink=json_event_sink,
        )

    if result:
        # Skip manual copy if real-time sync is enabled (files already synced)
        if not enable_sync:
            # Automatically copy to current directory with a readable name
            output_dir_path = Path(result["script_path"]).parent
            base_name = generate_folder_name(prompt, sdk=sdk)

            # Choose base path based on output mode
            if output_mode == "docs":
                base_path = Path.cwd() / "docs"
            else:
                base_path = Path.cwd() / "scripts"

            from .sync import get_available_directory

            # Get available directory (won't overwrite existing non-empty dirs)
            local_dir = get_available_directory(base_path, base_name)
            local_dir.mkdir(parents=True, exist_ok=True)

            import shutil

            for item in output_dir_path.iterdir():
                if item.is_file():
                    shutil.copy2(item, local_dir / item.name)

            # Different messages for docs vs client mode
            if output_mode == "docs":
                console.print(" [dim]>[/dim] [white]documentation complete[/white]")
                console.print(f" [dim]>[/dim] [white]{result['script_path']}[/white]")
                console.print(f" [dim]>[/dim] [white]copied to ./docs/{local_dir.name}[/white]\n")
            else:
                console.print(" [dim]>[/dim] [white]decoding complete[/white]")
                console.print(f" [dim]>[/dim] [white]{result['script_path']}[/white]")
                console.print(f" [dim]>[/dim] [white]copied to ./scripts/{local_dir.name}[/white]\n")
        else:
            # With sync enabled, just show completion
            if output_mode == "docs":
                console.print(" [dim]>[/dim] [white]documentation complete[/white]")
            else:
                console.print(" [dim]>[/dim] [white]decoding complete[/white]")
            console.print(f" [dim]>[/dim] [white]{result['script_path']}[/white]\n")

        session_manager.update_run(
            run_id=run_id,
            sdk=sdk,
            output_mode=output_mode,
            usage=result.get("usage", {}),
            paths={"script_path": result.get("script_path")},
        )
    return result


def _get_run_details(run: dict) -> dict:
    """Enrich a history entry with filesystem info."""
    run_id = run.get("run_id", "")
    output_dir = config_manager.get("output_dir")
    base_dir = get_base_output_dir(output_dir)
    script_dir = base_dir / "scripts" / run_id

    files = []
    if script_dir.exists():
        files = sorted(f.name for f in script_dir.iterdir() if f.is_file())

    # Scan ./scripts/ subdirectories to find local copy
    local_path = None
    local_scripts = Path.cwd() / "scripts"
    if local_scripts.exists() and files:
        files_set = set(files)
        for subdir in local_scripts.iterdir():
            if subdir.is_dir():
                local_files = {f.name for f in subdir.iterdir() if f.is_file()}
                if local_files and local_files == files_set:
                    local_path = f"./scripts/{subdir.name}/"
                    break

    usage = run.get("usage", {})
    cost = usage.get("total_cost", usage.get("cost"))

    return {
        "run_id": run_id,
        "prompt": run.get("prompt", ""),
        "timestamp": run.get("timestamp", ""),
        "model": run.get("model", ""),
        "mode": run.get("mode", ""),
        "sdk": run.get("sdk", ""),
        "cost": cost,
        "script_dir": str(script_dir),
        "files": files,
        "file_count": len(files),
        "local_path": local_path,
    }


@main.command(
    "list",
    epilog="""\b
Examples:
  reverse-api-engineer list
  reverse-api-engineer list --mode auto --search jobs --json | jq

JSON output (--json) is always a flat array (possibly empty []).
""",
)
@click.option("--json", "as_json", is_flag=True, help="Output as flat JSON array.")
@click.option("--full", is_flag=True, help="Show all columns (default: compact view).")
@click.option("--limit", "-n", type=int, default=None, help="Limit number of results.")
@click.option("--mode", "-m", type=str, default=None, help="Filter by mode (auto/manual/agent/engineer/collector).")
@click.option("--model", type=str, default=None, help="Filter by model name.")
@click.option("--search", "-s", type=str, default=None, help="Case-insensitive substring match on prompt.")
def list_runs(as_json, full, limit, mode, model, search):
    """List generated scripts and runs with optional filters."""
    from rich.table import Table

    runs = list(session_manager.history)

    if mode:
        runs = [r for r in runs if r.get("mode", "") == mode]
    if model:
        runs = [r for r in runs if model.lower() in (r.get("model") or "").lower()]
    if search:
        runs = [r for r in runs if search.lower() in (r.get("prompt") or "").lower()]

    if not runs:
        if as_json:
            click.echo(json.dumps([]))
        elif not session_manager.history:
            console.print("No runs found.", style="dim")
        else:
            console.print("No matching runs found.")
        return

    if limit is not None:
        runs = runs[:limit]

    results = [_get_run_details(r) for r in runs]

    if as_json:
        click.echo(json.dumps(results, indent=2))
        return

    if full:
        table = Table(show_lines=False)
        table.add_column("run_id", style="cyan")
        table.add_column("prompt", max_width=40)
        table.add_column("timestamp")
        table.add_column("model")
        table.add_column("mode")
        table.add_column("sdk")
        table.add_column("cost", justify="right")
        table.add_column("script_dir")
        table.add_column("files", justify="right")
        for r in results:
            prompt = r["prompt"][:40] + ("..." if len(r["prompt"]) > 40 else "")
            cost_str = f"${r['cost']:.2f}" if r["cost"] is not None else ""
            table.add_row(
                r["run_id"],
                prompt,
                r["timestamp"],
                r["model"] or "",
                r["mode"] or "",
                r["sdk"] or "",
                cost_str,
                r["script_dir"],
                str(r["file_count"]),
            )
    else:
        table = Table(show_lines=False)
        table.add_column("run_id", style="cyan")
        table.add_column("prompt", max_width=40)
        table.add_column("timestamp")
        table.add_column("script_dir")
        for r in results:
            prompt = r["prompt"][:40] + ("..." if len(r["prompt"]) > 40 else "")
            table.add_row(
                r["run_id"],
                prompt,
                r["timestamp"],
                r["script_dir"],
            )

    console.print(table)


@main.command(
    "show",
    epilog="""\b
Examples:
  reverse-api-engineer show
  reverse-api-engineer show <run_id> --json | jq

\b
Exit codes (--json):
  0  run found
  1  run not found / no history
""",
)
@click.argument("run_id", required=False)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON object.")
def show_run(run_id, as_json):
    """Show detailed info for a specific run."""
    from rich.table import Table
    from rich.text import Text

    def _show_error_payload(message: str, rid: str | None = None) -> dict:
        return {
            "schema_version": AGENT_JSON_SCHEMA_VERSION,
            "status": "error",
            "run_id": rid,
            "error": message,
            "error_kind": _classify_error(message, default="engine_failure"),
        }

    if run_id:
        run = session_manager.get_run(run_id)
    elif session_manager.history:
        run = session_manager.history[0]
    else:
        if as_json:
            click.echo(json.dumps(_show_error_payload("no runs found")))
            sys.exit(1)
        console.print("No runs found.", style="dim")
        return

    if run is None:
        if as_json:
            click.echo(json.dumps(_show_error_payload("run not found", run_id)))
            sys.exit(1)
        console.print(f"Run not found: {run_id}")
        return

    details = _get_run_details(run)
    rid = details["run_id"]
    output_dir = config_manager.get("output_dir")
    base_dir = get_base_output_dir(output_dir)

    # Extra fields
    details["url"] = run.get("url")
    details["output_mode"] = run.get("output_mode", "client")

    usage = run.get("usage", {})
    details["input_tokens"] = usage.get("input_tokens", 0)
    details["output_tokens"] = usage.get("output_tokens", 0)
    details["cache_creation_input_tokens"] = usage.get("cache_creation_input_tokens", 0)
    details["cache_read_input_tokens"] = usage.get("cache_read_input_tokens", 0)

    # Artifact paths with existence
    har_dir = base_dir / "har" / rid
    messages_path = get_messages_path(rid, output_dir)
    script_dir = Path(details["script_dir"])

    details["har_dir"] = str(har_dir)
    details["har_dir_exists"] = har_dir.exists()
    details["messages_path"] = str(messages_path)
    details["messages_path_exists"] = messages_path.exists()
    details["script_dir_exists"] = script_dir.exists()

    # HAR entry count
    har_entries = None
    if har_dir.exists():
        recording = har_dir / "recording.har"
        if recording.exists():
            try:
                har_data = json.loads(recording.read_text())
                har_entries = len(har_data.get("log", {}).get("entries", []))
            except Exception:
                pass
    details["har_entries"] = har_entries

    if as_json:
        details["schema_version"] = AGENT_JSON_SCHEMA_VERSION
        details["status"] = "ok"
        details["error"] = None
        details["error_kind"] = None
        click.echo(json.dumps(details, indent=2))
        return

    # Rich table output
    table = Table(show_header=False, show_lines=True)
    table.add_column(style="bold cyan")
    table.add_column()

    def _path_val(path_str: str, exists: bool) -> Text:
        t = Text(path_str + " ")
        t.append("✓" if exists else "✗", style="green" if exists else "red")
        return t

    rows: list[tuple[str, Text | str]] = [
        ("prompt", details["prompt"]),
        ("timestamp", details["timestamp"]),
        ("model", details["model"]),
        ("mode", details["mode"]),
        ("sdk", details["sdk"]),
        ("output_mode", details["output_mode"]),
        ("url", details.get("url")),
        ("cost", f"${details['cost']:.2f}" if details["cost"] is not None else None),
        ("input_tokens", str(details["input_tokens"])),
        ("output_tokens", str(details["output_tokens"])),
        ("cache_creation", str(details["cache_creation_input_tokens"])),
        ("cache_read", str(details["cache_read_input_tokens"])),
        ("har_dir", _path_val(details["har_dir"], details["har_dir_exists"])),
        ("har_entries", str(har_entries) if har_entries is not None else None),
        ("script_dir", _path_val(details["script_dir"], details["script_dir_exists"])),
    ]

    files = details["files"]
    if files:
        rows.append(("files", ", ".join(files) + f" ({len(files)})"))

    rows.append(("local_path", details.get("local_path")))
    rows.append(("messages", _path_val(details["messages_path"], details["messages_path_exists"])))

    for key, val in rows:
        if val is None or val == "":
            continue
        table.add_row(key, val if isinstance(val, Text) else str(val))

    console.print(f"\nRun {rid}")
    console.print(table)


def _extract_missing_module(stderr: str) -> str | None:
    """Extract a missing top-level module name from a ModuleNotFoundError message.

    Returns None if no module name is found or the name is not a plain Python
    identifier — a genuine ModuleNotFoundError always names one, and rejecting
    anything else prevents a crafted error message from smuggling pip options
    or arbitrary install targets.
    """
    import re as _re

    match = _re.search(r"No module named ['\"]([^'\"]+)['\"]", stderr)
    if not match:
        return None
    missing = match.group(1).split(".")[0]
    # fullmatch, since $ in re.match would accept a trailing newline
    if not _re.fullmatch(r"[a-zA-Z0-9_]+", missing) or len(missing) > 64:
        return None
    return missing


def _run_non_python_script(script, script_args) -> None:
    """Run a non-Python generated client with its language's toolchain and exit."""
    import shutil
    import subprocess

    from .utils import build_script_commands

    try:
        steps, tool = build_script_commands(script, script_args)
    except ValueError as e:
        raise click.ClickException(str(e)) from e
    if shutil.which(tool) is None:
        raise click.ClickException(f"cannot run {script.name}: '{tool}' is missing from PATH — install it and retry")
    returncode = 0
    for cmd in steps:
        returncode = subprocess.run(cmd, cwd=str(script.parent)).returncode
        if returncode != 0:
            break
    raise SystemExit(returncode)


def _run_script_machine_payload(
    *,
    identifier: str,
    script_args: tuple[str, ...],
    file_name: str | None,
    list_scripts: bool,
    auto_install: bool,
    emit_event,
) -> dict:
    """Run or list generated scripts without prompts and with JSON-safe stdout."""
    import subprocess

    run_id: str | None = None
    script: Path | None = None
    scripts: list[Path] = []

    try:
        run = resolve_run(identifier, session_manager, interactive=False)
        run_id = run["run_id"]
        output_dir = config_manager.get("output_dir")
        scripts = discover_scripts(run_id, output_dir, run_metadata=run)
        emit_event("run_resolved", run_id=run_id, script_count=len(scripts))

        if not scripts:
            return _build_run_payload(
                identifier=identifier,
                run_id=run_id,
                scripts=scripts,
                error=f"No runnable scripts found for run {run_id}",
                error_kind_hint="engine_failure",
            )

        if list_scripts:
            return _build_run_payload(
                identifier=identifier,
                run_id=run_id,
                scripts=scripts,
                returncode=0,
            )

        if file_name:
            matching = [s for s in scripts if s.name == file_name]
            if not matching:
                available = ", ".join(s.name for s in scripts)
                return _build_run_payload(
                    identifier=identifier,
                    run_id=run_id,
                    scripts=scripts,
                    error=f"'{file_name}' not found. Available: {available}",
                    error_kind_hint="misuse",
                )
            script = matching[0]
        elif len(scripts) == 1:
            script = scripts[0]
        else:
            available = ", ".join(s.name for s in scripts)
            return _build_run_payload(
                identifier=identifier,
                run_id=run_id,
                scripts=scripts,
                error=(f"multiple scripts found for run {run_id}; pass --file <name> to choose. Available: {available}"),
                error_kind_hint="misuse",
            )

        emit_event("script_selected", run_id=run_id, script_path=str(script))

        if script.suffix != ".py":
            import shutil

            from .utils import build_script_commands

            try:
                steps, tool = build_script_commands(script, script_args)
            except ValueError as e:
                return _build_run_payload(
                    identifier=identifier,
                    run_id=run_id,
                    script_path=str(script),
                    script_args=script_args,
                    scripts=scripts,
                    error=str(e),
                    error_kind_hint="misuse",
                )
            if shutil.which(tool) is None:
                return _build_run_payload(
                    identifier=identifier,
                    run_id=run_id,
                    script_path=str(script),
                    script_args=script_args,
                    scripts=scripts,
                    error=f"cannot run {script.name}: '{tool}' is missing from PATH — install it and retry",
                    error_kind_hint="config_invalid",
                )
            result = None
            for cmd in steps:
                emit_event("process_started", run_id=run_id, script_path=str(script))
                result = subprocess.run(cmd, cwd=str(script.parent), capture_output=True, text=True)
                if result.returncode != 0:
                    break
            return _build_run_payload(
                identifier=identifier,
                run_id=run_id,
                script_path=str(script),
                script_args=script_args,
                returncode=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                scripts=scripts,
            )

        from .utils import get_base_output_dir as _get_base

        venv_dir = _get_base(output_dir) / ".venv"
        venv_bin = "Scripts" if sys.platform == "win32" else "bin"
        venv_python = venv_dir / venv_bin / ("python.exe" if sys.platform == "win32" else "python")
        venv_pip = venv_dir / venv_bin / ("pip.exe" if sys.platform == "win32" else "pip")

        subprocess_kwargs = {"capture_output": True, "text": True}
        if not venv_dir.exists():
            emit_event("venv_setup_started", run_id=run_id, path=str(venv_dir))
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True, **subprocess_kwargs)
            subprocess.run([str(venv_pip), "install", "-q", "requests"], check=True, **subprocess_kwargs)
            emit_event("venv_setup_completed", run_id=run_id, path=str(venv_dir))

        requirements = script.parent / "requirements.txt"
        if requirements.exists():
            emit_event("requirements_install_started", run_id=run_id, path=str(requirements))
            subprocess.run([str(venv_pip), "install", "-q", "-r", str(requirements)], check=True, **subprocess_kwargs)
            emit_event("requirements_install_completed", run_id=run_id, path=str(requirements))

        cmd = [str(venv_python), str(script), *script_args]
        emit_event("process_started", run_id=run_id, script_path=str(script))
        result = subprocess.run(cmd, **subprocess_kwargs)

        stderr = result.stderr or ""
        if result.returncode != 0 and "ModuleNotFoundError: No module named" in stderr:
            missing = _extract_missing_module(stderr)
            if missing:
                emit_event("dependency_missing", run_id=run_id, package=missing)
                if auto_install:
                    emit_event("dependency_install_started", run_id=run_id, package=missing)
                    subprocess.run([str(venv_pip), "install", "-q", missing], check=True, **subprocess_kwargs)
                    emit_event("dependency_install_completed", run_id=run_id, package=missing)
                    emit_event("process_retried", run_id=run_id, script_path=str(script))
                    result = subprocess.run(cmd, **subprocess_kwargs)
                else:
                    return _build_run_payload(
                        identifier=identifier,
                        run_id=run_id,
                        script_path=str(script),
                        script_args=script_args,
                        returncode=result.returncode,
                        stdout=result.stdout or "",
                        stderr=stderr,
                        scripts=scripts,
                        error=f"missing dependency: {missing}",
                        error_kind_hint="engine_failure",
                    )
            elif auto_install:
                # Keep the refusal observable instead of falling through to a
                # generic script-exit error
                return _build_run_payload(
                    identifier=identifier,
                    run_id=run_id,
                    script_path=str(script),
                    script_args=script_args,
                    returncode=result.returncode,
                    stdout=result.stdout or "",
                    stderr=stderr,
                    scripts=scripts,
                    error="refusing to auto-install: no safe package name could be extracted from the ModuleNotFoundError output",
                    error_kind_hint="engine_failure",
                )

        return _build_run_payload(
            identifier=identifier,
            run_id=run_id,
            script_path=str(script),
            script_args=script_args,
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            scripts=scripts,
        )
    except click.ClickException as e:
        return _build_run_payload(
            identifier=identifier,
            run_id=run_id,
            script_path=str(script) if script else None,
            script_args=script_args,
            scripts=scripts,
            error=e.message,
            error_kind_hint="misuse",
        )
    except Exception as e:
        return _build_run_payload(
            identifier=identifier,
            run_id=run_id,
            script_path=str(script) if script else None,
            script_args=script_args,
            scripts=scripts,
            error=e,
            error_kind_hint="engine_failure",
        )


@main.command(
    "run",
    epilog="""\b
Examples:
  reverse-api-engineer run a450e520ca30
  reverse-api-engineer run ashby --ls
  reverse-api-engineer run ashby --file api_client.py -- --org acme --limit 10
  reverse-api-engineer run a450e520ca30 --file api_client.py --no-interactive --auto-install
  reverse-api-engineer run a450e520ca30 --file api_client.py --json | jq
  reverse-api-engineer run a450e520ca30 --file api_client.py --json-stream

\b
Exit codes:
  <script's exit code>  the underlying script's return code (0 on success)
  1                     no script found for the run
  non-zero              missing --file when multiple scripts exist under --no-interactive
""",
)
@click.argument("identifier")
@click.argument("script_args", nargs=-1, type=click.UNPROCESSED)
@click.option("--file", "-f", "file_name", default=None, help="Script filename to run (e.g. api_client.py).")
@click.option("--ls", "list_scripts", is_flag=True, help="List available scripts without executing.")
@click.option(
    "--no-interactive",
    is_flag=True,
    help="Fail fast on script-picker / missing-dependency prompts (intended for scripted/agent usage).",
)
@click.option(
    "--auto-install",
    is_flag=True,
    help="Auto-install missing dependencies on retry without prompting (implies --no-interactive for the picker).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit one JSON result on stdout with captured script stdout/stderr. Implies --no-interactive.",
)
@click.option(
    "--json-stream",
    "json_stream",
    is_flag=True,
    help='Emit NDJSON progress events on stdout, then a final {"event":"result",...} line. Implies --no-interactive.',
)
@click.pass_context
def run_script(ctx, identifier, script_args, file_name, list_scripts, no_interactive, auto_install, as_json, json_stream):
    """Run a generated script from a previous run.

    IDENTIFIER is a run ID or search term to match against prompts.
    Any extra arguments after the identifier are passed to the script.

    Examples:

        reverse-api-engineer run a450e520ca30

        reverse-api-engineer run ashby --ls

        reverse-api-engineer run ashby --file api_client.py

        reverse-api-engineer run ashby -- --org acme --limit 10
    """
    import subprocess
    import sys

    from rich.table import Table

    machine_output = as_json or json_stream
    no_interactive = no_interactive or machine_output

    if machine_output:
        with _quiet_consoles_for_json() as real_stdout:

            def emit_event(event: str, **fields) -> None:
                if json_stream:
                    _write_json_event(real_stdout, {"event": event, **fields})

            payload = _run_script_machine_payload(
                identifier=identifier,
                script_args=script_args,
                file_name=file_name,
                list_scripts=list_scripts,
                auto_install=auto_install,
                emit_event=emit_event,
            )
            _write_json_stdout(real_stdout, payload, json_stream=json_stream)

        if payload["returncode"] not in (None, 0):
            raise SystemExit(payload["returncode"])
        raise SystemExit(0 if payload["status"] == "ok" else 1)

    # Resolve which run
    run = resolve_run(identifier, session_manager, interactive=not no_interactive)
    run_id = run["run_id"]
    output_dir = config_manager.get("output_dir")

    # Discover scripts (prefer stored path from run metadata, fall back to output_dir)
    scripts = discover_scripts(run_id, output_dir, run_metadata=run)

    prompt_preview = (run.get("prompt") or "")[:80]
    ts = (run.get("timestamp") or "")[:19]
    console.print(f"{run_id}  {ts}  {prompt_preview}", style="dim")
    if scripts:
        console.print(f"{scripts[0].parent}", style="dim")

    if not scripts:
        console.print(f"[red]No runnable scripts found for run {run_id}[/red]")
        raise SystemExit(1)

    # --ls: just list and exit
    if list_scripts:
        table = Table(title=f"Scripts in run {run_id}")
        table.add_column("File", style="cyan")
        table.add_column("Size", justify="right")
        table.add_column("Modified")
        for s in scripts:
            stat = s.stat()
            size = f"{stat.st_size:,} B"
            from datetime import datetime

            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            table.add_row(s.name, size, modified)
        console.print(table)
        return

    # Select script
    if file_name:
        # Exact filename match
        matching = [s for s in scripts if s.name == file_name]
        if not matching:
            available = ", ".join(s.name for s in scripts)
            raise click.ClickException(f"'{file_name}' not found. Available: {available}")
        script = matching[0]
    elif len(scripts) == 1:
        script = scripts[0]
    elif no_interactive or auto_install:
        available = ", ".join(s.name for s in scripts)
        raise click.ClickException(
            f"multiple scripts found for run {run_id}; pass --file <name> to choose. Available: {available}"
        )
    else:
        # Interactive picker
        choices = [questionary.Choice(title=s.name, value=s) for s in scripts]
        script = questionary.select(
            "Select script to run:",
            choices=choices,
        ).ask()
        if script is None:
            raise click.Abort()

    # Non-Python clients: dispatch on extension, no venv involved
    if script.suffix != ".py":
        _run_non_python_script(script, script_args)

    # Shared venv at ~/.reverse-api/runs/.venv (with requests pre-installed)
    from .utils import get_base_output_dir as _get_base

    venv_dir = _get_base(output_dir) / ".venv"
    venv_bin = "Scripts" if sys.platform == "win32" else "bin"
    venv_python = venv_dir / venv_bin / ("python.exe" if sys.platform == "win32" else "python")
    venv_pip = venv_dir / venv_bin / ("pip.exe" if sys.platform == "win32" else "pip")

    if not venv_dir.exists():
        console.print("Setting up shared venv...", style="dim")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        subprocess.run([str(venv_pip), "install", "-q", "requests"], check=True)
        console.print("Shared venv ready.", style="dim")

    # Install per-run requirements.txt if present
    scripts_dir = script.parent
    requirements = scripts_dir / "requirements.txt"
    if requirements.exists():
        subprocess.run([str(venv_pip), "install", "-q", "-r", str(requirements)], check=True)

    python_path = str(venv_python)

    # Execute with real-time stdout, capture stderr for import error detection
    cmd = [python_path, str(script), *script_args]
    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)

    # Print stderr so the user sees it, then check for missing imports
    if result.stderr:
        sys.stderr.write(result.stderr)

    if result.returncode != 0:
        if "ModuleNotFoundError: No module named" in (result.stderr or ""):
            missing = _extract_missing_module(result.stderr)
            if missing:
                console.print(f"[yellow]Missing dependency: {missing}[/yellow]")

                if auto_install:
                    install = True
                elif no_interactive:
                    install = False
                else:
                    install = questionary.confirm(
                        f"Install '{missing}' and retry?", default=True
                    ).ask()
                if install:
                    subprocess.run([str(venv_pip), "install", "-q", missing], check=True)
                    console.print(f"Installed [green]{missing}[/green]. Retrying...")
                    result = subprocess.run(cmd)
                    raise SystemExit(result.returncode)

    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
