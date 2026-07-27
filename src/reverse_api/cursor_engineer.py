"""Cursor Agent SDK (TypeScript) via a Node subprocess bridge."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .agent_browser import ensure_agent_browser_runtime, print_agent_browser_setup_notices
from .base_engineer import BaseEngineer
from .tui import ClaudeUI

_BRIDGE_DIR = Path(__file__).resolve().parent / "cursor_bridge"
_BRIDGE_SCRIPT = _BRIDGE_DIR / "run.mjs"
_BRIDGE_LOCKFILE = _BRIDGE_DIR / "package-lock.json"
_SDK_MARKER = _BRIDGE_DIR / "node_modules" / "@cursor" / "sdk"
_BRIDGE_INSTALL_STAMP = _BRIDGE_DIR / "node_modules" / ".rae-package-lock.sha256"
_MIN_CURSOR_NODE_VERSION = (22, 13, 0)


def _bridge_lock_digest() -> str:
    return hashlib.sha256(_BRIDGE_LOCKFILE.read_bytes()).hexdigest()


def _cursor_node_version_error() -> str | None:
    node = shutil.which("node")
    if not node:
        return "node not found in PATH (Cursor SDK requires Node.js 22.13+)"
    try:
        result = subprocess.run(
            [node, "--version"],
            check=True,
            timeout=10,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        return f"failed to check Node.js version (Cursor SDK requires Node.js 22.13+): {e}"
    raw_version = result.stdout.strip()
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", raw_version)
    if not match:
        return f"could not parse Node.js version {raw_version!r} (Cursor SDK requires Node.js 22.13+)"
    version = tuple(int(part) for part in match.groups())
    if version < _MIN_CURSOR_NODE_VERSION:
        return f"Cursor SDK requires Node.js 22.13+; found Node.js {raw_version.lstrip('v')}"
    return None


def _ensure_cursor_bridge_deps() -> str | None:
    """Install npm dependencies for the bridge if missing. Returns error message or None."""
    if not _BRIDGE_SCRIPT.is_file():
        return "cursor bridge script missing (package incomplete)"
    if node_error := _cursor_node_version_error():
        return node_error
    try:
        lock_digest = _bridge_lock_digest()
    except OSError as e:
        return f"cursor bridge package-lock.json unavailable: {e}"
    if _SDK_MARKER.is_dir():
        try:
            if _BRIDGE_INSTALL_STAMP.read_text().strip() == lock_digest:
                return None
        except OSError:
            pass
    npm = shutil.which("npm")
    if not npm:
        return "npm not found in PATH (required to install @cursor/sdk for sdk=cursor)"
    try:
        subprocess.run(
            [npm, "install", "--no-fund", "--no-audit"],
            cwd=str(_BRIDGE_DIR),
            check=True,
            timeout=600,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or e.stdout or "")[-2000:]
        return f"npm install in cursor_bridge failed: {tail or e}"
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"npm install in cursor_bridge failed: {e}"
    if not _SDK_MARKER.is_dir():
        return "@cursor/sdk did not install under cursor_bridge/node_modules"
    try:
        _BRIDGE_INSTALL_STAMP.write_text(f"{_bridge_lock_digest()}\n")
    except OSError as e:
        return f"failed to record cursor bridge dependency state: {e}"
    return None


class CursorStreamUI(ClaudeUI):
    """Routes `.thinking()` into the Cursor buffer so nothing prints token-sized `..` lines."""

    def __init__(self, engineer: CursorEngineer, **kwargs: Any):
        super().__init__(**kwargs)
        self._eng = engineer

    def thinking(self, text: str, max_length: int = 500) -> None:
        _ = max_length
        if text:
            self._eng._cursor_feed_thinking(text)


class CursorEngineer(BaseEngineer):
    """Reverse engineering using Cursor's TypeScript agent SDK (Node subprocess)."""

    def __init__(
        self,
        run_id: str,
        har_path: Any,
        prompt: str,
        model: str | None = None,
        cursor_model: str | None = None,
        cursor_web_search: bool = True,
        cursor_setting_sources: list[str] | None = None,
        **kwargs: Any,
    ):
        cm = cursor_model or model or "composer-2.5"
        super().__init__(run_id=run_id, har_path=har_path, prompt=prompt, model=cm, **kwargs)
        self.cursor_model = cm
        self.cursor_web_search = cursor_web_search
        self.cursor_setting_sources = cursor_setting_sources
        vb = self.ui.verbose
        self.ui = CursorStreamUI(self, verbose=vb)
        self._cursor_thinking_acc = ""
        self._cursor_assistant_acc = ""
        # Cursor streams several `tool_call`/running deltas per call as the args
        # fill in; track which call_ids we've already announced so the UI and
        # json-stream emit exactly one tool_start per logical call.
        self._cursor_started_calls: set[str] = set()

    @staticmethod
    def _cursor_coerce_args(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw.strip().startswith("{"):
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    def _cursor_emit_todo_ui(self, name: str, args: dict[str, Any]) -> None:
        if "todo" not in name.lower():
            return
        todos = args.get("todos")
        if not isinstance(todos, list) or not todos:
            return
        self.ui.todo_updated(todos)
        self.message_store.save_todos(todos)

    def _workspace_cwd(self) -> str:
        return str(self.scripts_dir.parent.parent)

    def _merge_usage_from_bridge(self, usage: dict[str, Any] | None) -> None:
        if not usage:
            return
        for key in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
            if key in usage and isinstance(usage[key], (int, float)):
                self.usage_metadata[key] = self.usage_metadata.get(key, 0) + int(usage[key])

    def _cursor_reset_stream_buffers(self) -> None:
        self._cursor_thinking_acc = ""
        self._cursor_assistant_acc = ""
        # Each turn is a fresh agent stream; clear announced call IDs so a turn
        # interrupted before a tool's terminal event can't leave stale IDs that
        # suppress tool_start on a later turn (and so the set can't grow forever).
        self._cursor_started_calls.clear()

    def _cursor_feed_thinking(self, fragment: str) -> None:
        self._cursor_thinking_acc += fragment

    def _cursor_feed_assistant(self, text: str) -> None:
        """Merge assistant snapshots (Cursor often sends growing full-message text)."""
        if not text:
            return
        old = self._cursor_assistant_acc
        if not old.strip():
            self._cursor_assistant_acc = text
            return
        if text.startswith(old):
            self._cursor_assistant_acc = text
            return
        self._cursor_assistant_acc = old + text

    def _cursor_narrative_nonempty(self) -> bool:
        return bool(self._cursor_thinking_acc.strip() or self._cursor_assistant_acc.strip())

    def _cursor_flush_narrative(self) -> None:
        """Emit accumulated model text as one UI block + one message_store entry."""
        parts: list[str] = []
        if self._cursor_thinking_acc.strip():
            parts.append(self._cursor_thinking_acc.strip())
        if self._cursor_assistant_acc.strip():
            parts.append(self._cursor_assistant_acc.strip())
        combined = "\n\n".join(parts)
        if not combined:
            return
        self.ui.thinking_block(combined)
        self.message_store.save_thinking(combined)
        self._cursor_thinking_acc = ""
        self._cursor_assistant_acc = ""

    async def _dispatch_stream_event(self, event: dict[str, Any]) -> None:
        et = str(event.get("type") or "").lower()
        if et == "thinking" and event.get("text"):
            self._cursor_feed_thinking(str(event["text"]))
        elif et == "assistant" and event.get("text"):
            self._cursor_feed_assistant(str(event["text"]))
        elif et == "tool_call":
            name = str(event.get("name") or "tool")
            status = event.get("status")
            call_id = event.get("callId") or event.get("call_id")
            if status == "running":
                args = self._cursor_coerce_args(event.get("args"))
                # Live todo board reflects the latest snapshot on every delta;
                # this is a TUI-only render and never reaches the json-stream.
                self._cursor_emit_todo_ui(name, args)
                # Announce the tool exactly once, on the first running delta.
                if call_id and call_id in self._cursor_started_calls:
                    return
                if call_id:
                    self._cursor_started_calls.add(call_id)
                self._cursor_flush_narrative()
                if not self.interactive and self._is_ask_user_tool_name(name):
                    self._emit_json_event({"event": "ask_user_skipped", "count": 1, "tool": name})
                    self.ui.console.print(
                        f"  [dim]AskUserQuestion skipped ({name}; non-interactive mode)[/dim]"
                    )
                self.ui.tool_start(name, args, call_id=call_id)
                self.message_store.save_tool_start(name, args)
            else:
                is_err = status == "error"
                res = event.get("result")
                out = str(res) if res is not None else None
                self.ui.tool_result(name, is_err, out, call_id=call_id)
                self.message_store.save_tool_result(name, is_err, out)
                if call_id:
                    self._cursor_started_calls.discard(call_id)

    async def _one_turn(  # noqa: C901 - subprocess + NDJSON; splitting obscures control flow
        self,
        prompt: str,
        *,
        mcp_servers: dict[str, Any] | None,
        resume_agent_id: str | None,
    ) -> dict[str, Any]:
        api_key = os.environ.get("CURSOR_API_KEY", "")
        req: dict[str, Any] = {
            "cwd": self._workspace_cwd(),
            "modelId": self.cursor_model,
            "prompt": prompt,
        }
        if api_key:
            req["apiKey"] = api_key
        if mcp_servers:
            req["mcpServers"] = mcp_servers
        if resume_agent_id:
            req["resumeAgentId"] = resume_agent_id
        if isinstance(self.cursor_setting_sources, list) and self.cursor_setting_sources:
            req["settingSources"] = [str(x) for x in self.cursor_setting_sources]
        else:
            req["cursorWebSearch"] = bool(self.cursor_web_search)

        pre = _ensure_cursor_bridge_deps()
        if pre:
            return {"error": pre}

        node_exe = shutil.which("node")
        if not node_exe:
            return {"error": "node not found in PATH"}

        self._cursor_reset_stream_buffers()

        proc = await asyncio.create_subprocess_exec(
            node_exe,
            str(_BRIDGE_SCRIPT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(_BRIDGE_DIR),
            env=os.environ.copy(),
        )

        stderr_acc = bytearray()

        async def _pump_stderr() -> None:
            if proc.stderr is None:
                return
            try:
                while True:
                    chunk = await proc.stderr.read(65536)
                    if not chunk:
                        break
                    stderr_acc.extend(chunk)
            except Exception:
                return

        if proc.stdin:
            proc.stdin.write(json.dumps(req).encode("utf-8"))
            await proc.stdin.drain()
            proc.stdin.close()

        assert proc.stdout is not None
        stderr_task = asyncio.create_task(_pump_stderr())
        ret: dict[str, Any] | None = None
        try:
            while True:
                try:
                    line_b = await asyncio.wait_for(proc.stdout.readline(), timeout=900.0)
                except TimeoutError:
                    ret = {"error": "cursor bridge: no stdout for 15 minutes (timed out)"}
                    break
                if not line_b:
                    if ret is None:
                        err_t = stderr_acc.decode("utf-8", errors="replace").strip()
                        rc = proc.returncode
                        if rc is None:
                            try:
                                await asyncio.wait_for(proc.wait(), timeout=5.0)
                            except Exception:
                                pass
                            rc = proc.returncode
                        ret = {"error": err_t or f"cursor bridge stdout closed (exit {rc})"}
                    break
                line = line_b.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = obj.get("type")
                if t == "stream" and isinstance(obj.get("event"), dict):
                    await self._dispatch_stream_event(obj["event"])
                elif t == "agent":
                    pass
                elif t == "done":
                    run_result = obj.get("runResult") or {}
                    if run_result.get("status") == "error":
                        ret = {"error": str(run_result.get("result") or "run error")}
                        break
                    self._merge_usage_from_bridge(obj.get("usage"))
                    had_narrative = self._cursor_narrative_nonempty()
                    self._cursor_flush_narrative()
                    rr = run_result.get("result")
                    if isinstance(rr, str) and rr.strip() and not had_narrative:
                        self.ui.thinking_block(rr)
                        self.message_store.save_thinking(rr)
                    ret = {"ok": True, "agentId": obj.get("agentId")}
                    break
                elif t == "error":
                    msg = str(obj.get("message") or "bridge error")
                    extra = stderr_acc.decode("utf-8", errors="replace").strip()
                    if extra:
                        msg = f"{msg}\n{extra}"
                    ret = {"error": msg}
                    break
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if ret is None:
                ret = {"error": str(e)}
        finally:
            try:
                await asyncio.wait_for(proc.wait(), timeout=120.0)
            except TimeoutError:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=15.0)
                except (ProcessLookupError, TimeoutError):
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
                    try:
                        await proc.wait()
                    except Exception:
                        pass
            try:
                await asyncio.wait_for(stderr_task, timeout=10.0)
            except Exception:
                stderr_task.cancel()
                try:
                    await stderr_task
                except asyncio.CancelledError:
                    pass

        if ret is None:
            err_t = stderr_acc.decode("utf-8", errors="replace").strip()
            ret = {"error": err_t or "cursor bridge produced no result"}

        if ret.get("ok"):
            code = proc.returncode
            if code not in (None, 0):
                err_t = stderr_acc.decode("utf-8", errors="replace").strip()
                return {"error": err_t or f"cursor bridge exited with code {code}"}
        return ret

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        self.ui.header(self.run_id, self.prompt, self.cursor_model, self.sdk, mode="engineer")
        self.ui.start_analysis()

        dep_err = _ensure_cursor_bridge_deps()
        if dep_err:
            self.ui.error(dep_err)
            self.message_store.save_error(dep_err)
            self.ui.console.print("\n[dim]Set CURSOR_API_KEY and ensure Node.js 22.13+ and npm are installed.[/dim]")
            return None

        if not os.environ.get("CURSOR_API_KEY"):
            msg = "CURSOR_API_KEY is not set"
            self.ui.error(msg)
            self.message_store.save_error(msg)
            self.ui.console.print("\n[dim]Create an API key at https://cursor.com/dashboard/integrations[/dim]")
            return None

        system_prompt, user_message = self._build_prompts()
        self.message_store.save_prompt(user_message)
        combined = f"{system_prompt}\n\n{user_message}"

        agent_id: str | None = None
        last_result: dict[str, Any] | None = None
        turn_prompt: str = combined

        try:
            while True:
                res = await self._one_turn(
                    turn_prompt,
                    mcp_servers=None,
                    resume_agent_id=agent_id,
                )
                if res.get("error"):
                    self.ui.error(str(res["error"]))
                    self.message_store.save_error(str(res["error"]))
                    return None

                aid = res.get("agentId")
                if isinstance(aid, str) and aid:
                    agent_id = aid

                script_path = str(self.scripts_dir / self._get_client_filename())
                local_path = str(self.local_scripts_dir / self._get_client_filename()) if self.local_scripts_dir else None
                self.ui.success(script_path, local_path)

                self.usage_metadata.setdefault("estimated_cost_usd", 0.0)
                self.ui.console.print("  [dim]Usage (Cursor SDK): see dashboard — token counts are best-effort[/dim]")
                it = self.usage_metadata.get("input_tokens", 0)
                ot = self.usage_metadata.get("output_tokens", 0)
                if it or ot:
                    self.ui.console.print(f"  [dim]  input: {it:,} / output: {ot:,} tokens (approx.)[/dim]")

                last_result = {
                    "script_path": script_path,
                    "usage": self.usage_metadata,
                }
                self.message_store.save_result(last_result)

                if not self.interactive:
                    return last_result

                follow = await self._prompt_follow_up()
                if not follow:
                    return last_result
                turn_prompt = follow
                self.message_store.save_prompt(turn_prompt)
        except KeyboardInterrupt:
            self.ui.console.print("\n  [dim]run aborted[/dim]")
            return last_result


class CursorAutoEngineer(CursorEngineer):
    """Agent capture using Cursor SDK—browser via MCP for auto/chrome-mcp or Vercel agent-browser CLI prompts for agent-browser."""

    def __init__(
        self,
        run_id: str,
        prompt: str,
        output_dir: str | None = None,
        agent_provider: str = "auto",
        **kwargs: Any,
    ):
        headless = kwargs.pop("headless", False)
        from .utils import get_har_dir

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
        self.headless = headless

    def _cursor_mcp_servers(self) -> dict[str, Any]:
        if self.agent_provider == "agent-browser":
            return {}
        if self.agent_provider == "chrome-mcp":
            args = ["-y", "chrome-devtools-mcp@latest", "--no-usage-statistics"]
            if self.headless:
                args.append("--headless")
            else:
                args.append("--autoConnect")
            return {
                "chrome-devtools": {
                    "type": "stdio",
                    "command": "npx",
                    "args": args,
                },
            }
        playwright_args = [
            "-y",
            "rae-playwright-mcp@latest",
            "run-mcp-server",
            "--run-id",
            self.mcp_run_id,
        ]
        if self.headless:
            playwright_args.append("--headless")
        return {
            "playwright": {
                "type": "stdio",
                "command": "npx",
                "args": playwright_args,
            },
        }

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        from .auto_engineer import ClaudeAutoEngineer

        self.ui.header(self.run_id, self.prompt, self.cursor_model, self.sdk, mode="agent")
        self.ui.start_analysis()

        dep_err = _ensure_cursor_bridge_deps()
        if dep_err:
            self.ui.error(dep_err)
            self.message_store.save_error(dep_err)
            return None

        if not os.environ.get("CURSOR_API_KEY"):
            msg = "CURSOR_API_KEY is not set"
            self.ui.error(msg)
            self.message_store.save_error(msg)
            self.ui.console.print("\n[dim]Create an API key at https://cursor.com/dashboard/integrations[/dim]")
            return None

        if self.agent_provider == "agent-browser":
            ab_setup = ensure_agent_browser_runtime()
            print_agent_browser_setup_notices(self.ui.console, ab_setup)
            if not ab_setup.ok:
                err = ab_setup.error or "agent-browser setup failed"
                self.ui.error(err)
                self.message_store.save_error(err)
                return None

        system_prompt, user_message = ClaudeAutoEngineer._build_auto_prompts(self)
        self.message_store.save_prompt(user_message)
        combined = f"{system_prompt}\n\n{user_message}"

        mcp = self._cursor_mcp_servers()
        agent_id: str | None = None
        last_result: dict[str, Any] | None = None
        turn_prompt: str = combined

        try:
            while True:
                res = await self._one_turn(
                    turn_prompt,
                    mcp_servers=mcp,
                    resume_agent_id=agent_id,
                )
                if res.get("error"):
                    self.ui.error(str(res["error"]))
                    self.message_store.save_error(str(res["error"]))
                    return None

                aid = res.get("agentId")
                if isinstance(aid, str) and aid:
                    agent_id = aid

                script_path = str(self.scripts_dir / self._get_client_filename())
                local_path = str(self.local_scripts_dir / self._get_client_filename()) if self.local_scripts_dir else None
                self.ui.success(script_path, local_path)
                self.usage_metadata.setdefault("estimated_cost_usd", 0.0)

                last_result = {"script_path": script_path, "usage": self.usage_metadata}
                self.message_store.save_result(last_result)

                if not self.interactive:
                    return last_result

                fu = await self._prompt_follow_up()
                if not fu:
                    return last_result
                turn_prompt = fu
                self.message_store.save_prompt(turn_prompt)
        except KeyboardInterrupt:
            self.ui.console.print("\n  [dim]run aborted[/dim]")
            return last_result
