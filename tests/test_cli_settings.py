"""Tests for the interactive settings navigation."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx2 as httpx

from reverse_api import cli


def test_settings_stays_open_until_back():
    """Changing settings should return to settings, not the REPL."""
    with patch.object(cli, "_handle_settings_action", side_effect=[True, True, False]) as action:
        cli.handle_settings("magenta")

    assert action.call_count == 3


def _answer(value):
    question = MagicMock()
    question.ask.return_value = value
    return question


def _catalog():
    return {
        "default": {"opencode": "big-pickle"},
        "providers": [
            {
                "id": "opencode",
                "name": "OpenCode Zen",
                "models": {
                    "big-pickle": {
                        "name": "Big Pickle",
                        "status": "active",
                        "cost": {"input": 0, "output": 0},
                        "capabilities": {"toolcall": True},
                    },
                    "no-tools": {
                        "status": "active",
                        "capabilities": {"toolcall": False},
                    },
                },
            }
        ],
    }


def test_opencode_pair_picker_uses_live_tool_capable_catalog():
    """The picker only returns a provider/model pair exposed by OpenCode."""
    with patch.object(cli.console, "status") as loading:
        with patch.object(
            cli,
            "_load_opencode_catalog_for_settings",
            new=AsyncMock(return_value=_catalog()),
        ):
            with patch.object(
                cli.questionary,
                "select",
                side_effect=[_answer("opencode"), _answer("big-pickle")],
            ) as select:
                pair = cli._select_opencode_pair_for_settings("magenta")

    assert pair == ("opencode", "big-pickle")
    loading.assert_called_once_with(" Loading OpenCode providers and models...", spinner="dots")
    model_choices = select.call_args_list[1].kwargs["choices"]
    assert [choice.value for choice in model_choices] == ["big-pickle", "back"]
    assert "free" in model_choices[0].title
    assert select.call_args_list[0].kwargs["use_jk_keys"] is False
    assert select.call_args_list[1].kwargs["use_search_filter"] is True
    assert select.call_args_list[1].kwargs["use_jk_keys"] is False


def test_opencode_pair_is_saved_atomically():
    """Settings never persist only one half of a provider/model pair."""
    with patch.object(cli.questionary, "select", return_value=_answer("opencode_pair")):
        with patch.object(cli, "_select_opencode_pair_for_settings", return_value=("google", "gemini-3-flash")):
            with patch.object(cli.config_manager, "update") as update:
                assert cli._handle_settings_action("magenta") is True

    update.assert_called_once_with({"opencode_provider": "google", "opencode_model": "gemini-3-flash"})


def test_opencode_pair_picker_explains_server_authentication():
    """A password-protected server produces a settings-specific auth hint."""
    request = httpx.Request("GET", "http://127.0.0.1:4096/config/providers")
    response = httpx.Response(401, request=request)
    error = httpx.HTTPStatusError("unauthorized", request=request, response=response)
    with patch.object(
        cli,
        "_load_opencode_catalog_for_settings",
        new=AsyncMock(side_effect=error),
    ):
        with patch.object(cli.console, "print") as print_message:
            assert cli._select_opencode_pair_for_settings() is None

    output = " ".join(str(call.args[0]) for call in print_message.call_args_list)
    assert "OPENCODE_SERVER_PASSWORD" in output
