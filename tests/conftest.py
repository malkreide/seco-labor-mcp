"""Pytest configuration for seco-labor-mcp tests."""

import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "live: mark test as requiring live API access")


# Der modulweite CSV-Cache ist mit dem CSV-Zweig entfallen; die Fixture, die
# ihn zwischen den Tests leerte, deshalb ebenfalls. Der neue Abrufweg
# (`_fetch_bytes_with_retry`) haelt keinen Zustand ueber einen Aufruf hinaus —
# es gibt nichts mehr, was von einem Test in den naechsten lecken koennte.


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
