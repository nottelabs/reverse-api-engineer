"""Tests for opencode_engineer.py - OpenCodeEngineer and helpers."""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2 as httpx
import pytest

from reverse_api.opencode_engineer import (
    DEBUG,
    OpenCodeEngineer,
    debug_log,
    format_error,
    run_opencode_engineering,
)


def _valid_catalog_response() -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "default": {"opencode": "big-pickle"},
        "providers": [
            {
                "id": "opencode",
                "models": {
                    "big-pickle": {
                        "status": "active",
                        "capabilities": {"toolcall": True},
                    }
                },
            },
            {
                "id": "anthropic",
                "models": {
                    "claude-opus-4-6": {
                        "status": "active",
                        "capabilities": {"toolcall": True},
                    }
                },
            }
        ],
    }
    return response


class TestDebugLog:
    """Test debug_log function."""

    def test_debug_disabled(self, capsys):
        """No output when DEBUG is disabled."""
        with patch("reverse_api.opencode_engineer.DEBUG", False):
            debug_log("test message")
            captured = capsys.readouterr()
            assert captured.out == ""

    def test_debug_enabled(self, capsys):
        """Output when DEBUG is enabled."""
        with patch("reverse_api.opencode_engineer.DEBUG", True):
            debug_log("test message")
            captured = capsys.readouterr()
            assert "test message" in captured.out
            assert "[DEBUG]" in captured.out


class TestFormatError:
    """Test format_error function."""

    def test_basic_exception(self):
        """Formats basic exception."""
        e = Exception("something went wrong")
        result = format_error(e)
        assert "Exception" in result
        assert "something went wrong" in result

    def test_empty_message(self):
        """Formats exception with empty message."""
        e = Exception()
        result = format_error(e)
        assert "no message" in result

    def test_http_status_error(self):
        """Formats HTTP status error."""
        response = MagicMock()
        response.status_code = 500
        response.reason_phrase = "Internal Server Error"
        response.json.return_value = {"error": "server error"}
        e = httpx.HTTPStatusError("error", request=MagicMock(), response=response)
        result = format_error(e)
        assert "500" in result

    def test_http_status_error_non_json(self):
        """Formats HTTP error with non-JSON response."""
        response = MagicMock()
        response.status_code = 500
        response.reason_phrase = "Error"
        response.json.side_effect = ValueError("not json")
        response.text = "plain text error"
        e = httpx.HTTPStatusError("error", request=MagicMock(), response=response)
        result = format_error(e)
        assert "500" in result

    def test_http_status_error_empty_response_text(self):
        """Formats HTTP error with empty response text."""
        response = MagicMock()
        response.status_code = 500
        response.reason_phrase = "Error"
        response.json.side_effect = ValueError("not json")
        response.text = ""
        e = httpx.HTTPStatusError("error", request=MagicMock(), response=response)
        result = format_error(e)
        assert "500" in result

    def test_connect_error(self):
        """Formats connect error."""
        e = httpx.ConnectError("Connection refused")
        result = format_error(e)
        assert "ConnectError" in result

    def test_read_error(self):
        """Formats read error."""
        e = httpx.ReadError("Connection reset")
        result = format_error(e)
        assert "ReadError" in result

    def test_timeout_error(self):
        """Formats timeout error."""
        e = httpx.TimeoutException("Request timed out")
        result = format_error(e)
        assert "TimeoutException" in result

    def test_debug_mode_includes_traceback(self):
        """Debug mode includes traceback."""
        with patch("reverse_api.opencode_engineer.DEBUG", True):
            try:
                raise ValueError("test error")
            except ValueError as e:
                result = format_error(e)
                assert "Traceback" in result

    def test_http_error_with_json_body(self):
        """HTTP error with JSON body shows response content."""
        response = MagicMock()
        response.status_code = 422
        response.reason_phrase = "Unprocessable Entity"
        response.json.return_value = {"detail": "Validation error", "field": "name"}
        e = httpx.HTTPStatusError("error", request=MagicMock(), response=response)
        result = format_error(e)
        assert "422" in result
        assert "Unprocessable Entity" in result

    def test_connect_error_with_connection_refused(self):
        """Connect error with 'Connection refused' in message."""
        e = httpx.ConnectError("Connection refused")
        result = format_error(e)
        assert "Unable to connect" in result

    def test_connect_error_with_other_message(self):
        """Connect error with non-refused message shows details."""
        e = httpx.ConnectError("DNS resolution failed")
        result = format_error(e)
        assert "DNS resolution failed" in result

    def test_http_status_error_response_access_fails(self):
        """HTTP status error where response access raises."""
        response = MagicMock()
        type(response).status_code = property(lambda self: (_ for _ in ()).throw(RuntimeError("oops")))
        e = httpx.HTTPStatusError("error", request=MagicMock(), response=response)
        result = format_error(e)
        assert "HTTPStatusError" in result


class TestOpenCodeEngineerModelMap:
    """Test OpenCodeEngineer MODEL_MAP."""

    def test_model_map(self):
        """MODEL_MAP has expected entries."""
        assert OpenCodeEngineer.MODEL_MAP["sonnet"] == "claude-sonnet-4-6"
        assert OpenCodeEngineer.MODEL_MAP["opus"] == "claude-opus-4-6"
        assert OpenCodeEngineer.MODEL_MAP["haiku"] == "claude-haiku-4-5"


