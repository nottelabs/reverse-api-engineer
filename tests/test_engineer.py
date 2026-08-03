"""Tests for engineer.py - run_reverse_engineering dispatch."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reverse_api.base_engineer import OTHER_OPTION
from reverse_api.engineer import APIReverseEngineer, ClaudeEngineer, run_reverse_engineering


class TestClaudeEngineerAlias:
    """Test backward compatibility alias."""

    def test_alias(self):
        """APIReverseEngineer is alias for ClaudeEngineer."""
        assert APIReverseEngineer is ClaudeEngineer


class TestRunReverseEngineering:
    """Test run_reverse_engineering dispatch function."""

    def test_dispatches_to_claude(self, tmp_path):
        """Claude SDK is used by default."""
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.engineer.ClaudeEngineer") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.start_sync = MagicMock()
            mock_instance.stop_sync = MagicMock()

            with patch("reverse_api.engineer.asyncio.run", return_value={"test": True}):
                result = run_reverse_engineering(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                    sdk="claude",
                )
                mock_cls.assert_called_once()

    def test_dispatches_to_opencode(self, tmp_path):
        """OpenCode SDK is used when specified."""
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.opencode_engineer.OpenCodeEngineer") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.start_sync = MagicMock()
            mock_instance.stop_sync = MagicMock()

            with patch("reverse_api.engineer.asyncio.run", return_value={"test": True}):
                result = run_reverse_engineering(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                    sdk="opencode",
                    opencode_provider="anthropic",
                    opencode_model="claude-opus-4-6",
                )
                mock_cls.assert_called_once()

    def test_starts_sync(self, tmp_path):
        """Sync is started before analysis."""
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.engineer.ClaudeEngineer") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.start_sync = MagicMock()
            mock_instance.stop_sync = MagicMock()

            with patch("reverse_api.engineer.asyncio.run", return_value=None):
                run_reverse_engineering(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                )
                mock_instance.start_sync.assert_called_once()

    def test_stops_sync_on_error(self, tmp_path):
        """Sync is stopped even on error."""
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.engineer.ClaudeEngineer") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.start_sync = MagicMock()
            mock_instance.stop_sync = MagicMock()

            with patch("reverse_api.engineer.asyncio.run", side_effect=Exception("fail")):
                with pytest.raises(Exception):
                    run_reverse_engineering(
                        run_id="test123",
                        har_path=har_path,
                        prompt="test prompt",
                    )
                mock_instance.stop_sync.assert_called_once()

    def test_keyboard_interrupt_returns_none(self, tmp_path):
        """KeyboardInterrupt is caught and returns None."""
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.engineer.ClaudeEngineer") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.start_sync = MagicMock()
            mock_instance.stop_sync = MagicMock()

            with patch("reverse_api.engineer.asyncio.run", side_effect=KeyboardInterrupt):
                result = run_reverse_engineering(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                )
                assert result is None
                mock_instance.stop_sync.assert_called_once()

    def test_passes_all_params_to_claude(self, tmp_path):
        """All parameters are forwarded to ClaudeEngineer."""
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.engineer.ClaudeEngineer") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.start_sync = MagicMock()
            mock_instance.stop_sync = MagicMock()

            with patch("reverse_api.engineer.asyncio.run", return_value=None):
                run_reverse_engineering(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test",
                    model="claude-opus-4-6",
                    additional_instructions="extra",
                    output_dir="/custom",
                    verbose=False,
                    enable_sync=True,
                    is_fresh=True,
                    output_language="typescript",
                    output_mode="docs",
                )
                kwargs = mock_cls.call_args[1]
                assert kwargs["run_id"] == "test123"
                assert kwargs["model"] == "claude-opus-4-6"
                assert kwargs["output_language"] == "typescript"
                assert kwargs["output_mode"] == "docs"
                assert kwargs["is_fresh"] is True


class TestAskUserInteractive:
    """Test _ask_user_interactive method on BaseEngineer (via ClaudeEngineer)."""

    def _make_engineer(self, tmp_path):
        har_path = tmp_path / "test.har"
        har_path.touch()
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.MessageStore"):
                return ClaudeEngineer(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                    output_dir=str(tmp_path),
                )

    @pytest.mark.asyncio
    async def test_single_select_with_options(self, tmp_path):
        """Single select question with options includes Other option."""
        eng = self._make_engineer(tmp_path)

        mock_select = MagicMock()
        mock_select.ask_async = AsyncMock(return_value="Option A - Description A")

        with patch("reverse_api.base_engineer.questionary.select", return_value=mock_select) as mock_sel:
            answers = await eng._ask_user_interactive([{
                "question": "Which option?",
                "header": "Choice",
                "multiSelect": False,
                "options": [
                    {"label": "Option A", "description": "Description A"},
                    {"label": "Option B", "description": "Description B"},
                ],
            }])
            assert answers["Which option?"] == "Option A"
            # Verify OTHER_OPTION was appended to choices
            call_kwargs = mock_sel.call_args
            choices = call_kwargs.kwargs.get("choices") or call_kwargs[1].get("choices")
            assert OTHER_OPTION in choices

    @pytest.mark.asyncio
    async def test_single_select_other_option(self, tmp_path):
        """Selecting 'Other' in single-select prompts for free text."""
        eng = self._make_engineer(tmp_path)

        mock_select = MagicMock()
        mock_select.ask_async = AsyncMock(return_value=OTHER_OPTION)

        mock_text = MagicMock()
        mock_text.ask_async = AsyncMock(return_value="my custom answer")

        with patch("reverse_api.base_engineer.questionary.select", return_value=mock_select):
            with patch("reverse_api.base_engineer.questionary.text", return_value=mock_text):
                answers = await eng._ask_user_interactive([{
                    "question": "Which option?",
                    "header": "",
                    "multiSelect": False,
                    "options": [{"label": "Option A"}],
                }])
                assert answers["Which option?"] == "my custom answer"

    @pytest.mark.asyncio
    async def test_multi_select_with_options(self, tmp_path):
        """Multi select question with options."""
        eng = self._make_engineer(tmp_path)

        mock_checkbox = MagicMock()
        mock_checkbox.ask_async = AsyncMock(return_value=["Option A - Desc", "Option B"])

        with patch("reverse_api.base_engineer.questionary.checkbox", return_value=mock_checkbox):
            answers = await eng._ask_user_interactive([{
                "question": "Which features?",
                "header": "Features",
                "multiSelect": True,
                "options": [
                    {"label": "Option A", "description": "Desc"},
                    {"label": "Option B"},
                ],
            }])
            assert "Option A" in answers["Which features?"]

    @pytest.mark.asyncio
    async def test_multi_select_other_option(self, tmp_path):
        """Selecting 'Other' in multi-select prompts for free text combined with other selections."""
        eng = self._make_engineer(tmp_path)

        mock_checkbox = MagicMock()
        mock_checkbox.ask_async = AsyncMock(return_value=["Option A", OTHER_OPTION])

        mock_text = MagicMock()
        mock_text.ask_async = AsyncMock(return_value="custom extra")

        with patch("reverse_api.base_engineer.questionary.checkbox", return_value=mock_checkbox):
            with patch("reverse_api.base_engineer.questionary.text", return_value=mock_text):
                answers = await eng._ask_user_interactive([{
                    "question": "Which features?",
                    "header": "",
                    "multiSelect": True,
                    "options": [{"label": "Option A"}, {"label": "Option B"}],
                }])
                assert "Option A" in answers["Which features?"]
                assert "custom extra" in answers["Which features?"]

    @pytest.mark.asyncio
    async def test_empty_question_skipped(self, tmp_path):
        """Empty question text is skipped."""
        eng = self._make_engineer(tmp_path)
        answers = await eng._ask_user_interactive(
            [{"question": "", "header": "", "multiSelect": False, "options": []}]
        )
        assert answers == {}

    @pytest.mark.asyncio
    async def test_select_cancelled(self, tmp_path):
        """Cancelled selection returns empty answer."""
        eng = self._make_engineer(tmp_path)

        mock_select = MagicMock()
        mock_select.ask_async = AsyncMock(return_value=None)

        with patch("reverse_api.base_engineer.questionary.select", return_value=mock_select):
            answers = await eng._ask_user_interactive([{
                "question": "Which option?",
                "header": "",
                "multiSelect": False,
                "options": [{"label": "A"}],
            }])
            assert answers["Which option?"] == ""

    @pytest.mark.asyncio
    async def test_checkbox_cancelled(self, tmp_path):
        """Cancelled checkbox returns empty answer."""
        eng = self._make_engineer(tmp_path)

        mock_checkbox = MagicMock()
        mock_checkbox.ask_async = AsyncMock(return_value=None)

        with patch("reverse_api.base_engineer.questionary.checkbox", return_value=mock_checkbox):
            answers = await eng._ask_user_interactive([{
                "question": "Which features?",
                "header": "",
                "multiSelect": True,
                "options": [{"label": "A"}],
            }])
            assert answers["Which features?"] == ""

    @pytest.mark.asyncio
    async def test_text_fallback_no_options(self, tmp_path):
        """Text input fallback when no options."""
        eng = self._make_engineer(tmp_path)

        mock_text = MagicMock()
        mock_text.ask_async = AsyncMock(return_value="custom answer")

        with patch("reverse_api.base_engineer.questionary.text", return_value=mock_text):
            answers = await eng._ask_user_interactive([{
                "question": "Enter value?",
                "header": "",
                "multiSelect": False,
                "options": [],
            }])
            assert answers["Enter value?"] == "custom answer"

    @pytest.mark.asyncio
    async def test_text_fallback_cancelled(self, tmp_path):
        """Cancelled text input returns empty answer."""
        eng = self._make_engineer(tmp_path)

        mock_text = MagicMock()
        mock_text.ask_async = AsyncMock(return_value=None)

        with patch("reverse_api.base_engineer.questionary.text", return_value=mock_text):
            answers = await eng._ask_user_interactive([{
                "question": "Enter value?",
                "header": "",
                "multiSelect": False,
                "options": [],
            }])
            assert answers["Enter value?"] == ""

    @pytest.mark.asyncio
    async def test_multiple_questions(self, tmp_path):
        """Multiple questions in a single call."""
        eng = self._make_engineer(tmp_path)

        mock_select = MagicMock()
        mock_select.ask_async = AsyncMock(return_value="A")

        mock_text = MagicMock()
        mock_text.ask_async = AsyncMock(return_value="free answer")

        with patch("reverse_api.base_engineer.questionary.select", return_value=mock_select):
            with patch("reverse_api.base_engineer.questionary.text", return_value=mock_text):
                answers = await eng._ask_user_interactive([
                    {
                        "question": "Pick one?",
                        "header": "Section 1",
                        "multiSelect": False,
                        "options": [{"label": "A"}, {"label": "B"}],
                    },
                    {
                        "question": "Describe it?",
                        "header": "Section 2",
                        "multiSelect": False,
                        "options": [],
                    },
                ])
                assert answers["Pick one?"] == "A"
                assert answers["Describe it?"] == "free answer"


class TestHandleToolPermission:
    """Test _handle_tool_permission method."""

    def _make_engineer(self, tmp_path):
        har_path = tmp_path / "test.har"
        har_path.touch()
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.MessageStore"):
                return ClaudeEngineer(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                    output_dir=str(tmp_path),
                )

    @pytest.mark.asyncio
    async def test_non_ask_user_tool_auto_approves(self, tmp_path):
        """Non-AskUserQuestion tools are auto-approved."""
        eng = self._make_engineer(tmp_path)
        result = await eng._handle_tool_permission("Write", {"file_path": "/test.py"}, None)
        assert result.updated_input == {"file_path": "/test.py"}

    @pytest.mark.asyncio
    async def test_ask_user_question_delegates(self, tmp_path):
        """AskUserQuestion delegates to _ask_user_interactive."""
        eng = self._make_engineer(tmp_path)

        mock_text = MagicMock()
        mock_text.ask_async = AsyncMock(return_value="user answer")

        with patch("reverse_api.base_engineer.questionary.text", return_value=mock_text):
            result = await eng._handle_tool_permission(
                "AskUserQuestion",
                {"questions": [{"question": "What?", "header": "", "multiSelect": False, "options": []}]},
                None,
            )
            assert result.updated_input["answers"]["What?"] == "user answer"

    @pytest.mark.asyncio
    async def test_ask_user_question_non_interactive_stub(self, tmp_path):
        """AskUserQuestion returns a fixed message when interactive=False."""
        from reverse_api.base_engineer import NON_INTERACTIVE_ASK_USER_MESSAGE

        eng = self._make_engineer(tmp_path)
        eng.interactive = False

        with patch("reverse_api.base_engineer.questionary.text") as mock_text:
            result = await eng._handle_tool_permission(
                "AskUserQuestion",
                {"questions": [{"question": "What?", "header": "", "multiSelect": False, "options": []}]},
                None,
            )
            mock_text.assert_not_called()
            assert result.updated_input["answers"]["What?"] == NON_INTERACTIVE_ASK_USER_MESSAGE


class TestAskUserQuestions:
    """Test _ask_user_questions routing."""

    def _make_engineer(self, tmp_path, *, interactive: bool = True):
        har_path = tmp_path / "test.har"
        har_path.touch()
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.MessageStore"):
                eng = ClaudeEngineer(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                    output_dir=str(tmp_path),
                    interactive=interactive,
                )
                return eng

    @pytest.mark.asyncio
    async def test_non_interactive_no_questionary(self, tmp_path):
        from reverse_api.base_engineer import NON_INTERACTIVE_ASK_USER_MESSAGE

        eng = self._make_engineer(tmp_path, interactive=False)
        answers = await eng._ask_user_questions(
            [{"question": "Pick auth?", "header": "", "multiSelect": False, "options": []}]
        )
        assert answers["Pick auth?"] == NON_INTERACTIVE_ASK_USER_MESSAGE


class TestClaudeEngineerAnalyzeAndGenerate:
    """Test analyze_and_generate method."""

    def _make_engineer(self, tmp_path, **kwargs):
        har_path = tmp_path / "test.har"
        har_path.touch()
        defaults = {
            "run_id": "test123",
            "har_path": har_path,
            "prompt": "test prompt",
            "output_dir": str(tmp_path),
        }
        defaults.update(kwargs)
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.MessageStore") as mock_ms:
                mock_ms_instance = MagicMock()
                mock_ms.return_value = mock_ms_instance
                eng = ClaudeEngineer(**defaults)
                eng.scripts_dir = tmp_path / "scripts"
                eng.scripts_dir.mkdir(parents=True, exist_ok=True)
                return eng

    def _make_result_message(self, is_error=False, result_text="Success"):
        """Create a mock that passes isinstance(x, ResultMessage)."""
        from claude_agent_sdk import ResultMessage
        mock = MagicMock(spec=ResultMessage)
        mock.is_error = is_error
        mock.result = result_text
        return mock

    def _make_assistant_message(self, content=None):
        """Create a mock that passes isinstance(x, AssistantMessage)."""
        from claude_agent_sdk import AssistantMessage
        mock = MagicMock(spec=AssistantMessage)
        mock.content = content or []
        mock.usage = None
        return mock

    def _make_tool_use_block(self, name="Read", tool_input=None):
        from claude_agent_sdk import ToolUseBlock
        mock = MagicMock(spec=ToolUseBlock)
        mock.name = name
        mock.input = tool_input or {}
        return mock

    def _make_tool_result_block(self, is_error=False, content="output"):
        from claude_agent_sdk import ToolResultBlock
        mock = MagicMock(spec=ToolResultBlock)
        mock.is_error = is_error
        mock.content = content
        return mock

    def _make_text_block(self, text="Thinking..."):
        from claude_agent_sdk import TextBlock
        mock = MagicMock(spec=TextBlock)
        mock.text = text
        return mock

    @pytest.mark.asyncio
    async def test_successful_generation_no_followup(self, tmp_path):
        """Successful analysis with no follow-up returns result dict."""
        eng = self._make_engineer(tmp_path)

        mock_result = self._make_result_message(is_error=False)

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch("reverse_api.engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch.object(eng, "_prompt_follow_up", new_callable=AsyncMock, return_value=None):
                result = await eng.analyze_and_generate()
                assert result is not None
                assert "script_path" in result

    @pytest.mark.asyncio
    async def test_result_error(self, tmp_path):
        """Error result returns None."""
        eng = self._make_engineer(tmp_path)

        mock_result = self._make_result_message(is_error=True, result_text="Analysis failed")

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch("reverse_api.engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_result_error_none_message(self, tmp_path):
        """Error result with None message uses 'Unknown error'."""
        eng = self._make_engineer(tmp_path)

        mock_result = self._make_result_message(is_error=True, result_text=None)

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch("reverse_api.engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_assistant_message_with_tools(self, tmp_path):
        """AssistantMessage with tool blocks processes correctly."""
        eng = self._make_engineer(tmp_path)

        mock_tool_use = self._make_tool_use_block("Read", {"file_path": "/test.py"})
        mock_tool_result = self._make_tool_result_block(is_error=False, content="file content")
        mock_text = self._make_text_block("Analyzing the file...")

        mock_assistant = self._make_assistant_message(
            content=[mock_tool_use, mock_tool_result, mock_text]
        )
        mock_assistant.usage = {"input_tokens": 100, "output_tokens": 50}

        mock_result = self._make_result_message(is_error=False)

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        call_count = 0

        async def mock_receive():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield mock_assistant
                yield mock_result
            else:
                yield mock_result

        mock_client.receive_response = mock_receive

        with patch("reverse_api.engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch.object(eng, "_prompt_follow_up", new_callable=AsyncMock, return_value=None):
                result = await eng.analyze_and_generate()
                assert result is not None

    @pytest.mark.asyncio
    async def test_exception_handling(self, tmp_path):
        """Exception during SDK use returns None."""
        eng = self._make_engineer(tmp_path)

        with patch("reverse_api.engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(side_effect=Exception("SDK error"))
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_keyboard_interrupt_returns_partial(self, tmp_path):
        """KeyboardInterrupt during streaming returns last result or None."""
        eng = self._make_engineer(tmp_path)

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            raise KeyboardInterrupt

        mock_client.receive_response = mock_receive

        with patch("reverse_api.engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_follow_up_sends_new_query(self, tmp_path):
        """Follow-up message sends a new query and processes response."""
        eng = self._make_engineer(tmp_path)

        mock_result = self._make_result_message(is_error=False)

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_result

        mock_client.receive_response = mock_receive

        follow_up_responses = iter(["refine the auth handling", None])

        with patch("reverse_api.engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch.object(
                eng,
                "_prompt_follow_up",
                new_callable=AsyncMock,
                side_effect=lambda: next(follow_up_responses),
            ):
                result = await eng.analyze_and_generate()
                assert result is not None
                # Initial query + follow-up query
                assert mock_client.query.call_count == 2

    @pytest.mark.asyncio
    async def test_result_with_usage_metadata(self, tmp_path):
        """Result with usage metadata calculates cost."""
        eng = self._make_engineer(tmp_path)
        eng.usage_metadata = {
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_creation_input_tokens": 100,
            "cache_read_input_tokens": 50,
        }

        mock_result = self._make_result_message(is_error=False)

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch("reverse_api.engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch.object(eng, "_prompt_follow_up", new_callable=AsyncMock, return_value=None):
                result = await eng.analyze_and_generate()
                assert result is not None
                assert "usage" in result
                assert "estimated_cost_usd" in result["usage"]

    @pytest.mark.asyncio
    async def test_result_with_local_scripts_dir(self, tmp_path):
        """Result includes local path when local_scripts_dir is set."""
        eng = self._make_engineer(tmp_path)
        eng.local_scripts_dir = tmp_path / "local_scripts"

        mock_result = self._make_result_message(is_error=False)

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch("reverse_api.engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch.object(eng, "_prompt_follow_up", new_callable=AsyncMock, return_value=None):
                result = await eng.analyze_and_generate()
                assert result is not None


class TestContextOverflowHandling:
    """Test context-window overflow ("Prompt is too long") handling."""

    def _make_engineer(self, tmp_path):
        har_path = tmp_path / "test.har"
        har_path.touch()
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.MessageStore"):
                return ClaudeEngineer(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                    output_dir=str(tmp_path),
                )

    def _make_client(self, result_message):
        client = MagicMock()

        async def receive():
            yield result_message

        client.receive_response = receive
        return client

    @pytest.mark.asyncio
    async def test_overflow_error_sets_flag_and_prints_help(self, tmp_path):
        """A 'Prompt is too long' result flags the session as unrecoverable."""
        from claude_agent_sdk import ResultMessage

        eng = self._make_engineer(tmp_path)
        msg = MagicMock(spec=ResultMessage)
        msg.is_error = True
        msg.result = "API Error: 400 Prompt is too long"

        with patch.object(eng, "_print_context_overflow_help") as mock_help:
            result = await eng._process_streaming_response(self._make_client(msg))

        assert result is None
        assert eng._context_overflowed is True
        mock_help.assert_called_once()

    @pytest.mark.asyncio
    async def test_other_error_does_not_set_flag(self, tmp_path):
        """A non-overflow error leaves the follow-up loop available."""
        from claude_agent_sdk import ResultMessage

        eng = self._make_engineer(tmp_path)
        msg = MagicMock(spec=ResultMessage)
        msg.is_error = True
        msg.result = "Some other failure"

        with patch.object(eng, "_print_context_overflow_help") as mock_help:
            result = await eng._process_streaming_response(self._make_client(msg))

        assert result is None
        assert eng._context_overflowed is False
        mock_help.assert_not_called()

    @pytest.mark.asyncio
    async def test_follow_up_loop_exits_after_overflow(self, tmp_path):
        """After an overflow mid-follow-up, the loop returns the last result
        instead of prompting for another turn on a dead session."""
        eng = self._make_engineer(tmp_path)

        first_result = {"script_path": "x", "usage": {}}
        responses = iter([first_result, None])

        async def fake_process(client):
            value = next(responses)
            if value is None:
                eng._context_overflowed = True
            return value

        follow_ups = AsyncMock(side_effect=["make it faster", "should not be asked"])

        mock_client = AsyncMock()
        with patch.object(eng, "_process_streaming_response", side_effect=fake_process):
            with patch.object(eng, "_prompt_follow_up", follow_ups):
                with patch("reverse_api.engineer.ClaudeSDKClient") as mock_sdk:
                    mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

                    result = await eng.analyze_and_generate()

        assert result == first_result
        # Only one follow-up should have been requested before the loop ended.
        assert follow_ups.await_count == 1


class TestReportClientVerifiedTool:
    """Test the report_client_verified MCP tool and the client_executed
    json-stream event it now emits directly. Replaces the old approach of
    inferring a real client execution from the agent's own Bash tool-call
    text (_is_client_verification_command, removed) — eight rounds of
    automated PR review kept finding new ways a shell command could *look*
    like a real execution without being one (quoted mentions, "||"/"&&"
    masking, control-flow bodies, quoted keywords, index-misaligned
    quoting...). Suggested directly by the upstream maintainer on the PR:
    have the agent report verification itself via a dedicated tool call
    instead of inferring it from shell syntax after the fact — closes the
    whole bug class by construction.
    """

    def _make_engineer(self, tmp_path, **kwargs):
        har_path = tmp_path / "test.har"
        har_path.touch()
        defaults = {
            "run_id": "test123",
            "har_path": har_path,
            "prompt": "test prompt",
            "output_dir": str(tmp_path),
        }
        defaults.update(kwargs)
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.MessageStore"):
                eng = ClaudeEngineer(**defaults)
                eng.scripts_dir = tmp_path / "scripts"
                eng.scripts_dir.mkdir(parents=True, exist_ok=True)
                return eng

    @pytest.mark.asyncio
    async def test_tool_emits_client_executed_event_when_called(self, tmp_path):
        eng = self._make_engineer(tmp_path, output_language="python")
        events = []
        eng._json_event_sink = events.append

        tool = eng._build_verification_tool()
        await tool.handler({"summary": "ran api_client.py, got a real 200 response"})

        client_executed = [e for e in events if e["event"] == "client_executed"]
        assert len(client_executed) == 1
        assert client_executed[0]["script_path"] == str(eng.scripts_dir / "api_client.py")

    @pytest.mark.asyncio
    async def test_tool_second_call_in_same_session_does_not_re_emit(self, tmp_path):
        """The tool's own description tells the agent to call it exactly
        once, but that's prompt text, not enforced — flagged by automated
        review: a misbehaving or confused agent calling it twice must not
        emit two client_executed records for one job. Same `tool` object
        both times (matching how one _build_verification_tool() call is
        reused for a whole session, not rebuilt per tool-call)."""
        eng = self._make_engineer(tmp_path, output_language="python")
        events = []
        eng._json_event_sink = events.append

        tool = eng._build_verification_tool()
        await tool.handler({"summary": "first confirmation"})
        second_result = await tool.handler({"summary": "second confirmation, just to be sure"})

        client_executed = [e for e in events if e["event"] == "client_executed"]
        assert len(client_executed) == 1
        assert "already recorded" in second_result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_tool_two_separate_sessions_each_get_their_own_event(self, tmp_path):
        """The de-dup guard is per-session (per _build_verification_tool()
        call), not per-engine-instance or global — a fresh session (a new
        call to analyze_and_generate, hence a fresh _build_verification_
        tool()) must still be able to report verification normally."""
        eng = self._make_engineer(tmp_path, output_language="python")
        events = []
        eng._json_event_sink = events.append

        first_tool = eng._build_verification_tool()
        await first_tool.handler({"summary": "session one"})

        second_tool = eng._build_verification_tool()
        await second_tool.handler({"summary": "session two"})

        assert len([e for e in events if e["event"] == "client_executed"]) == 2

    @pytest.mark.asyncio
    async def test_tool_returns_confirmation_content(self, tmp_path):
        """The SDK requires a dict with a "content" key back from every
        tool call — confirms the handler's return value satisfies that,
        not just that it has the side effect."""
        eng = self._make_engineer(tmp_path, output_language="python")
        eng._json_event_sink = lambda e: None

        tool = eng._build_verification_tool()
        result = await tool.handler({"summary": "verified"})

        assert "content" in result
        assert isinstance(result["content"], list)

    @pytest.mark.asyncio
    async def test_tool_no_event_when_no_sink_attached(self, tmp_path):
        """No sink attached (plain --json, not --json-stream) — must not
        raise, same posture as _emit_json_event's own no-op-when-unset
        design."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._json_event_sink is None

        tool = eng._build_verification_tool()
        result = await tool.handler({"summary": "verified"})
        assert "content" in result  # didn't raise

    def test_tool_name_matches_the_documented_instruction(self, tmp_path):
        """Must match REPORT_CLIENT_VERIFIED_INSTRUCTION's own reference to
        this exact tool name — the two are only connected by string
        agreement, nothing enforces it structurally."""
        from reverse_api.base_engineer import REPORT_CLIENT_VERIFIED_INSTRUCTION

        eng = self._make_engineer(tmp_path, output_language="python")
        tool = eng._build_verification_tool()
        assert tool.name == "report_client_verified"
        assert f"`{tool.name}`" in REPORT_CLIENT_VERIFIED_INSTRUCTION

    def test_build_verification_mcp_server_returns_sdk_server_config(self, tmp_path):
        eng = self._make_engineer(tmp_path, output_language="python")
        server = eng._build_verification_mcp_server()
        assert server["type"] == "sdk"
        assert server["name"] == "verification"

    def test_get_codegen_instructions_appends_report_client_verified(self, tmp_path):
        """ClaudeEngineer's own override (the one place this actually
        applies — see engineer.py's own comment on why it's not in the
        shared BaseEngineer method) appends the tool-call instruction for
        every non-docs language."""
        from reverse_api.base_engineer import REPORT_CLIENT_VERIFIED_INSTRUCTION

        eng = self._make_engineer(tmp_path, output_language="python", output_mode="client")
        assert eng._get_codegen_instructions().endswith(REPORT_CLIENT_VERIFIED_INSTRUCTION)

    def test_get_codegen_instructions_docs_mode_has_no_verification_instruction(self, tmp_path):
        """Docs mode generates an OpenAPI spec document, not runnable code —
        nothing to live-verify, so it must not get the instruction."""
        from reverse_api.base_engineer import REPORT_CLIENT_VERIFIED_INSTRUCTION

        eng = self._make_engineer(tmp_path, output_language="python", output_mode="docs")
        assert REPORT_CLIENT_VERIFIED_INSTRUCTION not in eng._get_codegen_instructions()

    def test_get_codegen_instructions_appends_for_every_language(self, tmp_path):
        """Confirms this isn't accidentally scoped to one language's own
        partial template — every partials/_language_*.md gets it the same
        way, since it's appended in Python after loading whichever one."""
        from reverse_api.base_engineer import REPORT_CLIENT_VERIFIED_INSTRUCTION

        for language in ("python", "javascript", "typescript", "go", "java", "csharp", "php", "ruby", "c", "powershell"):
            eng = self._make_engineer(tmp_path, output_language=language, output_mode="client")
            assert eng._get_codegen_instructions().endswith(REPORT_CLIENT_VERIFIED_INSTRUCTION), language

    @pytest.mark.asyncio
    async def test_process_streaming_response_no_longer_infers_from_bash(self, tmp_path):
        """The old mechanism (removed) would have emitted client_executed
        just from seeing a successful `python api_client.py` Bash call.
        That inference is gone entirely now — _process_streaming_response
        must not emit the event no matter what the Bash command looks
        like; only the tool itself does that."""
        eng = self._make_engineer(tmp_path, output_language="python")
        events = []
        eng._json_event_sink = events.append

        from claude_agent_sdk import AssistantMessage, ResultMessage, ToolResultBlock, ToolUseBlock

        tool_use = MagicMock(spec=ToolUseBlock)
        tool_use.name = "Bash"
        tool_use.input = {"command": "python api_client.py"}
        tool_result = MagicMock(spec=ToolResultBlock)
        tool_result.is_error = False
        tool_result.content = "output"
        assistant = MagicMock(spec=AssistantMessage)
        assistant.content = [tool_use, tool_result]
        assistant.usage = None
        result = MagicMock(spec=ResultMessage)
        result.is_error = False
        result.result = "Success"

        async def receive():
            yield assistant
            yield result

        client = MagicMock()
        client.receive_response = receive

        await eng._process_streaming_response(client)

        assert [e for e in events if e["event"] == "client_executed"] == []

    @pytest.mark.asyncio
    async def test_analyze_and_generate_registers_verification_mcp_server(self, tmp_path):
        """Integration-level: the actual ClaudeAgentOptions built by
        analyze_and_generate must include the verification server, not
        just that _build_verification_mcp_server works correctly in
        isolation."""
        eng = self._make_engineer(tmp_path, output_language="python")

        mock_result = MagicMock()
        mock_result.is_error = False
        mock_result.result = "Success"

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch("reverse_api.engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch.object(eng, "_prompt_follow_up", new_callable=AsyncMock, return_value=None):
                await eng.analyze_and_generate()

        _, kwargs = mock_sdk.call_args
        options = kwargs["options"]
        assert "verification" in options.mcp_servers
        assert options.mcp_servers["verification"]["name"] == "verification"


class TestSdkEnvWiring:
    """Test that SDK sessions get the auto-compact env override."""

    def _make_engineer(self, tmp_path):
        har_path = tmp_path / "test.har"
        har_path.touch()
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.MessageStore"):
                return ClaudeEngineer(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                    output_dir=str(tmp_path),
                )

    @pytest.mark.asyncio
    async def test_options_env_includes_autocompact_override(self, tmp_path, monkeypatch):
        """ClaudeAgentOptions receives the lowered auto-compact threshold."""
        from reverse_api.utils import AUTOCOMPACT_PCT, AUTOCOMPACT_WINDOW

        monkeypatch.delenv("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_AUTO_COMPACT_WINDOW", raising=False)
        eng = self._make_engineer(tmp_path)

        mock_client = AsyncMock()

        async def empty_receive():
            return
            yield

        mock_client.receive_response = empty_receive

        with patch("reverse_api.engineer.ClaudeAgentOptions") as mock_options:
            with patch("reverse_api.engineer.ClaudeSDKClient") as mock_sdk:
                mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

                await eng.analyze_and_generate()

        env = mock_options.call_args.kwargs["env"]
        assert env["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] == AUTOCOMPACT_PCT
        assert env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] == AUTOCOMPACT_WINDOW
        assert env["CLAUDECODE"] == ""
