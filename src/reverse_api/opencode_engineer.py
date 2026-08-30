"""OpenCode SDK implementation for API reverse engineering.

Uses direct httpx calls with correct API format based on OpenCode
TypeScript SDK documentation.
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx2 as httpx

from .base_engineer import BaseEngineer
from .config import DEFAULT_OPENCODE_MODEL, DEFAULT_OPENCODE_PROVIDER
from .ollama_runtime import (
    OllamaProviderSetup,
    OllamaSetupError,
    opencode_ollama_env,
    prepare_ollama_model,
    validate_opencode_ollama_provider,
)
from .opencode_runtime import (
    OpenCodeSetupError,
    ensure_opencode_server,
    opencode_base_url,
    validate_opencode_model,
)
from .opencode_ui import OpenCodeUI

# Enable debug mode with OPENCODE_DEBUG=1
DEBUG = os.environ.get("OPENCODE_DEBUG", "0") == "1"


def debug_log(msg: str):
    """Print debug message if DEBUG mode is enabled."""
    if DEBUG:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}] [DEBUG] {msg}")


def format_error(e: Exception) -> str:
    """Format exception with full details in a pretty, readable format."""
    error_type = type(e).__name__
    error_msg = str(e)

    # Build comprehensive error message with pretty formatting
    lines = []

    # Main error line - always show error type and message
    if error_msg:
        lines.append(f"[bold red]✗ {error_type}[/bold red]")
        lines.append(f"  {error_msg}")
    else:
        lines.append(f"[bold red]✗ {error_type}[/bold red] (no message)")

    # Add additional context for specific exception types
    if isinstance(e, httpx.HTTPStatusError):
        if hasattr(e, "response") and e.response is not None:
            try:
                status_code = e.response.status_code
                status_text = e.response.reason_phrase or "Unknown"
                lines.append(f"\n[dim]HTTP Status:[/dim] [yellow]{status_code}[/yellow] {status_text}")

                # Try to parse JSON response for better formatting
                try:
                    response_json = e.response.json()
                    import json

                    response_text = json.dumps(response_json, indent=2)[:1000]  # Limit to 1000 chars
                    lines.append(f"\n[dim]Response Body:[/dim]")
                    # Split into lines and indent
                    for line in response_text.split("\n"):
                        lines.append(f"  [dim]{line}[/dim]")
                except Exception:
                    # Fall back to text if not JSON
                    response_text = e.response.text[:500]
                    if response_text:
                        lines.append(f"\n[dim]Response Body:[/dim]")
                        lines.append(f"  [dim]{response_text}[/dim]")
            except Exception:
                pass

    elif isinstance(e, httpx.ConnectError):
        lines.append(f"\n[dim]Unable to connect to OpenCode server[/dim]")
        if error_msg and "Connection refused" not in error_msg:
            lines.append(f"  [dim]{error_msg}[/dim]")

    elif isinstance(e, httpx.ReadError):
        lines.append(f"\n[dim]Connection was interrupted while reading response[/dim]")
        if error_msg:
            lines.append(f"  [dim]{error_msg}[/dim]")

    elif isinstance(e, httpx.TimeoutException):
        lines.append(f"\n[dim]Request timed out[/dim]")
        if error_msg:
            lines.append(f"  [dim]{error_msg}[/dim]")

    # In debug mode, include traceback
    if DEBUG:
        import traceback

        tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        lines.append(f"\n[dim]Traceback:[/dim]")
        for line in tb_str.split("\n"):
            lines.append(f"  [dim]{line}[/dim]")

    return "\n".join(lines)


class OpenCodeEngineer(BaseEngineer):
    """Uses OpenCode AI to analyze HAR files and generate Python API scripts."""

    BASE_URL = "http://127.0.0.1:4096"

    # Map short model names to full Anthropic model IDs
    MODEL_MAP = {
        "sonnet": "claude-sonnet-4-6",
        "opus": "claude-opus-4-6",
        "haiku": "claude-haiku-4-5",
    }

    def __init__(self, *args, **kwargs):
        # Pop OpenCode-specific kwargs before passing to parent class
        self.opencode_provider = kwargs.pop("opencode_provider", DEFAULT_OPENCODE_PROVIDER)
        self.opencode_model = kwargs.pop("opencode_model", DEFAULT_OPENCODE_MODEL)
        self.BASE_URL = opencode_base_url()

        super().__init__(*args, **kwargs)

        # Override UI with OpenCode-specific version
        self.opencode_ui = OpenCodeUI(verbose=kwargs.get("verbose", True))
        self.ui = self.opencode_ui  # Ensure base class uses our specialized UI
        self._last_error: str | None = None
        self._session_id: str | None = None
        self._last_event_time = 0.0
        self._work_started = False  # Track if any real work has been done
        self._busy_time: float | None = None  # When session became busy
        self._assistant_message_ids: set[str] = set()
        self._message_roles: dict[str, str] = {}
        self._pending_text_parts: dict[str, list[dict[str, Any]]] = {}

        # Read OpenCode server authentication from environment variables
        self.opencode_password = os.environ.get("OPENCODE_SERVER_PASSWORD")
        self.opencode_username = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode")

    def _get_auth(self) -> httpx.BasicAuth | None:
        """Get HTTP Basic Auth object if password is configured."""
        if self.opencode_password:
            return httpx.BasicAuth(self.opencode_username, self.opencode_password)
        return None

    async def _prepare_server(self, client: httpx.AsyncClient) -> bool:
        """Ensure OpenCode is healthy, starting the managed runtime if needed."""
        try:
            ollama_setup: OllamaProviderSetup | None = None
            env_overrides: dict[str, str] = {}
            if self.opencode_provider == "ollama":
                ollama_setup = await prepare_ollama_model(self.opencode_model)
                env_overrides = opencode_ollama_env(ollama_setup)

            server = await ensure_opencode_server(client, base_url=self.BASE_URL, env_overrides=env_overrides)
            if ollama_setup is not None:
                await validate_opencode_ollama_provider(client, self.opencode_model)
                self.opencode_ui.ollama_ready(self.opencode_model, ollama_setup.status.started)
            if server.started and server.package:
                self.opencode_ui.server_started(server.package, self.BASE_URL)
            self.opencode_ui.health_check(server.health)
            if server.version_warning:
                self.opencode_ui.compatibility_warning(server.version_warning)
            model_id = self.MODEL_MAP.get(self.opencode_model, self.opencode_model)
            await validate_opencode_model(client, self.opencode_provider, model_id)
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 401:
                raise
            debug_log("Health check failed: authentication required")
            self.opencode_ui.error("Authentication failed. OpenCode server requires a password.", unexpected=False)
            self.opencode_ui.console.print("\n[dim]Please set OPENCODE_SERVER_PASSWORD environment variable[/dim]")
            if self.opencode_username != "opencode":
                self.opencode_ui.console.print(f"[dim]Username: {self.opencode_username}[/dim]")
            return False
        except (OllamaSetupError, OpenCodeSetupError) as e:
            debug_log(f"OpenCode setup failed: {e}")
            self.opencode_ui.error(str(e), unexpected=False)
            return False
        except Exception as e:
            debug_log(f"Health check failed: {e}")
            self.opencode_ui.error(f"OpenCode server not responding. Is it running on {self.BASE_URL}?")
            self.opencode_ui.console.print("\n[dim]RAE can auto-start OpenCode when Node.js and npx are available.[/dim]")
            return False

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        """Run the reverse engineering analysis with OpenCode."""
        self.opencode_ui.header(self.run_id, self.prompt, self.opencode_model, self.sdk, mode="engineer")
        self.opencode_ui.start_analysis()

        system_prompt, user_message = self._build_prompts()
        combined_prompt = f"{system_prompt}\n\n{user_message}"
        self.message_store.save_prompt(user_message)

        try:
            auth = self._get_auth()
            async with httpx.AsyncClient(base_url=self.BASE_URL, timeout=600.0, auth=auth) as client:
                if not await self._prepare_server(client):
                    return None

                # Create a new session
                r = await client.post("/session", json={})
                r.raise_for_status()
                session_data = r.json()
                self._session_id = session_data["id"]

                self.opencode_ui.session_created(self._session_id)

                # Start event stream BEFORE sending message
                event_task = asyncio.create_task(self._stream_events(client))

                # Give event stream a moment to connect
                await asyncio.sleep(0.1)

                # Send prompt with correct format
                # POST /session/:id/message with model object
                # Resolve short model name to full model ID if needed
                model_id = self.MODEL_MAP.get(self.opencode_model, self.opencode_model)

                prompt_body = {
                    "model": {
                        "providerID": self.opencode_provider,
                        "modelID": model_id,
                    },
                    "parts": [{"type": "text", "text": combined_prompt}],
                }

                prompt_r = await client.post(f"/session/{self._session_id}/message", json=prompt_body)
                prompt_r.raise_for_status()

                # Wait for events to complete
                try:
                    await asyncio.wait_for(event_task, timeout=600.0)
                except TimeoutError:
                    self._last_error = "Session timed out (10 min)"

                # Stop streaming UI
                self.opencode_ui.stop_streaming()

                # Check for errors
                if self._last_error:
                    self.opencode_ui.error(self._last_error)
                    self.message_store.save_error(self._last_error)
                    return None

            # Success
            script_path = str(self.scripts_dir / self._get_client_filename())

            # Fetch actual provider and model used from session messages
            try:
                auth = self._get_auth()
                async with httpx.AsyncClient(base_url=self.BASE_URL, timeout=10.0, auth=auth) as client:
                    messages_r = await client.get(f"/session/{self._session_id}/message")
                    if messages_r.status_code == 200:
                        messages = messages_r.json()
                        # Find first assistant message with provider/model info
                        for msg in messages:
                            info = msg.get("info", {})
                            if info.get("role") == "assistant":
                                provider_id = info.get("providerID")
                                model_id = info.get("modelID")
                                if provider_id and model_id:
                                    self.opencode_ui.model_info(provider_id, model_id)
                                    break
            except Exception as e:
                error_msg = format_error(e)
                debug_log(f"Failed to fetch session messages: {error_msg}")
                # Don't fail the whole operation if we can't fetch messages

            # Show session summary before success message
            self.opencode_ui.session_summary(self.usage_metadata)
            local_path = str(self.local_scripts_dir / self._get_client_filename()) if self.local_scripts_dir else None
            self.opencode_ui.success(script_path, local_path)

            result_data: dict[str, Any] = {
                "script_path": script_path,
                "usage": self.usage_metadata,
                "session_id": self._session_id,
            }
            self.message_store.save_result(result_data)
            return result_data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                self.opencode_ui.error("Authentication failed. OpenCode server requires a password.", unexpected=False)
                self.opencode_ui.console.print("\n[dim]Please set OPENCODE_SERVER_PASSWORD environment variable[/dim]")
                if self.opencode_username != "opencode":
                    self.opencode_ui.console.print(f"[dim]Username: {self.opencode_username}[/dim]")
                self.message_store.save_error("Authentication failed")
                return None
            # Show detailed error including response body
            error_msg = format_error(e)
            debug_log(f"HTTPStatusError in analyze_and_generate: {error_msg}")
            self.opencode_ui.error(error_msg)
            self.message_store.save_error(error_msg)
            return None

        except httpx.ConnectError as e:
            error_msg = format_error(e)
            debug_log(f"ConnectError in analyze_and_generate: {error_msg}")
            self.opencode_ui.error("Connection error")
            self.opencode_ui.console.print(f"\n[dim]Details: {error_msg}[/dim]")
            self.opencode_ui.console.print("\n[dim]Please run: opencode serve[/dim]")
            self.message_store.save_error(f"Connection error: {error_msg}")
            return None

        except Exception as e:
            error_msg = format_error(e)
            debug_log(f"Exception in analyze_and_generate: {error_msg}")
            self.opencode_ui.error(error_msg)
            self.message_store.save_error(error_msg)
            return None

    async def _stream_events(self, client: httpx.AsyncClient):
        """Stream events from OpenCode and update UI."""
        seen_parts: set = set()  # Track part IDs to avoid duplicates
        import time

        self._last_event_time = time.time()

        debug_log("Starting event stream...")

        # Start the live display
        self.opencode_ui.start_streaming()

        try:
            debug_log("Connecting to GET /event")
            async with client.stream("GET", "/event", timeout=None) as response:
                debug_log(f"Event stream connected, status={response.status_code}")
                async for line in response.aiter_lines():
                    if not line:
                        continue

                    # SSE format: "data: {...}"
                    if not line.startswith("data: "):
                        if line.startswith("data:"):
                            line_data = line[5:].strip()
                        else:
                            debug_log(f"Skipping non-data line: {line[:50]}")
                            continue
                    else:
                        line_data = line[6:].strip()

                    if not line_data:
                        continue

                    self._last_event_time = time.time()

                    try:
                        data = json.loads(line_data)
                    except json.JSONDecodeError as e:
                        error_str = str(e)
                        # Check if this is a buffer size error
                        if "buffer size" in error_str.lower() or "1048576" in error_str or "exceeded maximum buffer" in error_str.lower():
                            debug_log(f"Buffer size error detected: {e}")
                            self._last_error = (
                                "Screenshot too large (exceeds 1MB limit). Try element-specific screenshots instead of full-page screenshots."
                            )
                            self.opencode_ui.error(self._last_error)
                            self.opencode_ui.console.print(
                                "[dim]Tip: Use browser_snapshot() for page structure or take smaller, element-specific screenshots.[/dim]"
                            )
                            # Don't continue - this is a fatal error for the session
                            return
                        debug_log(f"JSON decode error: {e}, data: {line_data[:100]}")
                        continue

                    event_type = data.get("type")
                    properties = data.get("properties", {})

                    debug_log(f"Event: {event_type}")

                    # Handle different event types
                    if event_type == "message.updated":
                        info = properties.get("info", {})
                        event_sid = properties.get("sessionID") or info.get("sessionID")
                        message_id = info.get("id")
                        if event_sid == self._session_id and message_id:
                            message_id = str(message_id)
                            role = str(info.get("role") or "")
                            self._message_roles[message_id] = role
                            pending = self._pending_text_parts.pop(message_id, [])
                            if role == "assistant":
                                self._assistant_message_ids.add(message_id)
                                for pending_properties in pending:
                                    await self._handle_part_update(pending_properties, seen_parts)

                    elif event_type == "message.part.updated":
                        await self._handle_part_update(properties, seen_parts)

                    elif event_type == "session.idle":
                        event_sid = properties.get("sessionID")
                        debug_log(f"session.idle: sessionID={event_sid}, our session={self._session_id}")
                        if event_sid == self._session_id:
                            if not await self._reconcile_pending_text_parts(client, seen_parts):
                                return
                            debug_log("Our session is idle, returning!")
                            self.opencode_ui.session_status("idle")
                            return  # Done!

                    elif event_type == "session.status":
                        event_sid = properties.get("sessionID")
                        status = properties.get("status", {})
                        status_type = status.get("type", "idle")
                        debug_log(f"session.status: sessionID={event_sid}, status={status_type}")
                        if event_sid == self._session_id:
                            if status_type == "retry":
                                attempt = status.get("attempt", 1)
                                message = status.get("message", "")
                                self.opencode_ui.session_retry(attempt, message)
                            elif status_type == "busy":
                                import time

                                self._busy_time = time.time()
                                self.opencode_ui.session_status(status_type)
                            else:
                                self.opencode_ui.session_status(status_type)

                            if status_type == "idle":
                                # Check if this is suspiciously fast (< 1 second of work)
                                import time

                                if self._busy_time and (time.time() - self._busy_time) < 1.0 and not self._work_started:
                                    debug_log("Suspiciously fast idle - checking for errors")
                                    # Try to get session details to check for error
                                    await self._check_session_error(client)
                                if self._last_error:
                                    return
                                if not await self._reconcile_pending_text_parts(client, seen_parts):
                                    return
                                debug_log("Our session status is idle, returning!")
                                return  # Done!

                    elif event_type in {"permission.updated", "permission.asked", "permission.v2.asked"}:
                        # Auto-approve permissions so the agent can proceed
                        permission_id = properties.get("id")
                        perm_session = properties.get("sessionID")
                        is_v2 = event_type == "permission.v2.asked"
                        perm_type = properties.get("type") or properties.get("permission") or properties.get("action") or "permission"
                        resources = properties.get("resources") or properties.get("patterns") or []
                        perm_title = properties.get("title") or ", ".join(resources) or perm_type

                        debug_log(f"{event_type}: id={permission_id}, type={perm_type}, title={perm_title}")

                        if perm_session == self._session_id and permission_id:
                            # Show permission request in UI
                            self.opencode_ui.permission_requested(perm_type, perm_title)

                            # Auto-approve the permission
                            # OpenCode expects: "once" | "always" | "reject"
                            debug_log(f"Auto-approving permission {permission_id}")
                            try:
                                if is_v2:
                                    perm_response = await client.post(
                                        f"/api/session/{self._session_id}/permission/{permission_id}/reply",
                                        json={"reply": "always"},
                                    )
                                else:
                                    perm_response = await client.post(
                                        f"/session/{self._session_id}/permissions/{permission_id}",
                                        json={"response": "always"},  # Legacy OpenCode permission API
                                    )
                                debug_log(f"Permission response: {perm_response.status_code}")
                                if 200 <= perm_response.status_code < 300:
                                    self.opencode_ui.permission_approved(perm_type)
                                else:
                                    self._last_error = (
                                        f"Permission approval failed for {perm_type}: "
                                        f"OpenCode returned HTTP {perm_response.status_code}."
                                    )
                                    debug_log(self._last_error)
                                    return
                            except Exception as pe:
                                self._last_error = f"Permission approval failed for {perm_type}: {pe}"
                                debug_log(self._last_error)
                                return

                    elif event_type == "todo.updated":
                        todos = properties.get("todos", [])
                        event_sid = properties.get("sessionID")
                        if event_sid == self._session_id and todos:
                            debug_log(f"todo.updated: {len(todos)} todos")
                            self.opencode_ui.todo_updated(todos)

                    elif event_type == "file.edited":
                        file_path = properties.get("file", "")
                        if file_path:
                            debug_log(f"file.edited: {file_path}")
                            self.opencode_ui.file_edited(file_path)

                    elif event_type == "session.diff":
                        event_sid = properties.get("sessionID")
                        diffs = properties.get("diff", [])
                        if event_sid == self._session_id and diffs:
                            debug_log(f"session.diff: {len(diffs)} files changed")
                            self.opencode_ui.session_diff(diffs)

                    elif event_type == "session.compacted":
                        event_sid = properties.get("sessionID")
                        if event_sid == self._session_id:
                            debug_log("session.compacted")
                            self.opencode_ui.session_compacted()

                    elif event_type == "session.error":
                        event_sid = properties.get("sessionID")
                        if event_sid and event_sid != self._session_id:
                            debug_log(f"session.error for other session {event_sid}, ignoring")
                            continue

                        error_obj = properties.get("error", {})
                        debug_log(f"session.error: {error_obj}")

                        # Parse error with type-specific handling
                        if isinstance(error_obj, dict):
                            error_name = error_obj.get("name", "UnknownError")
                            error_data = error_obj.get("data", {})

                            if error_name == "ProviderAuthError":
                                provider = error_data.get("providerID", "unknown")
                                msg = error_data.get("message", "Authentication failed")
                                self._last_error = f"Auth error ({provider}): {msg}"
                            elif error_name in ("ProviderModelNotFoundError", "ModelNotFoundError"):
                                provider = error_data.get("providerID", "unknown")
                                model = error_data.get("modelID", "unknown")
                                suggestions = error_data.get("suggestions", [])
                                self._last_error = f"Model not found: {provider}/{model}"
                                if suggestions:
                                    self._last_error += f"\n  Did you mean: {', '.join(suggestions)}?"
                            elif error_name == "APIError":
                                msg = error_data.get("message", "API error")
                                status = error_data.get("statusCode", "")
                                if str(status) == "401" and str(msg).casefold() == "no provider available":
                                    self._last_error = (
                                        "OpenCode has no serving provider available for this model right now. "
                                        "Try another free model or retry later."
                                    )
                                else:
                                    self._last_error = f"API error{' (' + str(status) + ')' if status else ''}: {msg}"
                            elif error_name == "MessageAbortedError":
                                self._last_error = "Aborted"
                            else:
                                msg = error_data.get("message", "") if isinstance(error_data, dict) else str(error_data)
                                self._last_error = f"{error_name}: {msg}" if msg else error_name
                        else:
                            self._last_error = str(error_obj)

                        return

        except httpx.ReadError as e:
            self._last_error = format_error(e)
            debug_log(f"ReadError in _stream_events: {self._last_error}")
        except Exception as e:
            self._last_error = format_error(e)
            debug_log(f"Exception in _stream_events: {self._last_error}")

    async def _reconcile_pending_text_parts(self, client: httpx.AsyncClient, seen_parts: set) -> bool:
        """Resolve buffered text roles from OpenCode's final session state."""

        if not self._pending_text_parts:
            return True
        try:
            response = await client.get(f"/session/{self._session_id}/message")
            if not 200 <= response.status_code < 300:
                self._last_error = f"Could not reconcile final OpenCode messages: HTTP {response.status_code}."
                return False
            messages = response.json()
        except Exception as e:
            self._last_error = f"Could not reconcile final OpenCode messages: {e}"
            return False
        if not isinstance(messages, list):
            self._last_error = "Could not reconcile final OpenCode messages: invalid response."
            return False

        for message in messages:
            info = message.get("info", {}) if isinstance(message, dict) else {}
            message_id = str(info.get("id") or "")
            role = str(info.get("role") or "")
            if not message_id or not role or message_id not in self._pending_text_parts:
                continue
            self._message_roles[message_id] = role
            pending = self._pending_text_parts.pop(message_id)
            if role == "assistant":
                self._assistant_message_ids.add(message_id)
                for pending_properties in pending:
                    await self._handle_part_update(pending_properties, seen_parts)

        if self._pending_text_parts:
            unresolved = ", ".join(sorted(self._pending_text_parts))
            self._last_error = f"OpenCode completed without role metadata for buffered message(s): {unresolved}."
            return False
        return True

    async def _check_session_error(self, client: httpx.AsyncClient):
        """Check session for errors when we get suspiciously fast idle."""
        try:
            # Get the session details to check for errors
            r = await client.get(f"/session/{self._session_id}")
            if r.status_code == 200:
                session_data = r.json()
                debug_log(f"Session data: {session_data}")

                # Check for error in session status
                status = session_data.get("status", {})
                if status.get("type") == "error":
                    error = status.get("error", {})
                    error_name = error.get("name", "UnknownError")
                    error_data = error.get("data", {})

                    if error_name in ("ProviderModelNotFoundError", "ModelNotFoundError"):
                        provider = error_data.get("providerID", "unknown")
                        model = error_data.get("modelID", "unknown")
                        suggestions = error_data.get("suggestions", [])
                        self._last_error = f"Model not found: {provider}/{model}"
                        if suggestions:
                            self._last_error += f"\n  Did you mean: {', '.join(suggestions)}?"
                    else:
                        msg = error_data.get("message", "") if isinstance(error_data, dict) else str(error_data)
                        self._last_error = f"{error_name}: {msg}" if msg else error_name

            # Also check messages for errors
            msg_r = await client.get(f"/session/{self._session_id}/message")
            if msg_r.status_code == 200:
                messages = msg_r.json()
                # Look for error messages
                for msg in messages:
                    info = msg.get("info", {})
                    if info.get("role") == "assistant":
                        # Check parts for error info
                        for part in msg.get("parts", []):
                            if part.get("type") == "error":
                                error_data = part.get("error", {})
                                error_name = error_data.get("name", "Error")

                                if error_name in ("ProviderModelNotFoundError", "ModelNotFoundError"):
                                    provider = error_data.get("data", {}).get("providerID", "unknown")
                                    model = error_data.get("data", {}).get("modelID", "unknown")
                                    suggestions = error_data.get("data", {}).get("suggestions", [])
                                    self._last_error = f"Model not found: {provider}/{model}"
                                    if suggestions:
                                        self._last_error += f"\n  Did you mean: {', '.join(suggestions)}?"
                                    return
        except Exception as e:
            debug_log(f"Error checking session: {e}")

    async def _handle_part_update(self, properties: dict, seen_parts: set):
        """Handle message.part.updated events."""
        part = properties.get("part", {})
        delta = properties.get("delta")  # Incremental text update

        part_id = part.get("id", "")
        part_type = part.get("type")
        part_session = part.get("sessionID")

        debug_log(f"Part update: type={part_type}, session={part_session}, our={self._session_id}")

        # Only process parts for our session
        if part_session != self._session_id:
            debug_log(f"Skipping part for other session")
            return

        if part_type == "text":
            text = part.get("text", "")
            debug_log(f"Handling text part: id={part_id}, delta={'yes' if delta else 'no'}, len={len(text)}")

            message_id = str(part.get("messageID") or "")
            if message_id and message_id not in self._message_roles and message_id not in self._assistant_message_ids:
                debug_log(f"Buffering text until role is known for message {message_id}")
                self._pending_text_parts.setdefault(message_id, []).append(properties)
                return
            if message_id not in self._assistant_message_ids:
                debug_log(f"Skipping text for non-assistant message {message_id or 'unknown'}")
                return

            # Use delta for incremental updates if available
            self.opencode_ui.update_text(text, delta)

            # Save to message store (only significant updates)
            if len(text) > 50 and part_id not in seen_parts:
                seen_parts.add(part_id)
                self.message_store.save_thinking(text)

        elif part_type == "tool":
            tool_name = part.get("tool", "tool")
            state = part.get("state", {})
            status = state.get("status")

            debug_log(f"Handling tool part: id={part_id}, tool={tool_name}, status={status}")

            if status == "running" and part_id not in seen_parts:
                self._work_started = True  # Mark that real work has started
                seen_parts.add(part_id)
                tool_input = state.get("input", {})
                self.opencode_ui.tool_start(tool_name, tool_input)
                self.message_store.save_tool_start(tool_name, tool_input)

            elif status == "completed":
                output = state.get("output", "")
                self.opencode_ui.tool_result(tool_name, False, output)
                self.message_store.save_tool_result(tool_name, False, output)

            elif status == "error":
                error = state.get("error", "Tool error")
                self.opencode_ui.tool_result(tool_name, True, error)
                self.message_store.save_tool_result(tool_name, True, error)

        elif part_type == "step-finish":
            debug_log("Handling step-finish part")
            # Extract usage stats
            api_cost = part.get("cost", 0)
            tokens = part.get("tokens", {})

            input_tokens = tokens.get("input", 0)
            output_tokens = tokens.get("output", 0)
            reasoning_tokens = tokens.get("reasoning", 0)
            cache = tokens.get("cache", {})
            cache_read = cache.get("read", 0)
            cache_write = cache.get("write", 0)

            if api_cost == 0 and (input_tokens > 0 or output_tokens > 0):
                from .pricing import calculate_cost

                calculated_cost = calculate_cost(
                    model_id=self.opencode_model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_creation_tokens=cache_write,
                    cache_read_tokens=cache_read,
                    reasoning_tokens=reasoning_tokens,
                )
                cost = calculated_cost
                debug_log(f"API cost was 0, calculated locally: ${cost:.4f}")
            else:
                cost = api_cost

            self.usage_metadata["input_tokens"] = self.usage_metadata.get("input_tokens", 0) + input_tokens
            self.usage_metadata["output_tokens"] = self.usage_metadata.get("output_tokens", 0) + output_tokens
            self.usage_metadata["reasoning_tokens"] = self.usage_metadata.get("reasoning_tokens", 0) + reasoning_tokens
            self.usage_metadata["cache_read_tokens"] = self.usage_metadata.get("cache_read_tokens", 0) + cache_read
            self.usage_metadata["cache_creation_tokens"] = self.usage_metadata.get("cache_creation_tokens", 0) + cache_write
            self.usage_metadata["cost"] = self.usage_metadata.get("cost", 0) + cost

        else:
            # Log unhandled part types for debugging
            debug_log(f"Unhandled part type: {part_type}")


def run_opencode_engineering(
    run_id: str,
    har_path: Path,
    prompt: str,
    model: str | None = None,
    additional_instructions: str | None = None,
    output_dir: str | None = None,
    verbose: bool = True,
    opencode_provider: str | None = None,
    opencode_model: str | None = None,
) -> dict[str, Any] | None:
    """Synchronous wrapper for OpenCode reverse engineering."""
    engineer = OpenCodeEngineer(
        run_id=run_id,
        har_path=har_path,
        prompt=prompt,
        model=model,
        additional_instructions=additional_instructions,
        output_dir=output_dir,
        verbose=verbose,
        opencode_provider=opencode_provider,
        opencode_model=opencode_model,
    )
    return asyncio.run(engineer.analyze_and_generate())
