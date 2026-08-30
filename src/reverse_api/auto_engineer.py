"""Auto mode engineers: LLM-controlled browsing with real-time reverse engineering.

Providers **auto** and **chrome-mcp** attach a browser MCP server to the SDK. Provider
**agent-browser** shells the upstream Vercel ``agent-browser`` CLI (auto-install via npm when missing, validated with ``--help``) instead of attaching browser MCP here.
"""

import asyncio
import logging
from typing import Any

import httpx2 as httpx
from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    ToolPermissionContext,
)

from .agent_browser import (
    agent_browser_prompt_fields,
    allowed_tools_agent_browser_agent_mode,
    ensure_agent_browser_runtime,
    print_agent_browser_setup_notices,
)
from .engineer import ClaudeEngineer
from .opencode_engineer import OpenCodeEngineer, debug_log, format_error
from .utils import build_sdk_env, get_har_dir

# Suppress claude_agent_sdk logs
logging.getLogger("claude_agent_sdk").setLevel(logging.WARNING)
logging.getLogger("claude_agent_sdk._internal.transport.subprocess_cli").setLevel(logging.WARNING)


def _agent_browser_prompt_context(engineer: Any) -> tuple[str, bool]:
    """Resolve run id + headless for agent-browser prompts without fragile getattr defaults."""

    if hasattr(engineer, "mcp_run_id"):
        run_id = engineer.mcp_run_id
    elif hasattr(engineer, "run_id"):
        run_id = engineer.run_id
    else:
        run_id = "unknown"
    headless = engineer.headless if hasattr(engineer, "headless") else False
    return run_id, headless


