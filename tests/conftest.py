"""Pytest configuration for seco-labor-mcp tests."""

import pytest

from seco_labor_mcp import server as _server_mod


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "live: mark test as requiring live API access")


@pytest.fixture(autouse=True)
def _clear_csv_cache():
    """Reset the module-level CSV cache between tests so mocked responses
    from one test don't leak into another."""
    _server_mod._CSV_CACHE.clear()
    yield
    _server_mod._CSV_CACHE.clear()


def pytest_collection_modifyitems(config, items):
    """Skip live tests unless explicitly requested."""
    if not config.getoption("--run-live", default=False):
        skip_live = pytest.mark.skip(reason="Use --run-live to run live API tests")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)


def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run live API tests (requires internet connection)",
    )
