"""Fixtures for the no-mock integration suite.

Everything under tests/integration runs in the default `pytest` invocation
(and therefore in the PR-gating CI job): no API keys, no external network,
no LLM. The point of these tests is to drive the *real* locked dependencies
— the mcp client/server transport chain, requests/aiohttp, bs4+soupsieve,
the installed console script — so a dependency bump that only "passes"
because the unit suite mocks everything gets caught here instead of in
production.
"""

import pytest

from tests.localserver import local_site


@pytest.fixture
def fixture_site():
    """Base URL of the local fixture site (HTML page + JSON API)."""
    with local_site() as url:
        yield url