class ClaudeAutoEngineer(ClaudeEngineer):
    """Auto mode using Claude SDK: LLM-led browsing plus reverse-engineering codegen."""

    def __init__(
        self,
        run_id: str,
        prompt: str,
        model: str,
        output_dir: str | None = None,
        agent_provider: str = "auto",
        **kwargs,
    ):
        """Initialize Claude-backed agent engineer (HAR path derives from ``run_id``)."""
        # `headless` is auto-engineer specific: for MCP providers it configures the MCP
        # server's browser launch; for `agent-browser` it only adjusts prompt wording.
        headless = kwargs.pop("headless", False)
        har_dir = get_har_dir(run_id, output_dir)
        har_path = har_dir / "recording.har"

        super().__init__(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            model=model,
            output_dir=output_dir,
            **kwargs,
        )
        self.mcp_run_id = run_id
        self.agent_provider = agent_provider
        self.headless = headless

    def _build_auto_prompts(self) -> tuple[str, str]:
        """Build (system_prompt, user_message) for auto mode.

        The system prompt contains the agent role, codegen instructions, and output
        format. The user message contains the mission, workflow, and tool-specific
        instructions.
        """
        from .prompts import load

        language_name = self._get_language_name()
        codegen_instructions = self._get_codegen_instructions()

        client_filename = self._get_client_filename()
        output_files = self._get_auto_output_files(language_name, client_filename)

        browser_tool_label = (
            "Chrome DevTools MCP"
            if self.agent_provider == "chrome-mcp"
            else ("Vercel agent-browser (shell CLI)" if self.agent_provider == "agent-browser" else "MCP")
        )

        system_prompt = load(
            "auto/system",
            browser_tool_label=browser_tool_label,
            language_name=language_name,
            codegen_instructions=codegen_instructions,
            output_files=output_files,
        )

        if self.agent_provider == "chrome-mcp":
            template = "auto/user_chrome_mcp"
        elif self.agent_provider == "agent-browser":
            template = "auto/user_agent_browser"
        else:
            template = "auto/user_playwright"

        template_kwargs = {
            "prompt": self.prompt,
            "scripts_dir": str(self.scripts_dir),
        }
        if self.agent_provider != "chrome-mcp":
            template_kwargs["har_path"] = str(self.har_path)
        if self.agent_provider == "agent-browser":
            ab_run_id, ab_headless = _agent_browser_prompt_context(self)
            template_kwargs.update(
                agent_browser_prompt_fields(run_id=ab_run_id, headless=ab_headless),
            )

        user_message = load(template, **template_kwargs)
        return system_prompt, user_message

    def _get_active_prompts(self) -> tuple[str, str]:
        """Return (system_prompt, user_message) based on agent_provider."""
        return self._build_auto_prompts()

    async def _handle_tool_permission(self, tool_name: str, input_data: dict[str, Any], context: ToolPermissionContext) -> PermissionResultAllow:
        """Handle tool permission requests, with interactive UI for AskUserQuestion."""
        if tool_name == "AskUserQuestion":
            if not self.interactive:
                return PermissionResultAllow(
                    updated_input={
                        "questions": input_data.get("questions", []),
                        "answers": {},
                    },
                )
            questions = input_data.get("questions", [])
            answers = await self._ask_user_questions(questions)
            return PermissionResultAllow(
                updated_input={"questions": questions, "answers": answers},
            )
        # Auto-approve all other tools
        return PermissionResultAllow(updated_input=input_data)

    def _get_mcp_config(self) -> tuple[str, dict]:
        """Return ``(server_name, mcp_config)`` for Playwright or Chrome MCP providers.

        Not applicable to ``agent-browser`` (calling this raises). Auto-connect Chrome
        requires a headed instance with remote debugging unless ``headless`` is set.
        """
        if self.agent_provider == "agent-browser":
            raise RuntimeError(
                "agent-browser uses the Vercel agent-browser CLI from the shell, not a "
                "registered browser MCP server (this helper only builds configs for MCP providers)"
            )
        if self.agent_provider == "chrome-mcp":
            args = ["chrome-devtools-mcp@latest", "--no-usage-statistics"]
            if self.headless:
                args.append("--headless")
            else:
                args.append("--autoConnect")
            return "chrome-devtools", {
                "type": "stdio",
                "command": "npx",
                "args": args,
            }
        playwright_args = [
            "rae-playwright-mcp@latest",
            "run-mcp-server",
            "--run-id",
            self.mcp_run_id,
        ]
        if self.headless:
            playwright_args.append("--headless")
        return "playwright", {
            "type": "stdio",
            "command": "npx",
            "args": playwright_args,
        }

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        """Run agent mode with browser automation appropriate to ``agent_provider``.

        Reuses _process_streaming_response and follow-up loop from ClaudeEngineer.
        """
        self.ui.header(self.run_id, self.prompt, self.model, mode="agent")
        self.ui.start_analysis()

        # Fresh SDK session, fresh context window: clear any overflow state
        # left over from a previous run on a reused engineer instance.
        self._context_overflowed = False

        if self.agent_provider == "agent-browser":
            ab_setup = ensure_agent_browser_runtime()
            print_agent_browser_setup_notices(self.ui.console, ab_setup)
            if not ab_setup.ok:
                self.ui.error(ab_setup.error or "agent-browser setup failed")
                self.message_store.save_error(ab_setup.error or "agent-browser setup failed")
                return None

        system_prompt, user_message = self._get_active_prompts()
        self.message_store.save_prompt(user_message)

        # Every provider branch below needs the report_client_verified tool
        # available (see engineer.py's _build_verification_mcp_server) —
        # agent-drive sessions live-verify a generated client exactly the
        # same way engineer-mode ones do.
        verification_server = self._build_verification_mcp_server()

        if self.agent_provider == "agent-browser":
            options = ClaudeAgentOptions(
                system_prompt=system_prompt,
                mcp_servers={"verification": verification_server},
                # allowed_tools is an explicit allow-list here (unlike the
                # else branch below), so the verification tool needs its
                # SDK-qualified name added alongside it — confirmed live
                # this is how the SDK namespaces an in-process MCP tool
                # (matches real chrome-devtools-mcp tool-use blocks, e.g.
                # "mcp__chrome-devtools__navigate_page").
                allowed_tools=[
                    *allowed_tools_agent_browser_agent_mode(),
                    "mcp__verification__report_client_verified",
                ],
                permission_mode="bypassPermissions",
                can_use_tool=self._handle_tool_permission,
                cwd=str(self.scripts_dir.parent.parent),
                model=self.model,
                env=build_sdk_env(),
                stderr=self._handle_cli_stderr,
            )
        else:
            mcp_name, mcp_config = self._get_mcp_config()
            options = ClaudeAgentOptions(
                system_prompt=system_prompt,
                mcp_servers={mcp_name: mcp_config, "verification": verification_server},
                permission_mode="bypassPermissions",
                can_use_tool=self._handle_tool_permission,
                cwd=str(self.scripts_dir.parent.parent),
                model=self.model,
                env=build_sdk_env(),
                stderr=self._handle_cli_stderr,
            )

        last_result: dict[str, Any] | None = None

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(user_message)

                # Process initial response
                last_result = await self._process_streaming_response(client)
                if last_result is None:
                    return None

                # Conversation loop: prompt for follow-ups
                while True:
                    follow_up = await self._prompt_follow_up()
                    if not follow_up:
                        return last_result

                    self.ui.console.print()
                    self.message_store.save_prompt(follow_up)
                    await client.query(follow_up)

                    result = await self._process_streaming_response(client)
                    if result is not None:
                        last_result = result
                    elif self._context_overflowed:
                        # The conversation exceeds the context window; every
                        # further query would fail the same way, so end the
                        # follow-up loop instead of offering another turn.
                        return last_result

        except KeyboardInterrupt:
            self.ui.console.print("\n  [dim]run aborted[/dim]")
            return last_result

        except Exception as e:
            error_msg = str(e)
            self.ui.error(error_msg)
            self.message_store.save_error(error_msg)

            if "buffer size" in error_msg.lower() or "1048576" in error_msg or "exceeded maximum buffer" in error_msg.lower():
                self.ui.console.print("\n[yellow]Screenshot too large (exceeds 1MB limit)[/yellow]")
                self.ui.console.print("[dim]Tip: The AI should take element-specific screenshots instead of full-page screenshots.[/dim]")
                self.ui.console.print(
                    "[dim]Consider using browser_snapshot() for accessibility tree information when screenshots aren't needed.[/dim]"
                )
            elif "MCP server" in error_msg or "npx" in error_msg:
                if self.agent_provider == "chrome-mcp":
                    self.ui.console.print("\n[dim]Make sure chrome-devtools-mcp is available: npx chrome-devtools-mcp@latest[/dim]")
                    self.ui.console.print("[dim]Chrome 146+ required with auto-connect enabled at chrome://inspect/#remote-debugging[/dim]")
                elif self.agent_provider == "agent-browser":
                    self.ui.console.print(
                        "\n[dim]agent-browser: ensure `agent-browser` is global (`npm install -g`) or pinned "
                        "via agent_browser_npx_package / RAE_AGENT_BROWSER_PACKAGE, and rerun `reverse-api-engineer`.[/dim]"
                    )
                else:
                    self.ui.console.print("\n[dim]Make sure rae-playwright-mcp is installed: npm install -g rae-playwright-mcp[/dim]")
            else:
                self.ui.console.print("\n[dim]Make sure Claude Code CLI is installed: npm install -g @anthropic-ai/claude-code[/dim]")
            return None