class TestOpenCodeEngineerInit:
    """Test OpenCodeEngineer initialization."""

    def test_init(self, tmp_path):
        """Initializes with OpenCode-specific attributes."""
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.MessageStore"):
                with patch("reverse_api.opencode_engineer.OpenCodeUI"):
                    eng = OpenCodeEngineer(
                        run_id="test123",
                        har_path=har_path,
                        prompt="test prompt",
                        output_dir=str(tmp_path),
                        opencode_provider="anthropic",
                        opencode_model="claude-opus-4-6",
                    )
                    assert eng.opencode_provider == "anthropic"
                    assert eng.opencode_model == "claude-opus-4-6"
                    assert eng._session_id is None

    def test_init_default_opencode_kwargs(self, tmp_path):
        """Default OpenCode kwargs."""
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.MessageStore"):
                with patch("reverse_api.opencode_engineer.OpenCodeUI"):
                    eng = OpenCodeEngineer(
                        run_id="test123",
                        har_path=har_path,
                        prompt="test prompt",
                        output_dir=str(tmp_path),
                    )
                    assert eng.opencode_provider == "opencode"
                    assert eng.opencode_model == "big-pickle"


class TestOpenCodeEngineerAuth:
    """Test authentication handling."""

    def _make_engineer(self, tmp_path, **env_vars):
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.MessageStore"):
                with patch("reverse_api.opencode_engineer.OpenCodeUI"):
                    with patch.dict(os.environ, env_vars, clear=False):
                        return OpenCodeEngineer(
                            run_id="test123",
                            har_path=har_path,
                            prompt="test prompt",
                            output_dir=str(tmp_path),
                        )

    def test_no_auth(self, tmp_path):
        """No auth when no password set."""
        eng = self._make_engineer(tmp_path)
        assert eng._get_auth() is None

    def test_with_password(self, tmp_path):
        """Auth with password."""
        eng = self._make_engineer(tmp_path, OPENCODE_SERVER_PASSWORD="secret123")
        auth = eng._get_auth()
        assert auth is not None

    def test_custom_username(self, tmp_path):
        """Custom username."""
        eng = self._make_engineer(
            tmp_path,
            OPENCODE_SERVER_PASSWORD="secret",
            OPENCODE_SERVER_USERNAME="admin",
        )
        assert eng.opencode_username == "admin"


