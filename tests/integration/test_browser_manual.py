"""Drive real Chromium via Playwright against the local fixture site.

Gated behind RAE_BROWSER_TESTS=1 rather than auto-detected: a silent skip
when the browser is merely missing would hide breakage, so CI installs
Chromium and opts in explicitly, while local runs without the browser
stay fast and skip loudly.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RAE_BROWSER_TESTS") != "1",
    reason="browser integration tests are opt-in: set RAE_BROWSER_TESTS=1 (CI does)",
)


async def test_chromium_renders_fixture_page(fixture_site):
    playwright_async = pytest.importorskip("playwright.async_api", reason="manual extra not installed")
    # The manual-capture module must import cleanly against the real
    # playwright install before we bother launching anything.
    import reverse_api.browser  # noqa: F401

    # RAE_CHROMIUM_PATH points at a system-provisioned Chromium for
    # environments where `playwright install` can't run (CI leaves it unset
    # and uses the browser it installed).
    executable_path = os.environ.get("RAE_CHROMIUM_PATH") or None

    async with playwright_async.async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path=executable_path)
        try:
            page = await browser.new_page()
            await page.goto(f"{fixture_site}/page")
            assert await page.title() == "Fixture Store"
            names = await page.locator("div.product > span.name").all_text_contents()
            assert names == ["Widget", "Gadget", "Doohickey"]
        finally:
            await browser.close()
