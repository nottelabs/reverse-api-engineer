"""Tests for utils.py - Utility functions."""

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reverse_api.utils import (
    _slugify,
    check_for_updates,
    generate_folder_name,
    generate_run_id,
    get_app_dir,
    get_base_output_dir,
    get_collected_dir,
    get_config_path,
    get_docs_dir,
    get_har_dir,
    get_history_path,
    get_messages_path,
    get_project_root,
    get_timestamp,
)


def _opencode_health_response() -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"healthy": True, "version": "1.18.4"}
    return response


def _opencode_catalog_response() -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "default": {"anthropic": "claude-opus-4-6"},
        "providers": [
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


class TestSlugify:
    """Test _slugify function."""

    def test_basic_text(self):
        """Converts basic text to slug."""
        assert _slugify("Hello World") == "hello_world"

    def test_removes_special_chars(self):
        """Removes special characters."""
        assert _slugify("Hello! World?") == "hello_world"

    def test_limits_to_three_words(self):
        """Takes first 3 words only."""
        result = _slugify("one two three four five")
        assert result == "one_two_three"

    def test_truncates_to_50_chars(self):
        """Truncates to 50 characters."""
        long_text = "a" * 100
        result = _slugify(long_text)
        assert len(result) <= 50

    def test_lowercase(self):
        """Converts to lowercase."""
        assert _slugify("HELLO WORLD") == "hello_world"

    def test_empty_string(self):
        """Handles empty string."""
        assert _slugify("") == ""

    def test_numbers(self):
        """Keeps numbers."""
        assert _slugify("test 123 api") == "test_123_api"

    def test_only_special_chars(self):
        """Handles string with only special chars."""
        result = _slugify("!@#$%")
        assert result == ""


class TestGenerateRunId:
    """Test generate_run_id function."""

    def test_returns_string(self):
        """Returns a string."""
        run_id = generate_run_id()
        assert isinstance(run_id, str)

    def test_length(self):
        """Run ID is 12 characters."""
        run_id = generate_run_id()
        assert len(run_id) == 12

    def test_hex_characters(self):
        """Run ID contains only hex characters."""
        run_id = generate_run_id()
        assert re.match(r"^[0-9a-f]+$", run_id)

    def test_unique(self):
        """Two run IDs are different."""
        id1 = generate_run_id()
        id2 = generate_run_id()
        assert id1 != id2


class TestPathHelpers:
    """Test path helper functions."""

    def test_get_project_root(self):
        """get_project_root returns a valid directory."""
        root = get_project_root()
        assert isinstance(root, Path)

    def test_get_app_dir(self):
        """get_app_dir returns ~/.reverse-api."""
        app_dir = get_app_dir()
        assert app_dir == Path.home() / ".reverse-api"

    def test_get_config_path(self):
        """get_config_path returns config.json in app dir."""
        config_path = get_config_path()
        assert config_path == Path.home() / ".reverse-api" / "config.json"

    def test_get_history_path(self):
        """get_history_path returns history.json in app dir."""
        history_path = get_history_path()
        assert history_path == Path.home() / ".reverse-api" / "history.json"

    def test_get_base_output_dir_default(self):
        """get_base_output_dir returns runs/ in app dir by default."""
        base = get_base_output_dir()
        assert base == Path.home() / ".reverse-api" / "runs"

    def test_get_base_output_dir_custom(self):
        """get_base_output_dir returns custom dir when specified."""
        base = get_base_output_dir("/custom/output")
        assert base == Path("/custom/output")

    def test_get_timestamp(self):
        """get_timestamp returns ISO format."""
        ts = get_timestamp()
        assert "T" in ts  # ISO format contains T separator

    def test_get_messages_path(self, tmp_path):
        """get_messages_path returns correct path."""
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            path = get_messages_path("run123")
            assert path == tmp_path / "messages" / "run123.jsonl"

    def test_get_messages_path_empty_run_id_raises(self):
        """Empty run_id raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            get_messages_path("")

    def test_get_messages_path_traversal_raises(self, tmp_path):
        """Path traversal in run_id raises ValueError."""
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            with pytest.raises(ValueError, match="Invalid run_id"):
                get_messages_path("../../../etc/passwd")

    def test_get_messages_path_too_long_raises(self):
        """Too long run_id raises ValueError."""
        with pytest.raises(ValueError, match="too long"):
            get_messages_path("x" * 65)


class TestGetHarDir:
    """Test get_har_dir with validation."""

    def test_valid_run_id(self, tmp_path):
        """Valid run_id creates correct directory."""
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            har_dir = get_har_dir("abc123")
            assert har_dir == tmp_path / "har" / "abc123"
            assert har_dir.exists()

    def test_run_id_with_hyphens(self, tmp_path):
        """Hyphens are allowed in run_id."""
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            har_dir = get_har_dir("crx-abc-123")
            assert har_dir.exists()

    def test_run_id_with_underscores(self, tmp_path):
        """Underscores are allowed in run_id."""
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            har_dir = get_har_dir("run_123_test")
            assert har_dir.exists()

    def test_empty_run_id_raises(self):
        """Empty run_id raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            get_har_dir("")

    def test_special_chars_raise(self):
        """Special characters in run_id raise ValueError."""
        with pytest.raises(ValueError, match="Invalid run_id"):
            get_har_dir("../../../etc")

    def test_dots_raise(self):
        """Dots in run_id raise ValueError."""
        with pytest.raises(ValueError, match="Invalid run_id"):
            get_har_dir("run.123")

    def test_spaces_raise(self):
        """Spaces in run_id raise ValueError."""
        with pytest.raises(ValueError, match="Invalid run_id"):
            get_har_dir("run 123")

    def test_too_long_run_id(self):
        """Run ID > 64 chars raises ValueError."""
        with pytest.raises(ValueError, match="too long"):
            get_har_dir("a" * 65)

    def test_trailing_newline_raises(self):
        """A trailing newline in run_id raises ValueError."""
        with pytest.raises(ValueError, match="Invalid run_id"):
            get_har_dir("run123\n")

    def test_custom_output_dir(self, tmp_path):
        """Custom output_dir is used."""
        har_dir = get_har_dir("run123", output_dir=str(tmp_path))
        assert har_dir == tmp_path / "har" / "run123"


class TestGetScriptsDir:
    """Test get_scripts_dir with validation."""

    def test_valid_run_id(self, tmp_path):
        """Valid run_id creates correct directory."""
        from reverse_api.utils import get_scripts_dir

        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            scripts_dir = get_scripts_dir("abc123")
            assert scripts_dir == tmp_path / "scripts" / "abc123"
            assert scripts_dir.exists()

    def test_empty_run_id_raises(self):
        """Empty run_id raises ValueError."""
        from reverse_api.utils import get_scripts_dir

        with pytest.raises(ValueError, match="cannot be empty"):
            get_scripts_dir("")

    def test_special_chars_raise(self):
        """Special characters raise ValueError."""
        from reverse_api.utils import get_scripts_dir

        with pytest.raises(ValueError, match="Invalid run_id"):
            get_scripts_dir("../hack")

    def test_too_long_raises(self):
        """Too long run_id raises ValueError."""
        from reverse_api.utils import get_scripts_dir

        with pytest.raises(ValueError, match="too long"):
            get_scripts_dir("x" * 65)


class TestGetDocsDir:
    """Test get_docs_dir with validation."""

    def test_valid_run_id(self, tmp_path):
        """Valid run_id creates correct directory."""
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            docs_dir = get_docs_dir("abc123")
            assert docs_dir == tmp_path / "docs" / "abc123"
            assert docs_dir.exists()

    def test_empty_run_id_raises(self):
        """Empty run_id raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            get_docs_dir("")

    def test_special_chars_raise(self):
        """Special characters raise ValueError."""
        with pytest.raises(ValueError, match="Invalid run_id"):
            get_docs_dir("../hack")

    def test_too_long_raises(self):
        """Too long run_id raises ValueError."""
        with pytest.raises(ValueError, match="too long"):
            get_docs_dir("x" * 65)


class TestGetCollectedDir:
    """Test get_collected_dir."""

    def test_creates_collected_dir(self, tmp_path):
        """Creates collected directory."""
        with patch("reverse_api.utils.Path.cwd", return_value=tmp_path):
            from reverse_api.utils import get_collected_dir

            path = get_collected_dir("test_collection")
            assert path.exists()
            assert path.name == "test_collection"

    def test_empty_folder_name_raises(self):
        """Empty folder_name raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            get_collected_dir("")

    def test_traversal_raises(self, tmp_path):
        """Path traversal in folder_name raises ValueError."""
        with patch("reverse_api.utils.Path.cwd", return_value=tmp_path):
            with pytest.raises(ValueError, match="Invalid folder_name"):
                get_collected_dir("../../etc")

    def test_too_long_raises(self):
        """Too long folder_name raises ValueError."""
        with pytest.raises(ValueError, match="too long"):
            get_collected_dir("x" * 65)


class TestCheckForUpdates:
    """Test check_for_updates function."""

    def test_no_update_needed(self):
        """Returns None when versions match."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"info": {"version": "0.0.0.dev"}}
        with patch("reverse_api.utils.httpx.get", return_value=mock_response):
            with patch("reverse_api.utils.__version__", "0.0.0.dev"):
                assert check_for_updates() is None

    def test_update_available(self):
        """Returns update message when newer version exists."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"info": {"version": "99.0.0"}}
        with patch("reverse_api.utils.httpx.get", return_value=mock_response):
            result = check_for_updates()
            assert result is not None
            assert "99.0.0" in result

    def test_network_error_returns_none(self):
        """Returns None on network error."""
        with patch("reverse_api.utils.httpx.get", side_effect=Exception("network error")):
            assert check_for_updates() is None

    def test_non_200_returns_none(self):
        """Returns None on non-200 response."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        with patch("reverse_api.utils.httpx.get", return_value=mock_response):
            assert check_for_updates() is None


class TestGenerateFolderName:
    """Test generate_folder_name function."""

    def test_falls_back_to_slugify_in_async_context(self):
        """Falls back to _slugify when in async context."""
        import asyncio

        async def _inner():
            return generate_folder_name("test api capture")

        result = asyncio.run(_inner())
        # Should use _slugify fallback since we're in async context
        assert isinstance(result, str)
        assert len(result) > 0

    def test_falls_back_on_exception(self):
        """Falls back to _slugify on exception."""
        with patch("reverse_api.utils.asyncio.get_running_loop", side_effect=RuntimeError):
            with patch("reverse_api.utils.asyncio.run", side_effect=Exception("fail")):
                result = generate_folder_name("test api", sdk="claude")
                assert isinstance(result, str)
                assert len(result) > 0

    def test_sdk_opencode_falls_back(self):
        """OpenCode SDK falls back to slugify when API unavailable."""
        with patch("reverse_api.utils.asyncio.get_running_loop", side_effect=RuntimeError):
            with patch("reverse_api.utils.asyncio.run", side_effect=Exception("no server")):
                result = generate_folder_name("apple jobs api", sdk="opencode")
                assert isinstance(result, str)

    def test_sdk_default_from_config(self):
        """SDK defaults from config when not provided."""
        with patch("reverse_api.utils.asyncio.get_running_loop", side_effect=RuntimeError):
            with patch("reverse_api.utils.asyncio.run", side_effect=Exception("fail")):
                result = generate_folder_name("test prompt")
                assert isinstance(result, str)

    def test_config_exception_defaults_to_claude(self):
        """Config exception defaults SDK to claude."""
        with patch("reverse_api.utils.asyncio.get_running_loop", side_effect=RuntimeError):
            with patch("reverse_api.utils.asyncio.run", side_effect=Exception("fail")):
                with patch("reverse_api.utils.get_config_path", side_effect=Exception("no config")):
                    result = generate_folder_name("test prompt")
                    assert isinstance(result, str)

    def test_opencode_calls_opencode_async(self):
        """OpenCode SDK calls _generate_folder_name_opencode_async."""
        with patch("reverse_api.utils.asyncio.get_running_loop", side_effect=RuntimeError):
            with patch("reverse_api.utils.asyncio.run", return_value="opencode_result") as mock_run:
                result = generate_folder_name("test prompt", sdk="opencode")
                assert result == "opencode_result"

    def test_claude_calls_claude_async(self):
        """Claude SDK calls _generate_folder_name_async."""
        with patch("reverse_api.utils.asyncio.get_running_loop", side_effect=RuntimeError):
            with patch("reverse_api.utils.asyncio.run", return_value="claude_result") as mock_run:
                result = generate_folder_name("test prompt", sdk="claude")
                assert result == "claude_result"

    def test_sdk_cursor_uses_slugify_path(self):
        """Cursor SDK uses slugify (no Claude folder-name call)."""
        with patch("reverse_api.utils._slugify", return_value="slug_cursor") as mock_slug:
            result = generate_folder_name("My API!", sdk="cursor")
        assert result == "slug_cursor"
        mock_slug.assert_called_once()

    def test_with_session_id(self):
        """OpenCode with session_id passes it through."""
        with patch("reverse_api.utils.asyncio.get_running_loop", side_effect=RuntimeError):
            with patch("reverse_api.utils.asyncio.run", return_value="test_result") as mock_run:
                result = generate_folder_name("test prompt", sdk="opencode", session_id="sess123")
                assert result == "test_result"


class TestGenerateFolderNameAsync:
    """Test _generate_folder_name_async function."""

    @pytest.mark.asyncio
    async def test_async_with_sdk_response(self):
        """Async function returns cleaned folder name from SDK."""
        from reverse_api.utils import _generate_folder_name_async
        from claude_agent_sdk import AssistantMessage, TextBlock

        mock_text = MagicMock(spec=TextBlock)
        mock_text.text = "  Apple_Jobs_API  "

        mock_assistant = MagicMock(spec=AssistantMessage)
        mock_assistant.content = [mock_text]

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_assistant

        mock_client.receive_response = mock_receive

        with patch("claude_agent_sdk.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _generate_folder_name_async("Get Apple jobs API")
            assert result == "apple_jobs_api"

    @pytest.mark.asyncio
    async def test_async_empty_response_falls_back(self):
        """Async function falls back to slugify on empty response."""
        from reverse_api.utils import _generate_folder_name_async

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            return
            yield

        mock_client.receive_response = mock_receive

        with patch("claude_agent_sdk.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _generate_folder_name_async("test api capture")
            assert result == "test_api_capture"

    @pytest.mark.asyncio
    async def test_async_cleans_special_chars(self):
        """Async function cleans special characters from response."""
        from reverse_api.utils import _generate_folder_name_async
        from claude_agent_sdk import AssistantMessage, TextBlock

        mock_text = MagicMock(spec=TextBlock)
        mock_text.text = "my-cool/api (v2)"

        mock_assistant = MagicMock(spec=AssistantMessage)
        mock_assistant.content = [mock_text]

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_assistant

        mock_client.receive_response = mock_receive

        with patch("claude_agent_sdk.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _generate_folder_name_async("my cool api")
            assert result == "my_cool_api_v2"


class TestGenerateFolderNameOpencodeAsync:
    """Test _generate_folder_name_opencode_async function."""

    @pytest.mark.asyncio
    async def test_health_check_fails(self):
        """Raises when OpenCode server not responding."""
        from reverse_api.utils import _generate_folder_name_opencode_async

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))

        with patch("reverse_api.config.ConfigManager"):
            with patch("reverse_api.utils.get_config_path"):
                with patch("httpx2.AsyncClient") as mock_async:
                    mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

                    with pytest.raises(Exception, match="not responding"):
                        await _generate_folder_name_opencode_async("test prompt")

    @pytest.mark.asyncio
    async def test_creates_session_when_no_id(self):
        """Creates a new session when session_id is None."""
        from reverse_api.utils import _generate_folder_name_opencode_async

        mock_health = AsyncMock()
        mock_session_create = MagicMock()
        mock_session_create.raise_for_status = MagicMock()
        mock_session_create.json.return_value = {"id": "new_sess_123"}

        mock_message_post = AsyncMock()

        mock_messages_response = MagicMock()
        mock_messages_response.status_code = 200
        mock_messages_response.json.return_value = [
            {
                "info": {"role": "assistant"},
                "parts": [{"type": "text", "text": "apple_jobs_api"}],
            }
        ]

        call_idx = [0]

        async def mock_get(path, **kwargs):
            if path == "/global/health":
                return _opencode_health_response()
            if path == "/config/providers":
                return _opencode_catalog_response()
            if "/message" in path:
                return mock_messages_response
            return MagicMock()

        async def mock_post(path, **kwargs):
            if path == "/session":
                return mock_session_create
            return MagicMock()

        # Mock the stream context manager
        mock_stream_response = AsyncMock()

        async def mock_aiter_lines():
            yield 'data: {"type":"session.idle","properties":{"sessionID":"new_sess_123"}}'

        mock_stream_response.aiter_lines = mock_aiter_lines

        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_stream_response)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.post = mock_post
        mock_client.stream = MagicMock(return_value=mock_stream_cm)
        mock_client.delete = AsyncMock()

        with patch("reverse_api.config.ConfigManager") as mock_cm:
            mock_cm.return_value.get.side_effect = lambda key, default=None: {
                "opencode_provider": "anthropic",
                "opencode_model": "claude-opus-4-6",
            }.get(key, default)
            with patch("reverse_api.utils.get_config_path"):
                with patch("httpx2.AsyncClient") as mock_async:
                    mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

                    result = await _generate_folder_name_opencode_async("Get Apple jobs")
                    assert result == "apple_jobs_api"
                    # Session should be cleaned up
                    mock_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_reuses_existing_session(self):
        """Reuses session_id when provided."""
        from reverse_api.utils import _generate_folder_name_opencode_async

        mock_messages_response = MagicMock()
        mock_messages_response.status_code = 200
        mock_messages_response.json.return_value = [
            {
                "info": {"role": "assistant"},
                "parts": [{"type": "text", "text": "test_api"}],
            }
        ]

        async def mock_get(path, **kwargs):
            if path == "/global/health":
                return _opencode_health_response()
            if path == "/config/providers":
                return _opencode_catalog_response()
            if "/message" in path:
                return mock_messages_response
            return MagicMock()

        async def mock_post(path, **kwargs):
            return MagicMock()

        mock_stream_response = AsyncMock()

        async def mock_aiter_lines():
            yield 'data: {"type":"session.idle","properties":{"sessionID":"existing_sess"}}'

        mock_stream_response.aiter_lines = mock_aiter_lines

        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_stream_response)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.post = mock_post
        mock_client.stream = MagicMock(return_value=mock_stream_cm)
        mock_client.delete = AsyncMock()

        with patch("reverse_api.config.ConfigManager") as mock_cm:
            mock_cm.return_value.get.side_effect = lambda key, default=None: {
                "opencode_provider": "anthropic",
                "opencode_model": "claude-opus-4-6",
            }.get(key, default)
            with patch("reverse_api.utils.get_config_path"):
                with patch("httpx2.AsyncClient") as mock_async:
                    mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

                    result = await _generate_folder_name_opencode_async("test", session_id="existing_sess")
                    assert result == "test_api"
                    # Should NOT delete session since we didn't create it
                    mock_client.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_assistant_messages_returns_slugified(self):
        """Falls back to slugify when no assistant messages found."""
        from reverse_api.utils import _generate_folder_name_opencode_async

        mock_messages_response = MagicMock()
        mock_messages_response.status_code = 200
        mock_messages_response.json.return_value = []  # No messages

        async def mock_get(path, **kwargs):
            if path == "/global/health":
                return _opencode_health_response()
            if path == "/config/providers":
                return _opencode_catalog_response()
            if "/message" in path:
                return mock_messages_response
            return MagicMock()

        async def mock_post(path, **kwargs):
            return MagicMock()

        mock_stream_response = AsyncMock()

        async def mock_aiter_lines():
            yield 'data: {"type":"session.idle","properties":{"sessionID":"sess1"}}'

        mock_stream_response.aiter_lines = mock_aiter_lines

        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_stream_response)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.post = mock_post
        mock_client.stream = MagicMock(return_value=mock_stream_cm)

        with patch("reverse_api.config.ConfigManager") as mock_cm:
            mock_cm.return_value.get.side_effect = lambda key, default=None: {
                "opencode_provider": "anthropic",
                "opencode_model": "claude-opus-4-6",
            }.get(key, default)
            with patch("reverse_api.utils.get_config_path"):
                with patch("httpx2.AsyncClient") as mock_async:
                    mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

                    result = await _generate_folder_name_opencode_async("test api", session_id="sess1")
                    # Falls through to the final return
                    assert result == "test_api"

    @pytest.mark.asyncio
    async def test_session_status_idle_event(self):
        """Handles session.status with idle type."""
        from reverse_api.utils import _generate_folder_name_opencode_async

        mock_messages_response = MagicMock()
        mock_messages_response.status_code = 200
        mock_messages_response.json.return_value = [
            {
                "info": {"role": "assistant"},
                "parts": [{"type": "text", "text": "data_api"}],
            }
        ]

        async def mock_get(path, **kwargs):
            if path == "/global/health":
                return _opencode_health_response()
            if path == "/config/providers":
                return _opencode_catalog_response()
            if "/message" in path:
                return mock_messages_response
            return MagicMock()

        async def mock_post(path, **kwargs):
            return MagicMock()

        mock_stream_response = AsyncMock()

        async def mock_aiter_lines():
            yield 'data: {"type":"session.status","properties":{"sessionID":"sess1","status":{"type":"idle"}}}'

        mock_stream_response.aiter_lines = mock_aiter_lines

        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_stream_response)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.post = mock_post
        mock_client.stream = MagicMock(return_value=mock_stream_cm)

        with patch("reverse_api.config.ConfigManager") as mock_cm:
            mock_cm.return_value.get.side_effect = lambda key, default=None: {
                "opencode_provider": "anthropic",
                "opencode_model": "claude-opus-4-6",
            }.get(key, default)
            with patch("reverse_api.utils.get_config_path"):
                with patch("httpx2.AsyncClient") as mock_async:
                    mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

                    result = await _generate_folder_name_opencode_async("test", session_id="sess1")
                    assert result == "data_api"


class TestPathValidationExceptions:
    """Test path traversal validation exception handling."""

    def test_har_dir_resolve_oserror(self, tmp_path):
        """get_har_dir raises ValueError on OSError during resolve."""
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            with patch.object(Path, "resolve", side_effect=OSError("permission denied")):
                with pytest.raises(ValueError, match="Invalid path"):
                    get_har_dir("valid_id")

    def test_scripts_dir_resolve_oserror(self, tmp_path):
        """get_scripts_dir raises ValueError on OSError during resolve."""
        from reverse_api.utils import get_scripts_dir
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            with patch.object(Path, "resolve", side_effect=OSError("permission denied")):
                with pytest.raises(ValueError, match="Invalid path"):
                    get_scripts_dir("valid_id")

    def test_docs_dir_resolve_oserror(self, tmp_path):
        """get_docs_dir raises ValueError on OSError during resolve."""
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            with patch.object(Path, "resolve", side_effect=OSError("permission denied")):
                with pytest.raises(ValueError, match="Invalid path"):
                    get_docs_dir("valid_id")

    def test_har_dir_resolve_runtime_error(self, tmp_path):
        """get_har_dir raises ValueError on RuntimeError during resolve."""
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            with patch.object(Path, "resolve", side_effect=RuntimeError("symlink loop")):
                with pytest.raises(ValueError, match="Invalid path"):
                    get_har_dir("valid_id")


class TestBuildSdkEnv:
    """Test SDK subprocess environment construction."""

    def test_default_sets_autocompact_override(self, monkeypatch):
        """A proactive compaction window and lowered threshold apply by default."""
        from reverse_api.utils import AUTOCOMPACT_PCT, AUTOCOMPACT_WINDOW, build_sdk_env

        monkeypatch.delenv("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_AUTO_COMPACT_WINDOW", raising=False)
        env = build_sdk_env()
        assert env["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] == AUTOCOMPACT_PCT
        assert env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] == AUTOCOMPACT_WINDOW
        assert env["CLAUDECODE"] == ""

    def test_user_window_wins(self, monkeypatch):
        """An explicit user CLAUDE_CODE_AUTO_COMPACT_WINDOW is not clobbered."""
        from reverse_api.utils import build_sdk_env

        monkeypatch.setenv("CLAUDE_CODE_AUTO_COMPACT_WINDOW", "500000")
        env = build_sdk_env()
        assert "CLAUDE_CODE_AUTO_COMPACT_WINDOW" not in env

    def test_user_override_wins(self, monkeypatch):
        """An explicit user CLAUDE_AUTOCOMPACT_PCT_OVERRIDE is not clobbered."""
        from reverse_api.utils import build_sdk_env

        monkeypatch.setenv("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", "60")
        env = build_sdk_env()
        # The SDK merges our dict on top of os.environ, so omitting the key
        # leaves the user's value in effect.
        assert "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE" not in env
        assert env["CLAUDECODE"] == ""

    def test_empty_user_override_wins(self, monkeypatch):
        """An explicit empty override (opting back into the CLI default)
        is also respected, not replaced with our threshold."""
        from reverse_api.utils import build_sdk_env

        monkeypatch.setenv("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", "")
        env = build_sdk_env()
        assert "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE" not in env


class TestIsContextOverflowError:
    """Test context-window overflow error detection."""

    def test_prompt_too_long(self):
        from reverse_api.utils import is_context_overflow_error

        assert is_context_overflow_error("API Error: 400 Prompt is too long")

    def test_conversation_too_long(self):
        from reverse_api.utils import is_context_overflow_error

        assert is_context_overflow_error(
            "Error during compaction: Error: Conversation too long."
        )

    def test_input_and_max_tokens_variant(self):
        from reverse_api.utils import is_context_overflow_error

        assert is_context_overflow_error(
            "input length and max_tokens exceed context limit"
        )

    def test_unrelated_error(self):
        from reverse_api.utils import is_context_overflow_error

        assert not is_context_overflow_error("Unknown error")
        assert not is_context_overflow_error("rate limit exceeded")
