"""Exercise the real HTTP + parsing stack against the local fixture site.

requests and aiohttp are core runtime deps; beautifulsoup4 (backed by
soupsieve's CSS engine) and markdownify ship in the [collector] extra.
All four are pinned only by floor in pyproject, so a bad bump would sail
through the mocked suite — here they do real I/O and real parsing.
"""

import aiohttp
import pytest
import requests

from tests.localserver import FIXTURE_PRODUCTS


def test_requests_fetches_fixture_json(fixture_site):
    response = requests.get(f"{fixture_site}/api/products", timeout=10)
    response.raise_for_status()
    assert response.json()["products"] == FIXTURE_PRODUCTS


async def test_aiohttp_fetches_fixture_json(fixture_site):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{fixture_site}/api/products") as response:
            response.raise_for_status()
            payload = await response.json()
    assert payload["products"] == FIXTURE_PRODUCTS


def test_bs4_soupsieve_css_selection(fixture_site):
    bs4 = pytest.importorskip("bs4", reason="collector extra not installed")
    html = requests.get(f"{fixture_site}/page", timeout=10).text
    soup = bs4.BeautifulSoup(html, "html.parser")
    # .select() routes through soupsieve — the CSS engine the collector
    # relies on — so a soupsieve bump that breaks selector parsing fails here.
    names = [el.get_text() for el in soup.select("div.product > span.name")]
    assert names == ["Widget", "Gadget", "Doohickey"]


def test_markdownify_converts_fixture_page(fixture_site):
    markdownify = pytest.importorskip("markdownify", reason="collector extra not installed")
    html = requests.get(f"{fixture_site}/page", timeout=10).text
    markdown = markdownify.markdownify(html)
    assert "Products" in markdown
    assert "Widget" in markdown
