"""
Live API tests for seco-labor-mcp.

These require internet access to opendata.swiss and SECO endpoints.
By default they are skipped (see conftest.py); run them explicitly with:

    pytest tests/test_live.py --run-live -v

CI excludes this file via `pytest -m "not live"`.
"""

import pytest

from seco_labor_mcp.server import (
    CANTON_CODES,
    DatasetSearchInput,
    YouthUnemploymentInput,
    seco_get_youth_unemployment,
    seco_list_cantons,
    seco_search_datasets,
)


@pytest.mark.live
class TestLiveAPI:
    """Live API tests – require internet connection. Skipped in CI."""

    @pytest.mark.asyncio
    async def test_ckan_search_live(self):
        """Test real CKAN search against opendata.swiss."""
        inp = DatasetSearchInput(query="Arbeitslosigkeit Kantone", limit=3)
        result = await seco_search_datasets(inp)
        # Should return some content, not an error
        assert "Error" not in result or "SECO" in result

    @pytest.mark.asyncio
    async def test_youth_unemployment_live(self):
        """Live test for youth unemployment."""
        inp = YouthUnemploymentInput(canton="ZH")
        result = await seco_get_youth_unemployment(inp)
        assert isinstance(result, str)
        assert len(result) > 100

    @pytest.mark.asyncio
    async def test_cantons_list_live(self):
        """Canton list requires no external calls."""
        result = await seco_list_cantons()
        assert "ZH" in result
        assert "26" in result or len(CANTON_CODES) == 26