class TestOpenCodeEngineerHandlePartUpdate:
    """Test _handle_part_update method."""

    def _make_engineer(self, tmp_path):
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.MessageStore") as mock_ms:
                mock_ms_instance = MagicMock()
                mock_ms.return_value = mock_ms_instance
                with patch("reverse_api.opencode_engineer.OpenCodeUI") as mock_ui:
                    mock_ui_instance = MagicMock()
                    mock_ui.return_value = mock_ui_instance
                    eng = OpenCodeEngineer(
                        run_id="test123",
                        har_path=har_path,
                        prompt="test prompt",
                        output_dir=str(tmp_path),
                    )
                    eng._session_id = "session_abc"
                    eng._assistant_message_ids.add("message_assistant")
                    return eng

    @pytest.mark.asyncio
    async def test_text_part(self, tmp_path):
        """Text part updates UI."""
        eng = self._make_engineer(tmp_path)
        seen_parts = set()
        properties = {
            "part": {
                "id": "part1",
                "type": "text",
                "text": "x" * 100,
                "sessionID": "session_abc",
                "messageID": "message_assistant",
            },
            "delta": None,
        }
        await eng._handle_part_update(properties, seen_parts)
        eng.opencode_ui.update_text.assert_called_once()
        assert "part1" in seen_parts

    @pytest.mark.asyncio
    async def test_text_part_short_not_saved(self, tmp_path):
        """Short text part is not saved to message store."""
        eng = self._make_engineer(tmp_path)
        seen_parts = set()
        properties = {
            "part": {
                "id": "part1",
                "type": "text",
                "text": "ok",
                "sessionID": "session_abc",
                "messageID": "message_assistant",
            },
            "delta": None,
        }
        await eng._handle_part_update(properties, seen_parts)
        eng.message_store.save_thinking.assert_not_called()

    @pytest.mark.asyncio
    async def test_user_text_part_is_not_rendered(self, tmp_path):
        """The submitted internal prompt must not appear as assistant output."""
        eng = self._make_engineer(tmp_path)
        properties = {
            "part": {
                "id": "part-user",
                "messageID": "message_user",
                "type": "text",
                "text": "There is no HAR file — capture all network data.",
                "sessionID": "session_abc",
            }
        }

        await eng._handle_part_update(properties, set())

        eng.opencode_ui.update_text.assert_not_called()
        eng.message_store.save_thinking.assert_not_called()

    @pytest.mark.asyncio
    async def test_tool_running(self, tmp_path):
        """Running tool part starts tool in UI."""
        eng = self._make_engineer(tmp_path)
        seen_parts = set()
        properties = {
            "part": {
                "id": "tool1",
                "type": "tool",
                "tool": "Read",
                "sessionID": "session_abc",
                "state": {"status": "running", "input": {"file_path": "/test.py"}},
            },
        }
        await eng._handle_part_update(properties, seen_parts)
        eng.opencode_ui.tool_start.assert_called_once_with("Read", {"file_path": "/test.py"})
        assert "tool1" in seen_parts

    @pytest.mark.asyncio
    async def test_tool_completed(self, tmp_path):
        """Completed tool part shows result."""
        eng = self._make_engineer(tmp_path)
        seen_parts = set()
        properties = {
            "part": {
                "id": "tool1",
                "type": "tool",
                "tool": "Read",
                "sessionID": "session_abc",
                "state": {"status": "completed", "output": "file content"},
            },
        }
        await eng._handle_part_update(properties, seen_parts)
        eng.opencode_ui.tool_result.assert_called_once_with("Read", False, "file content")

    @pytest.mark.asyncio
    async def test_tool_error(self, tmp_path):
        """Error tool part shows error."""
        eng = self._make_engineer(tmp_path)
        seen_parts = set()
        properties = {
            "part": {
                "id": "tool1",
                "type": "tool",
                "tool": "Bash",
                "sessionID": "session_abc",
                "state": {"status": "error", "error": "command failed"},
            },
        }
        await eng._handle_part_update(properties, seen_parts)
        eng.opencode_ui.tool_result.assert_called_once_with("Bash", True, "command failed")

    @pytest.mark.asyncio
    async def test_step_finish(self, tmp_path):
        """Step finish updates usage metadata."""
        eng = self._make_engineer(tmp_path)
        seen_parts = set()
        properties = {
            "part": {
                "id": "step1",
                "type": "step-finish",
                "cost": 0.05,
                "tokens": {
                    "input": 1000,
                    "output": 500,
                    "reasoning": 200,
                    "cache": {"read": 100, "write": 50},
                },
                "sessionID": "session_abc",
            },
        }
        await eng._handle_part_update(properties, seen_parts)
        assert eng.usage_metadata["input_tokens"] == 1000
        assert eng.usage_metadata["output_tokens"] == 500
        assert eng.usage_metadata["reasoning_tokens"] == 200
        assert eng.usage_metadata["cache_read_tokens"] == 100
        assert eng.usage_metadata["cache_creation_tokens"] == 50
        assert eng.usage_metadata["cost"] == 0.05

    @pytest.mark.asyncio
    async def test_step_finish_calculates_cost_when_zero(self, tmp_path):
        """Step finish calculates cost locally when API returns 0."""
        eng = self._make_engineer(tmp_path)
        seen_parts = set()
        properties = {
            "part": {
                "id": "step1",
                "type": "step-finish",
                "cost": 0,
                "tokens": {
                    "input": 1000,
                    "output": 500,
                    "reasoning": 0,
                    "cache": {"read": 0, "write": 0},
                },
                "sessionID": "session_abc",
            },
        }
        await eng._handle_part_update(properties, seen_parts)
        assert eng.usage_metadata["cost"] > 0  # Should have calculated locally

    @pytest.mark.asyncio
    async def test_wrong_session_ignored(self, tmp_path):
        """Parts for other sessions are ignored."""
        eng = self._make_engineer(tmp_path)
        seen_parts = set()
        properties = {
            "part": {
                "id": "part1",
                "type": "text",
                "text": "ignored",
                "sessionID": "other_session",
            },
        }
        await eng._handle_part_update(properties, seen_parts)
        eng.opencode_ui.update_text.assert_not_called()


