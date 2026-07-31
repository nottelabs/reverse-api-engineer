"""Real MCP client/server round-trips — the dependency-bump canary.

The engineer's verification tool and the whole agent backend ride on
claude-agent-sdk -> mcp -> (starlette, sse-starlette, uvicorn, httpx).
The unit suite mocks all of that away, which is exactly how a breaking
transitive bump (e.g. a Starlette major) could pass 800+ tests and still
break at runtime. These tests connect a genuine mcp ClientSession to a
genuine mcp Server over both transports the stack uses:

- in-memory: the SDK-server path ClaudeSDKClient actually wires up for
  report_client_verified during a session;
- streamable HTTP: the only path that loads starlette/uvicorn for real,
  so a Starlette-incompatible mcp release fails here, not in the field.
"""

import socket
import threading

import anyio
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from reverse_api.engineer import ClaudeEngineer


def _make_engineer(tmp_path) -> ClaudeEngineer:
    return ClaudeEngineer(
        run_id="mcpcanary",
        har_path=tmp_path / "recording.har",
        prompt="integration canary",
        output_dir=str(tmp_path),
        verbose=False,
        interactive=False,
    )


async def test_verification_server_roundtrip_over_real_client(tmp_path):
    """Drive report_client_verified through a real mcp ClientSession.

    Covers the exact Server instance create_sdk_mcp_server hands to the
    Claude SDK, including the once-per-session guard and the
    client_executed json-stream event — behaviors the unit tests only
    reach by calling the handler directly.
    """
    engineer = _make_engineer(tmp_path)
    events: list[dict] = []
    engineer._json_event_sink = events.append

    server_config = engineer._build_verification_mcp_server()
    assert server_config["type"] == "sdk"

    async with create_connected_server_and_client_session(server_config["instance"]) as session:
        tools = await session.list_tools()
        assert [t.name for t in tools.tools] == ["report_client_verified"]

        first = await session.call_tool("report_client_verified", {"summary": "ran the client live"})
        assert not first.isError
        assert "Recorded" in first.content[0].text

        second = await session.call_tool("report_client_verified", {"summary": "again"})
        assert "Already recorded" in second.content[0].text

    assert [e["event"] for e in events] == ["client_executed"]
    assert events[0]["script_path"].endswith("api_client.py")


async def test_streamable_http_transport_roundtrip():
    """Full client<->server exchange over mcp's streamable-HTTP transport.

    This is the one test in the repo that actually runs Starlette under
    uvicorn and speaks to it with mcp's httpx-based client, so it fails
    loudly if a starlette/sse-starlette/uvicorn/mcp bump breaks the wire
    protocol or the ASGI surface.
    """
    mcp_server = FastMCP("canary")

    @mcp_server.tool()
    def echo(text: str) -> str:
        return f"echo:{text}"

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    config = uvicorn.Config(mcp_server.streamable_http_app(), host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    # uvicorn owns its own event loop in a daemon thread; the test's loop
    # stays free to run the client side of the exchange.
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if server.started:
                break
            await anyio.sleep(0.05)
        else:
            pytest.fail("uvicorn did not start within 10s")

        async with streamable_http_client(f"http://127.0.0.1:{port}/mcp") as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert [t.name for t in tools.tools] == ["echo"]
                result = await session.call_tool("echo", {"text": "hi"})
                assert not result.isError
                assert result.content[0].text == "echo:hi"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