class OpenCodeAutoEngineer(OpenCodeEngineer):
    """Agent mode via OpenCode: registers a browser MCP server when the provider uses MCP."""

    def __init__(self, run_id: str, prompt: str, output_dir: str | None = None, agent_provider: str = "auto", **kwargs):
        """Initialize OpenCode-backed agent engineer."""
        headless = kwargs.pop("headless", False)
        har_dir = get_har_dir(run_id, output_dir)
        har_path = har_dir / "recording.har"

        super().__init__(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            output_dir=output_dir,
            **kwargs,
        )
        self.mcp_run_id = run_id
        self.agent_provider = agent_provider
        self.mcp_name = None
        self.headless = headless

    def _get_active_prompts(self) -> tuple[str, str]:
        return ClaudeAutoEngineer._build_auto_prompts(self)

    def _get_opencode_mcp_config(self) -> dict | None:
        """Return OpenCode MCP registration payload based on agent_provider.

        Auto-connect requires a headed Chrome with a remote debugging server,
        so it is dropped in headless mode in favor of an MCP-spawned headless
        Chromium.

        agent-browser skips MCP—the model shells the upstream CLI directly.
        """
        if self.agent_provider == "agent-browser":
            self.mcp_name = None
            return None
        if self.agent_provider == "chrome-mcp":
            self.mcp_name = f"chrome-devtools-{self._session_id}"
            cmd = ["npx", "-y", "chrome-devtools-mcp@latest", "--no-usage-statistics"]
            if self.headless:
                cmd.append("--headless")
            else:
                cmd.append("--autoConnect")
            return {
                "name": self.mcp_name,
                "config": {
                    "type": "local",
                    "command": cmd,
                    "enabled": True,
                    "timeout": 30000,
                },
            }
        self.mcp_name = f"playwright-{self._session_id}"
        cmd = [
            "npx",
            "-y",
            "rae-playwright-mcp@latest",
            "run-mcp-server",
            "--run-id",
            self.mcp_run_id,
        ]
        if self.headless:
            cmd.append("--headless")
        return {
            "name": self.mcp_name,
            "config": {
                "type": "local",
                "command": cmd,
                "enabled": True,
                "timeout": 30000,
            },
        }

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        """Run agent mode via OpenCode (browser MCP registration only for MCP-backed providers)."""
        self.opencode_ui.header(self.run_id, self.prompt, self.opencode_model, mode="agent")
        self.opencode_ui.start_analysis()

        if self.agent_provider == "agent-browser":
            ab_setup = ensure_agent_browser_runtime()
            print_agent_browser_setup_notices(self.opencode_ui.console, ab_setup)
            if not ab_setup.ok:
                msg = ab_setup.error or "agent-browser setup failed"
                self.opencode_ui.error(msg)
                self.message_store.save_error(msg)
                return None

        system_prompt, user_message = self._get_active_prompts()
        active_prompt = f"{system_prompt}\n\n{user_message}"
        self.message_store.save_prompt(user_message)

        try:
            auth = self._get_auth()
            async with httpx.AsyncClient(base_url=self.BASE_URL, timeout=600.0, auth=auth) as client:
                if not await self._prepare_server(client):
                    return None

                # Create session first
                session_r = await client.post("/session", json={})
                session_r.raise_for_status()
                session_data = session_r.json()
                self._session_id = session_data["id"]
                self.opencode_ui.session_created(self._session_id)

                mcp_config = self._get_opencode_mcp_config()

                if mcp_config is not None:
                    try:
                        debug_log(f"Registering MCP server: {self.mcp_name}")
                        mcp_r = await client.post("/mcp", json=mcp_config)
                        mcp_r.raise_for_status()
                        debug_log("MCP server registered successfully")
                    except Exception as e:
                        self.opencode_ui.error(f"Failed to register MCP server: {e}")
                        return None

                # Start event stream BEFORE sending message
                event_task = asyncio.create_task(self._stream_events(client))

                # Give event stream a moment to connect
                await asyncio.sleep(0.1)

                model_id = self.MODEL_MAP.get(self.opencode_model, self.opencode_model)
                prompt_body = {
                    "model": {
                        "providerID": self.opencode_provider,
                        "modelID": model_id,
                    },
                    "parts": [{"type": "text", "text": active_prompt}],
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

                # Deregister MCP server
                if self.mcp_name:
                    try:
                        debug_log(f"Deregistering MCP server: {self.mcp_name}")
                        await client.delete(f"/mcp/{self.mcp_name}")
                        debug_log("MCP server deregistered")
                    except Exception as e:
                        debug_log(f"Failed to deregister MCP server: {e}")

                # Check for errors
                if self._last_error:
                    self.opencode_ui.error(self._last_error)
                    self.message_store.save_error(self._last_error)
                    return None

            # Success
            script_path = str(self.scripts_dir / self._get_client_filename())

            # Fetch actual provider and model used
            try:
                auth = self._get_auth()
                async with httpx.AsyncClient(base_url=self.BASE_URL, timeout=10.0, auth=auth) as client:
                    messages_r = await client.get(f"/session/{self._session_id}/message")
                    if messages_r.status_code == 200:
                        messages = messages_r.json()
                        for msg in messages:
                            info = msg.get("info", {})
                            if info.get("role") == "assistant":
                                provider_id = info.get("providerID")
                                model_id = info.get("modelID")
                                if provider_id and model_id:
                                    self.opencode_ui.model_info(provider_id, model_id)
                                    break
            except Exception as e:
                debug_log(f"Failed to fetch session messages: {e}")

            # Show session summary
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
            error_msg = f"HTTP {e.response.status_code}: {str(e)}"
            self.opencode_ui.error(error_msg)
            self.message_store.save_error(error_msg)
            return None

        except httpx.ConnectError:
            self.opencode_ui.error("Connection error")
            self.opencode_ui.console.print("\n[dim]Make sure OpenCode is running: opencode[/dim]")
            self.message_store.save_error("Connection error")
            return None

        except Exception as e:
            error_msg = format_error(e)
            debug_log(f"Exception in OpenCodeAutoEngineer.analyze_and_generate: {error_msg}")
            self.opencode_ui.error(error_msg)
            self.message_store.save_error(error_msg)

            # Handle screenshot buffer size errors specifically
            if "buffer size" in error_msg.lower() or "1048576" in error_msg or "exceeded maximum buffer" in error_msg.lower():
                self.opencode_ui.console.print("\n[yellow]⚠ Screenshot too large (exceeds 1MB limit)[/yellow]")
                self.opencode_ui.console.print("[dim]Tip: The AI should take element-specific screenshots instead of full-page screenshots.[/dim]")
                self.opencode_ui.console.print(
                    "[dim]Consider using browser_snapshot() for accessibility tree information when screenshots aren't needed.[/dim]"
                )

            return None

        finally:
            # Best effort cleanup - deregister MCP server
            if self.mcp_name:
                try:
                    auth = self._get_auth()
                    async with httpx.AsyncClient(base_url=self.BASE_URL, timeout=5.0, auth=auth) as client:
                        await client.delete(f"/mcp/{self.mcp_name}")
                        debug_log(f"Cleaned up MCP server: {self.mcp_name}")
                except Exception:
                    pass  # Ignore cleanup errors


class CopilotAutoEngineer:
    """Agent mode via Copilot SDK.

    Delegates to ``CopilotEngineer`` while wiring browser tooling: MCP for ``auto`` /
    ``chrome-mcp``, validated ``agent-browser`` CLI bootstrap for ``agent-browser``.
    Uses composition because ``CopilotEngineer`` relies on lazy imports.
    """

    def __init__(
        self,
        run_id: str,
        prompt: str,
        copilot_model: str | None = None,
        output_dir: str | None = None,
        agent_provider: str = "auto",
        **kwargs: Any,
    ):
        from .copilot_engineer import CopilotEngineer

        headless = kwargs.pop("headless", False)
        har_dir = get_har_dir(run_id, output_dir)
        har_path = har_dir / "recording.har"

        self._engineer = CopilotEngineer(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            copilot_model=copilot_model,
            output_dir=output_dir,
            **kwargs,
        )
        self.mcp_run_id = run_id
        self.agent_provider = agent_provider
        self.headless = headless

    def start_sync(self) -> None:
        self._engineer.start_sync()

    def stop_sync(self) -> None:
        self._engineer.stop_sync()

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        """Run agent mode with Copilot SDK (MCP browsers or agent-browser CLI per provider)."""
        try:
            from copilot import CopilotClient, PermissionHandler
        except ImportError:
            self._engineer.ui.error(
                "GitHub Copilot SDK not installed. From source: uv sync --extra copilot. Installed: pip install 'reverse-api-engineer[copilot]'"
            )
            return None

        eng = self._engineer
        eng.ui.header(eng.run_id, eng.prompt, eng.copilot_model, eng.sdk, mode="agent")
        eng.ui.start_analysis()

        eng.agent_provider = self.agent_provider
        eng.mcp_run_id = self.mcp_run_id
        eng.headless = self.headless

        if self.agent_provider == "agent-browser":
            ab_setup = ensure_agent_browser_runtime()
            print_agent_browser_setup_notices(eng.ui.console, ab_setup)
            if not ab_setup.ok:
                err = ab_setup.error or "agent-browser setup failed"
                eng.ui.error(err)
                eng.message_store.save_error(err)
                return None

        system_prompt, user_message = ClaudeAutoEngineer._build_auto_prompts(eng)
        auto_prompt = f"{system_prompt}\n\n{user_message}"
        eng.message_store.save_prompt(user_message)

        done_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        accumulated_text: list[str] = []

        def on_event(event: Any) -> None:
            event_type = event.type.value if hasattr(event.type, "value") else str(event.type)

            if event_type == "assistant.message_delta":
                delta = ""
                if hasattr(event, "data") and hasattr(event.data, "delta_content"):
                    delta = event.data.delta_content or ""
                if delta:
                    accumulated_text.append(delta)
                    eng.ui.thinking(delta)
            elif event_type == "assistant.message":
                if hasattr(event, "data") and hasattr(event.data, "usage"):
                    usage = event.data.usage
                    if isinstance(usage, dict):
                        eng.usage_metadata["input_tokens"] = usage.get("prompt_tokens", 0)
                        eng.usage_metadata["output_tokens"] = usage.get("completion_tokens", 0)
            elif event_type == "session.idle":
                # Use thread-safe call in case SDK invokes callback from a different thread
                loop.call_soon_threadsafe(done_event.set)

        client = None
        try:
            client = CopilotClient(
                {
                    "auto_start": True,
                    "use_logged_in_user": True,
                }
            )
            await client.start()

            if self.agent_provider == "chrome-mcp":
                chrome_args = ["-y", "chrome-devtools-mcp@latest", "--no-usage-statistics"]
                if self.headless:
                    chrome_args.append("--headless")
                else:
                    chrome_args.append("--autoConnect")
                mcp_servers_payload: dict[str, Any] = {
                    "chrome-devtools": {
                        "type": "local",
                        "command": "npx",
                        "args": chrome_args,
                        "tools": ["*"],
                        "timeout": 30000,
                    },
                }
            elif self.agent_provider == "agent-browser":
                mcp_servers_payload = {}
            else:
                pw_args = [
                    "-y",
                    "rae-playwright-mcp@latest",
                    "run-mcp-server",
                    "--run-id",
                    self.mcp_run_id,
                ]
                if self.headless:
                    pw_args.append("--headless")
                mcp_servers_payload = {
                    "playwright": {
                        "type": "local",
                        "command": "npx",
                        "args": pw_args,
                        "tools": ["*"],
                        "timeout": 30000,
                    },
                }

            async def on_pre_tool_use(input: dict, _invocation: dict) -> dict:
                tool_name = input.get("toolName", "unknown")
                tool_args = input.get("toolArgs") or {}
                eng.ui.tool_start(tool_name, tool_args)
                eng.message_store.save_tool_start(tool_name, tool_args)
                return {"permissionDecision": "allow", "modifiedArgs": tool_args}

            async def on_post_tool_use(input: dict, invocation: dict) -> dict:
                tool_name = input.get("toolName", "unknown")
                is_error = invocation.get("resultType") == "error" if isinstance(invocation, dict) else False
                output = invocation.get("result") if isinstance(invocation, dict) else None
                eng.ui.tool_result(tool_name, is_error=is_error, output=str(output) if output else None)
                eng.message_store.save_tool_result(tool_name, is_error, str(output) if output else None)
                return {}

            session = await client.create_session(
                {
                    "model": eng.copilot_model,
                    "streaming": True,
                    "infinite_sessions": {"enabled": True},
                    "mcp_servers": mcp_servers_payload,
                    "on_permission_request": PermissionHandler.approve_all,
                    "hooks": {
                        "on_pre_tool_use": on_pre_tool_use,
                        "on_post_tool_use": on_post_tool_use,
                    },
                }
            )

            session.on(on_event)
            await session.send({"prompt": auto_prompt})

            # Wait with timeout protection (10 minutes)
            try:
                await asyncio.wait_for(done_event.wait(), timeout=600)
            except TimeoutError:
                eng.ui.error("Session timed out (10 min)")
                eng.message_store.save_error("Session timed out")
                return None

            if accumulated_text:
                eng.message_store.save_thinking("".join(accumulated_text))

            script_path = str(eng.scripts_dir / eng._get_client_filename())
            local_path = str(eng.local_scripts_dir / eng._get_client_filename()) if eng.local_scripts_dir else None
            eng.ui.success(script_path, local_path)
            eng.usage_metadata["estimated_cost_usd"] = 0.0

            result: dict[str, Any] = {
                "script_path": script_path,
                "usage": eng.usage_metadata,
            }
            eng.message_store.save_result(result)
            return result

        except Exception as e:
            error_msg = str(e)
            eng.ui.error(error_msg)
            eng.message_store.save_error(error_msg)

            if "buffer size" in error_msg.lower() or "1048576" in error_msg or "exceeded maximum buffer" in error_msg.lower():
                eng.ui.console.print("\n[yellow]Screenshot too large (exceeds 1MB limit)[/yellow]")
                eng.ui.console.print("[dim]Tip: The AI should take element-specific screenshots instead of full-page screenshots.[/dim]")
            else:
                eng.ui.console.print("\n[dim]Make sure GitHub Copilot CLI is installed and you are logged in: gh auth login[/dim]")
            return None

        finally:
            # Always stop the client to avoid resource leaks
            if client is not None:
                try:
                    await client.stop()
                except Exception:
                    pass
