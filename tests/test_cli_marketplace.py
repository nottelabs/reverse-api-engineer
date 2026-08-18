"""Tests for the marketplace CLI surface and the pre-capture suggestion."""

import json
from unittest.mock import patch

from click.testing import CliRunner

from reverse_api import cloud
from reverse_api.cli import _maybe_suggest_marketplace, marketplace


def _fn(function_id="f1", label="get_nfl_standings", domain="nfl.com", runs=8):
    return cloud.MarketplaceFunction(
        function_id=function_id,
        label=label,
        description="Returns NFL team standings.",
        domain=domain,
        run_count=runs,
    )


class TestMarketplaceSearchCommand:
    """`reverse-api-engineer marketplace search`."""

    def test_json_output_shape(self):
        with patch("reverse_api.cli.cloud.search", return_value=[_fn()]):
            result = CliRunner().invoke(marketplace, ["search", "nfl", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["count"] == 1
        assert payload["query"] == "nfl"
        assert payload["results"][0]["function_id"] == "f1"
        assert payload["results"][0]["url"].endswith("/f1")

    def test_site_flag_uses_domain_scoped_search(self):
        with patch("reverse_api.cli.cloud.search_for_site", return_value=[_fn()]) as scoped:
            result = CliRunner().invoke(marketplace, ["search", "--site", "https://www.nfl.com", "--json"])
        assert result.exit_code == 0
        scoped.assert_called_once()
        assert scoped.call_args.args[0] == "https://www.nfl.com"

    def test_limit_is_forwarded(self):
        with patch("reverse_api.cli.cloud.search", return_value=[]) as search:
            CliRunner().invoke(marketplace, ["search", "nfl", "-n", "3", "--json"])
        assert search.call_args.kwargs["limit"] == 3

    def test_requires_a_query_or_site(self):
        result = CliRunner().invoke(marketplace, ["search"])
        assert result.exit_code == 2

    def test_missing_query_still_emits_json_with_json_flag(self):
        result = CliRunner().invoke(marketplace, ["search", "--json"])
        assert result.exit_code == 2
        assert json.loads(result.output)["results"] == []

    def test_no_matches_is_not_an_error(self):
        with patch("reverse_api.cli.cloud.search", return_value=[]):
            result = CliRunner().invoke(marketplace, ["search", "nothing-here"])
        assert result.exit_code == 0
        assert "no hosted function matches" in result.output

    def test_human_output_lists_matches(self):
        with patch("reverse_api.cli.cloud.search", return_value=[_fn()]):
            result = CliRunner().invoke(marketplace, ["search", "nfl"])
        assert result.exit_code == 0
        assert "get_nfl_standings" in result.output

    def test_bare_group_prints_overview(self):
        result = CliRunner().invoke(marketplace, [])
        assert result.exit_code == 0
        assert cloud.MARKETPLACE_URL in result.output

    def test_network_failure_degrades_to_no_matches(self):
        # cloud.search already swallows errors, so the command sees [].
        with patch("reverse_api.cli.cloud.search", return_value=[]):
            result = CliRunner().invoke(marketplace, ["search", "nfl", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output)["count"] == 0


class TestPreCaptureSuggestion:
    """The offer shown before a capture starts."""

    def test_skipped_without_a_url(self):
        with patch("reverse_api.cli.cloud.search_for_site") as search:
            assert _maybe_suggest_marketplace(None, interactive=True) is False
        search.assert_not_called()

    def test_skipped_when_not_interactive(self):
        with patch("reverse_api.cli.cloud.search_for_site") as search:
            assert _maybe_suggest_marketplace("https://nfl.com", interactive=False) is False
        search.assert_not_called()

    def test_skipped_when_disabled(self, monkeypatch):
        monkeypatch.setenv("RAE_NO_CLOUD", "1")
        with patch("reverse_api.cli.cloud.search_for_site") as search:
            assert _maybe_suggest_marketplace("https://nfl.com", interactive=True) is False
        search.assert_not_called()

    def test_no_matches_continues_the_capture(self, monkeypatch):
        monkeypatch.delenv("RAE_NO_CLOUD", raising=False)
        with patch("reverse_api.cli.cloud.search_for_site", return_value=[]):
            assert _maybe_suggest_marketplace("https://nfl.com", interactive=True) is False

    def test_declining_continues_the_capture(self, monkeypatch):
        monkeypatch.delenv("RAE_NO_CLOUD", raising=False)
        with (
            patch("reverse_api.cli.cloud.search_for_site", return_value=[_fn()]),
            patch("reverse_api.cli.questionary.confirm") as confirm,
        ):
            confirm.return_value.ask.return_value = False
            assert _maybe_suggest_marketplace("https://nfl.com", interactive=True) is False

    def test_ctrl_c_at_the_prompt_continues_the_capture(self, monkeypatch):
        # questionary returns None when the user interrupts the prompt.
        monkeypatch.delenv("RAE_NO_CLOUD", raising=False)
        with (
            patch("reverse_api.cli.cloud.search_for_site", return_value=[_fn()]),
            patch("reverse_api.cli.questionary.confirm") as confirm,
        ):
            confirm.return_value.ask.return_value = None
            assert _maybe_suggest_marketplace("https://nfl.com", interactive=True) is False

    def test_accepting_opens_the_page_and_aborts(self, monkeypatch):
        monkeypatch.delenv("RAE_NO_CLOUD", raising=False)
        with (
            patch("reverse_api.cli.cloud.search_for_site", return_value=[_fn()]),
            patch("reverse_api.cli.questionary.confirm") as confirm,
            patch("webbrowser.open") as opener,
        ):
            confirm.return_value.ask.return_value = True
            assert _maybe_suggest_marketplace("https://nfl.com", interactive=True) is True
        opened = opener.call_args.args[0]
        assert "utm_campaign=cli_precapture" in opened
        assert "/f1" in opened

    def test_browser_failure_still_aborts_cleanly(self, monkeypatch):
        monkeypatch.delenv("RAE_NO_CLOUD", raising=False)
        with (
            patch("reverse_api.cli.cloud.search_for_site", return_value=[_fn()]),
            patch("reverse_api.cli.questionary.confirm") as confirm,
            patch("webbrowser.open", side_effect=OSError("no browser")),
        ):
            confirm.return_value.ask.return_value = True
            assert _maybe_suggest_marketplace("https://nfl.com", interactive=True) is True

    def test_lookup_crash_never_blocks_a_capture(self, monkeypatch):
        monkeypatch.delenv("RAE_NO_CLOUD", raising=False)
        with patch("reverse_api.cli.cloud.search_for_site", side_effect=RuntimeError("boom")):
            assert _maybe_suggest_marketplace("https://nfl.com", interactive=True) is False
