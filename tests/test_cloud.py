"""Tests for cloud.py - Anything marketplace lookups.

Nothing here touches the network: `requests.get` is stubbed everywhere so the
suite stays offline-safe and deterministic.
"""

import json
from types import SimpleNamespace

import pytest

from reverse_api import cloud


def _result(function_id="f1", label="get_thing", domain="example.com", runs=3, description="Does a thing."):
    return {
        "function_id": function_id,
        "label": label,
        "description": description,
        "domain": domain,
        "run_count": runs,
    }


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


@pytest.fixture
def fake_get(monkeypatch):
    """Stub requests.get and record the calls it received."""
    calls = []

    def _install(payload, status_code=200, raises=None):
        def _get(url, params=None, timeout=None, headers=None):
            calls.append(SimpleNamespace(url=url, params=params or {}, timeout=timeout, headers=headers or {}))
            if raises is not None:
                raise raises
            return _FakeResponse(payload, status_code)

        import requests

        monkeypatch.setattr(requests, "get", _get)
        return calls

    return _install


class TestRegistrableDomain:
    """Reducing a URL to the domain a marketplace entry would carry."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("https://jobs.ashbyhq.com/openai?x=1", "ashbyhq.com"),
            ("https://www.nfl.com/scores", "nfl.com"),
            ("instagram.com", "instagram.com"),
            ("www.bbc.co.uk", "bbc.co.uk"),
            ("https://shop.example.com.au/cart", "example.com.au"),
            ("HTTPS://WWW.Example.COM/", "example.com"),
            ("https://user:pw@example.com:8443/x", "example.com"),
            ("example.com.", "example.com"),
        ],
    )
    def test_extracts_domain(self, value, expected):
        assert cloud.registrable_domain(value) == expected

    @pytest.mark.parametrize(
        "value",
        ["", "   ", "not a url", "localhost", "http://192.168.1.1/x", "https://[::1]:8080/x", "/just/a/path"],
    )
    def test_rejects_unusable_input(self, value):
        assert cloud.registrable_domain(value) is None


class TestSuggestionsEnabled:
    """The kill switches."""

    def test_enabled_by_default(self, monkeypatch):
        monkeypatch.delenv("RAE_NO_CLOUD", raising=False)
        assert cloud.suggestions_enabled() is True

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
    def test_env_var_disables(self, monkeypatch, value):
        monkeypatch.setenv("RAE_NO_CLOUD", value)
        assert cloud.suggestions_enabled() is False

    def test_env_var_beats_config(self, monkeypatch):
        monkeypatch.setenv("RAE_NO_CLOUD", "1")
        cm = SimpleNamespace(get=lambda key, default=None: True)
        assert cloud.suggestions_enabled(cm) is False

    def test_config_disables(self, monkeypatch):
        monkeypatch.delenv("RAE_NO_CLOUD", raising=False)
        cm = SimpleNamespace(get=lambda key, default=None: False)
        assert cloud.suggestions_enabled(cm) is False

    def test_unset_env_is_ignored(self, monkeypatch):
        monkeypatch.setenv("RAE_NO_CLOUD", "0")
        assert cloud.suggestions_enabled() is True


class TestSearch:
    """The public marketplace search call."""

    def test_parses_results(self, fake_get):
        fake_get({"results": [_result(), _result(function_id="f2", label="other")], "total": 2})
        found = cloud.search("thing")
        assert [f.function_id for f in found] == ["f1", "f2"]
        assert found[0].label == "get_thing"
        assert found[0].run_count == 3

    def test_sends_query_and_limit(self, fake_get):
        calls = fake_get({"results": []})
        cloud.search("thing", limit=7)
        assert calls[0].params == {"q": "thing", "limit": 7}
        assert calls[0].url == cloud.SEARCH_ENDPOINT
        assert "reverse-api-engineer" in calls[0].headers["User-Agent"]

    def test_blank_query_skips_the_call(self, fake_get):
        calls = fake_get({"results": [_result()]})
        assert cloud.search("   ") == []
        assert calls == []

    def test_non_200_returns_empty(self, fake_get):
        fake_get({"results": [_result()]}, status_code=500)
        assert cloud.search("thing") == []

    def test_network_error_returns_empty(self, fake_get):
        fake_get(None, raises=OSError("no route to host"))
        assert cloud.search("thing") == []

    def test_invalid_json_returns_empty(self, fake_get):
        fake_get(json.JSONDecodeError("bad", "", 0))
        assert cloud.search("thing") == []

    @pytest.mark.parametrize("payload", [[], "nope", None, {"results": "nope"}, {}])
    def test_unexpected_shapes_return_empty(self, fake_get, payload):
        fake_get(payload)
        assert cloud.search("thing") == []

    def test_skips_malformed_entries(self, fake_get):
        fake_get(
            {
                "results": [
                    {"label": "no id"},
                    {"function_id": "f2"},
                    "not a dict",
                    _result(function_id="f3", runs="not-a-number"),
                ]
            }
        )
        found = cloud.search("thing")
        assert [f.function_id for f in found] == ["f3"]
        assert found[0].run_count == 0

    def test_url_points_at_the_function_page(self, fake_get):
        fake_get({"results": [_result(function_id="abc")]})
        assert cloud.search("thing")[0].url == f"{cloud.MARKETPLACE_URL}/abc"


class TestSearchForSite:
    """Domain-scoped lookups must never surface an unrelated site."""

    def test_keeps_matching_domains_only(self, fake_get):
        fake_get(
            {
                "results": [
                    _result(function_id="a", domain="nfl.com", runs=2),
                    _result(function_id="b", domain="fantasy.nfl.com", runs=9),
                    _result(function_id="c", domain="paisabazaar.com", runs=99),
                    _result(function_id="d", domain="notnfl.com", runs=50),
                ]
            }
        )
        found = cloud.search_for_site("https://www.nfl.com/standings")
        assert [f.function_id for f in found] == ["b", "a"]

    def test_queries_the_registrable_domain(self, fake_get):
        calls = fake_get({"results": []})
        cloud.search_for_site("https://jobs.ashbyhq.com/openai")
        assert calls[0].params["q"] == "ashbyhq.com"

    def test_unrelated_results_yield_nothing(self, fake_get):
        # The live endpoint ranks rather than filters, so a site it has never
        # seen still comes back full of other people's functions.
        fake_get({"results": [_result(domain="paisabazaar.com"), _result(domain="ratings.fide.com")]})
        assert cloud.search_for_site("https://jobs.ashbyhq.com/openai") == []

    def test_respects_limit(self, fake_get):
        fake_get({"results": [_result(function_id=f"f{i}", domain="nfl.com", runs=i) for i in range(10)]})
        assert len(cloud.search_for_site("nfl.com", limit=2)) == 2

    def test_unusable_url_skips_the_call(self, fake_get):
        calls = fake_get({"results": [_result()]})
        assert cloud.search_for_site("localhost") == []
        assert calls == []


class TestCloudLink:
    """UTM tagging for attribution."""

    def test_adds_tags(self):
        tagged = cloud.cloud_link(cloud.CLOUD_URL, "cli_precapture")
        assert tagged.startswith(f"{cloud.CLOUD_URL}?")
        assert "utm_source=rae" in tagged
        assert "utm_medium=cli" in tagged
        assert "utm_campaign=cli_precapture" in tagged

    def test_appends_to_existing_query(self):
        tagged = cloud.cloud_link("https://anything.notte.cc/x?a=1", "somewhere")
        assert "?a=1&utm_source=rae" in tagged