class TestOpenCodeEngineerStreamEvents:
    """Test _stream_events method."""

    def _make_engineer(self, tmp_path):
        har_path = tmp_path / "test.har"
        har_path.touch()
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.MessageStore") as mock_ms:
                mock_ms.return_value = MagicMock()
                with patch("reverse_api.opencode_engineer.OpenCodeUI") as mock_ui:
                    mock_ui.return_value = MagicMock()
                    eng = OpenCodeEngineer(
                        run_id="test123",
                        har_path=har_path,
                        prompt="test prompt",
                        output_dir=str(tmp_path),
                    )
                    eng._session_id = "session_abc"
                    return eng

    @pytest.mark.asyncio
    async def test_session_idle_event(self, tmp_path):
        """session.idle event ends streaming."""
        eng = self._make_engineer(tmp_path)

        lines = [
            'data: {"type":"session.idle","properties":{"sessionID":"session_abc"}}',
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        mock_client = AsyncMock()
        mock_client.stream = MagicMock()

        # Use async context manager mock
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream.return_value = cm

        await eng._stream_events(mock_client)
        eng.opencode_ui.session_status.assert_called_with("idle")

    @pytest.mark.asyncio
    async def test_session_status_idle(self, tmp_path):
        """session.status with idle type ends streaming."""
        eng = self._make_engineer(tmp_path)

        lines = [
            'data: {"type":"session.status","properties":{"sessionID":"session_abc","status":{"type":"idle"}}}',
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        await eng._stream_events(mock_client)

    @pytest.mark.asyncio
    async def test_session_status_retry(self, tmp_path):
        """session.status with retry type calls retry UI."""
        eng = self._make_engineer(tmp_path)

        lines = [
            'data: {"type":"session.status","properties":{"sessionID":"session_abc","status":{"type":"retry","attempt":2,"message":"Rate limited"}}}',
            'data: {"type":"session.idle","properties":{"sessionID":"session_abc"}}',
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        await eng._stream_events(mock_client)
        eng.opencode_ui.session_retry.assert_called_with(2, "Rate limited")

    @pytest.mark.asyncio
    async def test_permission_updated_event(self, tmp_path):
        """permission.updated event auto-approves."""
        eng = self._make_engineer(tmp_path)

        lines = [
            'data: {"type":"permission.updated","properties":{"id":"perm1","sessionID":"session_abc","type":"write","title":"Write file"}}',
            'data: {"type":"session.idle","properties":{"sessionID":"session_abc"}}',
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)
        mock_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        await eng._stream_events(mock_client)
        eng.opencode_ui.permission_requested.assert_called_with("write", "Write file")
        eng.opencode_ui.permission_approved.assert_called_with("write")

    @pytest.mark.asyncio
    async def test_permission_v2_event_uses_current_reply_endpoint(self, tmp_path):
        """OpenCode 1.18 permission.v2 events use the non-deprecated endpoint."""
        eng = self._make_engineer(tmp_path)

        lines = [
            (
                'data: {"type":"permission.v2.asked","properties":{"id":"per_1","sessionID":"session_abc",'
                '"action":"write","resources":["/tmp/client.py"]}}'
            ),
            'data: {"type":"session.idle","properties":{"sessionID":"session_abc"}}',
        ]
        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines
        stream = AsyncMock()
        stream.__aenter__ = AsyncMock(return_value=mock_response)
        stream.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=stream)
        mock_client.post = AsyncMock(return_value=MagicMock(status_code=204))

        await eng._stream_events(mock_client)

        mock_client.post.assert_awaited_once_with(
            "/api/session/session_abc/permission/per_1/reply",
            json={"reply": "always"},
        )
        eng.opencode_ui.permission_requested.assert_called_once_with("write", "/tmp/client.py")
        eng.opencode_ui.permission_approved.assert_called_once_with("write")

    @pytest.mark.asyncio
    async def test_todo_updated_event(self, tmp_path):
        """todo.updated event updates UI."""
        eng = self._make_engineer(tmp_path)

        lines = [
            'data: {"type":"todo.updated","properties":{"sessionID":"session_abc","todos":[{"text":"Do X"}]}}',
            'data: {"type":"session.idle","properties":{"sessionID":"session_abc"}}',
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        await eng._stream_events(mock_client)
        eng.opencode_ui.todo_updated.assert_called_once()

    @pytest.mark.asyncio
    async def test_file_edited_event(self, tmp_path):
        """file.edited event updates UI."""
        eng = self._make_engineer(tmp_path)

        lines = [
            'data: {"type":"file.edited","properties":{"file":"/test.py"}}',
            'data: {"type":"session.idle","properties":{"sessionID":"session_abc"}}',
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        await eng._stream_events(mock_client)
        eng.opencode_ui.file_edited.assert_called_with("/test.py")

    @pytest.mark.asyncio
    async def test_session_diff_event(self, tmp_path):
        """session.diff event updates UI."""
        eng = self._make_engineer(tmp_path)

        lines = [
            'data: {"type":"session.diff","properties":{"sessionID":"session_abc","diff":[{"file":"test.py"}]}}',
            'data: {"type":"session.idle","properties":{"sessionID":"session_abc"}}',
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        await eng._stream_events(mock_client)
        eng.opencode_ui.session_diff.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_compacted_event(self, tmp_path):
        """session.compacted event updates UI."""
        eng = self._make_engineer(tmp_path)

        lines = [
            'data: {"type":"session.compacted","properties":{"sessionID":"session_abc"}}',
            'data: {"type":"session.idle","properties":{"sessionID":"session_abc"}}',
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        await eng._stream_events(mock_client)
        eng.opencode_ui.session_compacted.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_error_event(self, tmp_path):
        """session.error event sets _last_error."""
        eng = self._make_engineer(tmp_path)

        lines = [
            'data: {"type":"session.error","properties":{"sessionID":"session_abc","error":{"name":"ProviderAuthError","data":{"providerID":"anthropic","message":"Invalid API key"}}}}',
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        await eng._stream_events(mock_client)
        assert "Auth error" in eng._last_error
        assert "anthropic" in eng._last_error
        eng.opencode_ui.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_error_api_error(self, tmp_path):
        """session.error with APIError."""
        eng = self._make_engineer(tmp_path)

        lines = [
            'data: {"type":"session.error","properties":{"sessionID":"session_abc","error":{"name":"APIError","data":{"message":"Rate limited","statusCode":429}}}}',
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        await eng._stream_events(mock_client)
        assert "API error" in eng._last_error
        assert "429" in eng._last_error
        eng.opencode_ui.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_error_no_provider_available(self, tmp_path):
        """Zen capacity errors are explained without being displayed twice."""
        eng = self._make_engineer(tmp_path)

        lines = [
            "data: "
            '{"type":"session.error","properties":{"sessionID":"session_abc",'
            '"error":{"name":"APIError","data":{"message":"No provider available","statusCode":401}}}}',
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        await eng._stream_events(mock_client)
        assert eng._last_error == (
            "OpenCode has no serving provider available for this model right now. "
            "Try another free model or retry later."
        )
        eng.opencode_ui.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_error_aborted(self, tmp_path):
        """session.error with MessageAbortedError."""
        eng = self._make_engineer(tmp_path)

        lines = [
            'data: {"type":"session.error","properties":{"sessionID":"session_abc","error":{"name":"MessageAbortedError","data":{}}}}',
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        await eng._stream_events(mock_client)
        assert eng._last_error == "Aborted"

    @pytest.mark.asyncio
    async def test_session_error_unknown_type(self, tmp_path):
        """session.error with unknown error type."""
        eng = self._make_engineer(tmp_path)

        lines = [
            'data: {"type":"session.error","properties":{"sessionID":"session_abc","error":{"name":"CustomError","data":{"message":"custom msg"}}}}',
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        await eng._stream_events(mock_client)
        assert "CustomError" in eng._last_error

    @pytest.mark.asyncio
    async def test_session_error_string(self, tmp_path):
        """session.error with string error object."""
        eng = self._make_engineer(tmp_path)

        lines = [
            'data: {"type":"session.error","properties":{"sessionID":"session_abc","error":"simple error string"}}',
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        await eng._stream_events(mock_client)
        assert eng._last_error == "simple error string"

    @pytest.mark.asyncio
    async def test_session_error_other_session_ignored(self, tmp_path):
        """session.error for other session is ignored."""
        eng = self._make_engineer(tmp_path)

        lines = [
            'data: {"type":"session.error","properties":{"sessionID":"other_session","error":"some error"}}',
            'data: {"type":"session.idle","properties":{"sessionID":"session_abc"}}',
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        await eng._stream_events(mock_client)
        assert eng._last_error is None

    @pytest.mark.asyncio
    async def test_json_decode_error(self, tmp_path):
        """Invalid JSON in event stream is skipped."""
        eng = self._make_engineer(tmp_path)

        lines = [
            'data: not-valid-json',
            'data: {"type":"session.idle","properties":{"sessionID":"session_abc"}}',
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        await eng._stream_events(mock_client)
        # Should not error, just skip invalid line

    @pytest.mark.asyncio
    async def test_buffer_size_error(self, tmp_path):
        """Buffer size error is handled specially."""
        eng = self._make_engineer(tmp_path)

        lines = [
            'data: {"invalid": "exceeded maximum buffer size 1048576',  # Causes JSONDecodeError with buffer text
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        # The JSON parse will fail but "1048576" isn't in the JSONDecodeError message
        # Let's directly test the error by checking for normal decode errors
        await eng._stream_events(mock_client)

    @pytest.mark.asyncio
    async def test_buffer_size_json_error_with_keyword(self, tmp_path):
        """Buffer size error detected in JSONDecodeError message triggers special handling."""
        eng = self._make_engineer(tmp_path)

        # Patch json.loads to raise JSONDecodeError with buffer size in message
        original_loads = json.loads

        def mock_loads(s, *args, **kwargs):
            raise json.JSONDecodeError("exceeded maximum buffer size 1048576", s, 0)

        lines = [
            'data: {"some":"data"}',
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        with patch("reverse_api.opencode_engineer.json.loads", side_effect=mock_loads):
            await eng._stream_events(mock_client)
            assert eng._last_error is not None
            assert "Screenshot too large" in eng._last_error

    @pytest.mark.asyncio
    async def test_message_part_updated_event(self, tmp_path):
        """message.part.updated event calls _handle_part_update."""
        eng = self._make_engineer(tmp_path)

        lines = [
            'data: {"type":"message.part.updated","properties":{"sessionID":"session_abc","part":{"type":"text","text":"thinking..."}}}',
            'data: {"type":"session.idle","properties":{"sessionID":"session_abc"}}',
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        with patch.object(eng, "_handle_part_update", new_callable=AsyncMock) as mock_handle:
            await eng._stream_events(mock_client)
            mock_handle.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_renders_only_assistant_text(self, tmp_path):
        """Parts arriving before their roles are known are safely buffered."""
        eng = self._make_engineer(tmp_path)
        lines = [
            'data: {"type":"message.part.updated","properties":{"sessionID":"session_abc",'
            '"part":{"id":"part_user","messageID":"message_user","sessionID":"session_abc",'
            '"type":"text","text":"There is no HAR file — capture all network data."}}}',
            'data: {"type":"message.part.updated","properties":{"sessionID":"session_abc",'
            '"part":{"id":"part_assistant","messageID":"message_assistant","sessionID":"session_abc",'
            '"type":"text","text":"Assistant answer","time":{"start":1,"end":2}}}}',
            'data: {"type":"message.updated","properties":{"sessionID":"session_abc",'
            '"info":{"id":"message_user","sessionID":"session_abc","role":"user"}}}',
            'data: {"type":"message.updated","properties":{"sessionID":"session_abc",'
            '"info":{"id":"message_assistant","sessionID":"session_abc","role":"assistant"}}}',
            'data: {"type":"session.idle","properties":{"sessionID":"session_abc"}}',
        ]
        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)
        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        await eng._stream_events(mock_client)

        eng.opencode_ui.update_text.assert_called_once_with("Assistant answer", None)
        assert eng._pending_text_parts == {}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "idle_event",
        [
            'data: {"type":"session.idle","properties":{"sessionID":"session_abc"}}',
            'data: {"type":"session.status","properties":{"sessionID":"session_abc","status":{"type":"idle"}}}',
        ],
    )
    async def test_idle_reconciles_buffered_assistant_role(self, tmp_path, idle_event):
        """Idle resolves buffered roles from final state without waiting on SSE order."""
        eng = self._make_engineer(tmp_path)
        lines = [
            'data: {"type":"message.part.updated","properties":{"sessionID":"session_abc",'
            '"part":{"id":"part_user","messageID":"message_user","sessionID":"session_abc",'
            '"type":"text","text":"Internal user prompt"}}}',
            'data: {"type":"message.part.updated","properties":{"sessionID":"session_abc",'
            '"part":{"id":"part_assistant","messageID":"message_assistant","sessionID":"session_abc",'
            '"type":"text","text":"Late assistant answer"}}}',
            idle_event,
            'data: {"type":"message.updated","properties":{"sessionID":"session_abc",'
            '"info":{"id":"message_assistant","sessionID":"session_abc","role":"assistant"}}}',
        ]
        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)
        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)
        final_response = MagicMock(status_code=200)
        final_response.json.return_value = [
            {"info": {"id": "message_user", "sessionID": "session_abc", "role": "user"}},
            {"info": {"id": "message_assistant", "sessionID": "session_abc", "role": "assistant"}},
        ]
        mock_client.get = AsyncMock(return_value=final_response)

        await eng._stream_events(mock_client)

        assert eng._last_error is None
        eng.opencode_ui.update_text.assert_called_once_with("Late assistant answer", None)
        assert eng._pending_text_parts == {}
        mock_client.get.assert_awaited_once_with("/session/session_abc/message")

    @pytest.mark.asyncio
    async def test_idle_with_unresolved_buffer_reports_specific_error(self, tmp_path):
        """A closed stream cannot turn unresolved buffered output into success."""
        eng = self._make_engineer(tmp_path)
        lines = [
            'data: {"type":"message.part.updated","properties":{"sessionID":"session_abc",'
            '"part":{"id":"part_assistant","messageID":"message_assistant","sessionID":"session_abc",'
            '"type":"text","text":"Unresolved answer"}}}',
            'data: {"type":"session.idle","properties":{"sessionID":"session_abc"}}',
        ]
        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)
        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)
        final_response = MagicMock(status_code=200)
        final_response.json.return_value = []
        mock_client.get = AsyncMock(return_value=final_response)

        await eng._stream_events(mock_client)

        assert eng._last_error == "OpenCode completed without role metadata for buffered message(s): message_assistant."
        eng.opencode_ui.update_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_and_non_data_lines_skipped(self, tmp_path):
        """Empty lines and non-data lines are skipped."""
        eng = self._make_engineer(tmp_path)

        lines = [
            "",
            "event: message",
            "data:",
            'data: {"type":"session.idle","properties":{"sessionID":"session_abc"}}',
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        await eng._stream_events(mock_client)

    @pytest.mark.asyncio
    async def test_data_without_space(self, tmp_path):
        """data: (without space) prefix is handled."""
        eng = self._make_engineer(tmp_path)

        lines = [
            'data:{"type":"session.idle","properties":{"sessionID":"session_abc"}}',
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        await eng._stream_events(mock_client)

    @pytest.mark.asyncio
    async def test_read_error_in_stream(self, tmp_path):
        """httpx.ReadError during streaming sets _last_error."""
        eng = self._make_engineer(tmp_path)

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            raise httpx.ReadError("Connection lost")
            yield  # Make it a generator

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        await eng._stream_events(mock_client)
        assert eng._last_error is not None

    @pytest.mark.asyncio
    async def test_general_exception_in_stream(self, tmp_path):
        """General exception during streaming sets _last_error."""
        eng = self._make_engineer(tmp_path)

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            raise RuntimeError("Unexpected error")
            yield

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)

        await eng._stream_events(mock_client)
        assert eng._last_error is not None

    @pytest.mark.asyncio
    async def test_permission_approval_fails(self, tmp_path):
        """Permission transport failures stop the stream immediately."""
        eng = self._make_engineer(tmp_path)

        lines = [
            'data: {"type":"permission.updated","properties":{"id":"perm1","sessionID":"session_abc","type":"write","title":"Write"}}',
            'data: {"type":"session.idle","properties":{"sessionID":"session_abc"}}',
        ]

        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)
        mock_client.post = AsyncMock(side_effect=Exception("permission failed"))

        await eng._stream_events(mock_client)
        assert eng._last_error == "Permission approval failed for write: permission failed"
        eng.opencode_ui.session_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_permission_rejection_reports_status_and_stops_stream(self, tmp_path):
        """A rejected permission reply is fatal instead of timing out later."""
        eng = self._make_engineer(tmp_path)
        lines = [
            'data: {"type":"permission.v2.asked","properties":{"id":"perm1","sessionID":"session_abc","action":"write"}}',
            'data: {"type":"session.idle","properties":{"sessionID":"session_abc"}}',
        ]
        mock_response = AsyncMock()

        async def mock_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = mock_aiter_lines
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)
        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=cm)
        mock_client.post = AsyncMock(return_value=MagicMock(status_code=403))

        await eng._stream_events(mock_client)

        assert eng._last_error == "Permission approval failed for write: OpenCode returned HTTP 403."
        eng.opencode_ui.permission_approved.assert_not_called()
        eng.opencode_ui.session_status.assert_not_called()


class TestOpenCodeEngineerAnalyzeAndGenerate:
    """Test analyze_and_generate method."""

    def _make_engineer(self, tmp_path):
        har_path = tmp_path / "test.har"
        har_path.touch()
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.MessageStore") as mock_ms:
                mock_ms.return_value = MagicMock()
                with patch("reverse_api.opencode_engineer.OpenCodeUI") as mock_ui:
                    mock_ui.return_value = MagicMock()
                    eng = OpenCodeEngineer(
                        run_id="test123",
                        har_path=har_path,
                        prompt="test prompt",
                        output_dir=str(tmp_path),
                    )
                    eng.scripts_dir = tmp_path / "scripts"
                    eng.scripts_dir.mkdir(parents=True, exist_ok=True)
                    return eng

    @pytest.mark.asyncio
    async def test_prepare_server_configures_ollama_before_opencode(self, tmp_path):
        eng = self._make_engineer(tmp_path)
        eng.opencode_provider = "ollama"
        eng.opencode_model = "qwen3:4b"
        client = AsyncMock()
        ollama_setup = MagicMock()
        ollama_setup.status.started = False
        server = MagicMock(started=True, package="opencode-ai@latest", health={"version": "1.18.4"})

        with patch(
            "reverse_api.opencode_engineer.prepare_ollama_model",
            new=AsyncMock(return_value=ollama_setup),
        ) as prepare:
            with patch(
                "reverse_api.opencode_engineer.opencode_ollama_env",
                return_value={"OPENCODE_CONFIG_CONTENT": "{}"},
            ):
                with patch(
                    "reverse_api.opencode_engineer.ensure_opencode_server",
                    new=AsyncMock(return_value=server),
                ) as ensure:
                    with patch(
                        "reverse_api.opencode_engineer.validate_opencode_ollama_provider",
                        new=AsyncMock(),
                    ) as validate:
                        with patch(
                            "reverse_api.opencode_engineer.validate_opencode_model",
                            new=AsyncMock(),
                        ) as validate_model:
                            assert await eng._prepare_server(client) is True

        prepare.assert_awaited_once_with("qwen3:4b")
        ensure.assert_awaited_once_with(
            client,
            base_url=eng.BASE_URL,
            env_overrides={"OPENCODE_CONFIG_CONTENT": "{}"},
        )
        validate.assert_awaited_once_with(client, "qwen3:4b")
        validate_model.assert_awaited_once_with(client, "ollama", "qwen3:4b")
        eng.opencode_ui.ollama_ready.assert_called_once_with("qwen3:4b", False)

    @pytest.mark.asyncio
    async def test_health_check_401(self, tmp_path):
        """401 on health check returns None."""
        eng = self._make_engineer(tmp_path)

        mock_response = MagicMock()
        mock_response.status_code = 401
        error = httpx.HTTPStatusError("401", request=MagicMock(), response=mock_response)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=error)

        with patch("reverse_api.opencode_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self, tmp_path):
        """Connection error on health check returns None."""
        eng = self._make_engineer(tmp_path)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))

        with patch("reverse_api.opencode_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_connect_error(self, tmp_path):
        """httpx.ConnectError returns None."""
        eng = self._make_engineer(tmp_path)

        with patch("reverse_api.opencode_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_general_exception(self, tmp_path):
        """General exception returns None."""
        eng = self._make_engineer(tmp_path)

        with patch("reverse_api.opencode_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(
                side_effect=RuntimeError("unexpected")
            )
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_http_401_during_session(self, tmp_path):
        """401 during session creation returns None."""
        eng = self._make_engineer(tmp_path)

        health_response = MagicMock()
        health_response.status_code = 200
        health_response.json.return_value = {"status": "ok"}
        health_response.raise_for_status = MagicMock()

        session_response = MagicMock()
        session_response.status_code = 401
        session_error = httpx.HTTPStatusError("401", request=MagicMock(), response=session_response)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=health_response)
        mock_client.post = AsyncMock(side_effect=session_error)

        with patch("reverse_api.opencode_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None


    @pytest.mark.asyncio
    async def test_success_flow(self, tmp_path):
        """Full success flow: health check → session → event stream → result."""
        eng = self._make_engineer(tmp_path)

        health_response = MagicMock()
        health_response.status_code = 200
        health_response.json.return_value = {"status": "ok"}
        health_response.raise_for_status = MagicMock()

        session_response = MagicMock()
        session_response.json.return_value = {"id": "sess_abc"}
        session_response.raise_for_status = MagicMock()

        prompt_response = MagicMock()
        prompt_response.raise_for_status = MagicMock()

        messages_response = MagicMock()
        messages_response.status_code = 200
        messages_response.json.return_value = [
            {
                "info": {"role": "assistant", "providerID": "anthropic", "modelID": "claude-sonnet-4-6"},
                "parts": [{"type": "text", "text": "Here is the API client."}],
            }
        ]

        async def mock_get(path, **kwargs):
            if path == "/global/health":
                return health_response
            if path == "/config/providers":
                return _valid_catalog_response()
            if "/message" in path:
                return messages_response
            return MagicMock()

        post_count = [0]

        async def mock_post(path, **kwargs):
            post_count[0] += 1
            if path == "/session":
                return session_response
            return prompt_response

        # Mock event stream that completes immediately
        mock_stream_resp = AsyncMock()

        async def mock_aiter_lines():
            yield 'data: {"type":"session.idle","properties":{"sessionID":"sess_abc"}}'

        mock_stream_resp.aiter_lines = mock_aiter_lines
        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_stream_resp)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.post = mock_post
        mock_client.stream = MagicMock(return_value=mock_stream_cm)

        with patch("reverse_api.opencode_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is not None
            assert "script_path" in result
            assert result["session_id"] == "sess_abc"

    @pytest.mark.asyncio
    async def test_health_401_custom_username(self, tmp_path):
        """401 with custom username shows username."""
        eng = self._make_engineer(tmp_path)
        eng.opencode_username = "custom_user"

        mock_response = MagicMock()
        mock_response.status_code = 401
        error = httpx.HTTPStatusError("401", request=MagicMock(), response=mock_response)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=error)

        with patch("reverse_api.opencode_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_http_non_401_error(self, tmp_path):
        """Non-401 HTTP error during session shows error details."""
        eng = self._make_engineer(tmp_path)

        health_response = MagicMock()
        health_response.status_code = 200
        health_response.json.return_value = {"status": "ok"}
        health_response.raise_for_status = MagicMock()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        session_error = httpx.HTTPStatusError("500", request=MagicMock(), response=mock_response)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=health_response)
        mock_client.post = AsyncMock(side_effect=session_error)

        with patch("reverse_api.opencode_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_success_message_fetch_exception(self, tmp_path):
        """Success flow handles exception when fetching session messages."""
        eng = self._make_engineer(tmp_path)

        health_response = MagicMock()
        health_response.status_code = 200
        health_response.json.return_value = {"status": "ok"}
        health_response.raise_for_status = MagicMock()

        session_response = MagicMock()
        session_response.json.return_value = {"id": "sess_msgfail"}
        session_response.raise_for_status = MagicMock()

        prompt_response = MagicMock()
        prompt_response.raise_for_status = MagicMock()

        get_count = [0]

        async def mock_get(path, **kwargs):
            get_count[0] += 1
            if path == "/global/health":
                return health_response
            if path == "/config/providers":
                return _valid_catalog_response()
            if "/message" in path:
                raise Exception("message fetch failed")
            return MagicMock()

        async def mock_post(path, **kwargs):
            if path == "/session":
                return session_response
            return prompt_response

        mock_stream_resp = AsyncMock()

        async def mock_aiter_lines():
            yield 'data: {"type":"session.idle","properties":{"sessionID":"sess_msgfail"}}'

        mock_stream_resp.aiter_lines = mock_aiter_lines
        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_stream_resp)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.post = mock_post
        mock_client.stream = MagicMock(return_value=mock_stream_cm)

        with patch("reverse_api.opencode_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            # Should still succeed even if message fetch fails
            assert result is not None
            assert "script_path" in result

    @pytest.mark.asyncio
    async def test_health_401_with_custom_username_outer(self, tmp_path):
        """401 in session creation with custom username shows username (line 255)."""
        eng = self._make_engineer(tmp_path)
        eng.opencode_username = "admin"

        health_response = MagicMock()
        health_response.status_code = 200
        health_response.json.return_value = {"status": "ok"}
        health_response.raise_for_status = MagicMock()

        mock_response = MagicMock()
        mock_response.status_code = 401
        session_error = httpx.HTTPStatusError("401", request=MagicMock(), response=mock_response)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=health_response)
        mock_client.post = AsyncMock(side_effect=session_error)

        with patch("reverse_api.opencode_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_health_non_401_raises(self, tmp_path):
        """Non-401 HTTPStatusError in health check re-raises (line 160)."""
        eng = self._make_engineer(tmp_path)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server Error"
        error = httpx.HTTPStatusError("500", request=MagicMock(), response=mock_response)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=error)

        with patch("reverse_api.opencode_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            # 500 should be caught by outer HTTPStatusError handler
            assert result is None

    @pytest.mark.asyncio
    async def test_event_timeout(self, tmp_path):
        """Event stream timeout shows error."""
        eng = self._make_engineer(tmp_path)

        health_response = MagicMock()
        health_response.status_code = 200
        health_response.json.return_value = {"status": "ok"}
        health_response.raise_for_status = MagicMock()

        session_response = MagicMock()
        session_response.json.return_value = {"id": "sess_timeout"}
        session_response.raise_for_status = MagicMock()

        prompt_response = MagicMock()
        prompt_response.raise_for_status = MagicMock()

        async def mock_get(path, **kwargs):
            if path == "/global/health":
                return health_response
            return MagicMock(status_code=200, json=MagicMock(return_value=[]))

        async def mock_post(path, **kwargs):
            if path == "/session":
                return session_response
            return prompt_response

        # Mock event stream that never yields
        mock_stream_resp = AsyncMock()

        async def mock_aiter_lines():
            # Simulate hanging by not yielding idle
            await asyncio.sleep(100)
            yield "will never reach here"

        mock_stream_resp.aiter_lines = mock_aiter_lines
        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_stream_resp)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.post = mock_post
        mock_client.stream = MagicMock(return_value=mock_stream_cm)

        with patch("reverse_api.opencode_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)
            # Patch timeout to be very short
            with patch("reverse_api.opencode_engineer.asyncio.wait_for", side_effect=TimeoutError()):
                result = await eng.analyze_and_generate()
                # Should still return None due to _last_error being set
                assert result is None


class TestRunOpenCodeEngineering:
    """Test run_opencode_engineering dispatch function."""

    def test_dispatches_to_opencode(self, tmp_path):
        """Creates OpenCodeEngineer and runs async."""
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.MessageStore"):
                with patch("reverse_api.opencode_engineer.OpenCodeUI"):
                    with patch("reverse_api.opencode_engineer.asyncio.run", return_value={"test": True}) as mock_run:
                        result = run_opencode_engineering(
                            run_id="test123",
                            har_path=har_path,
                            prompt="test prompt",
                        )
                        mock_run.assert_called_once()
                        assert result == {"test": True}
