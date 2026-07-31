"""Fixtures for the opt-in, real-agent e2e suite (see test_engineer_live.py)."""

import pytest

from tests.localserver import local_site


@pytest.fixture
def fixture_site():
    with local_site() as url:
        yield url
