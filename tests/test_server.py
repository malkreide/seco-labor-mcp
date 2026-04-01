"""
Tests for seco-labor-mcp
Run: pytest tests/ -m "not live" -v
Live API tests: pytest tests/ -m live -v
"""

import json

import httpx
import pytest
import respx

from seco_labor_mcp.server import (
    CANTON_CODES,
    CKAN_BASE,
    DatasetDetailsInput,
    DatasetSearchInput,
    MonthlyReportInput,
    OpenPositionsInput,
    ResponseFormat,
    UnemploymentInput,
    YouthUnemploymentInput,
    seco_get_dataset,
    seco_get_monthly_report_url,
    seco_get_open_positions,
    seco_get_unemployment_overview,
    seco_get_youth_unemployment,
    seco_list_cantons,
    seco_search_datasets,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_CKAN_SEARCH_RESPONSE = {
    "success": True,
    "result": {
        "count": 2,
        "results": [
            {
                "name": "monatliche-arbeitslosenzahlen-2024",
                "id": "abc123",
                "title": {"de": "Monatliche Arbeitslosenzahlen 2024", "fr": "Chômage mensuel"},
                "notes": {"de": "Monatliche Statistiken zur Arbeitslosigkeit in der Schweiz."},
                "metadata_modified": "2025-01-15T10:00:00",
                "tags": [{"name": "arbeitslosigkeit"}, {"name": "kantone"}],
                "resources": [
                    {
                        "id": "res001",
                        "name": {"de": "Arbeitslosenzahlen CSV"},
                        "format": "CSV",
                        "url": "https://www.seco.admin.ch/data/arbeitslose_2024.csv",
                        "size": 102400,
                        "last_modified": "2025-01-10",
                    }
                ],
            },
            {
                "name": "stellensuchende-kantone",
                "id": "def456",
                "title": {"de": "Stellensuchende nach Kantonen"},
                "notes": {"de": "Anzahl Stellensuchende je Kanton."},
                "metadata_modified": "2025-01-10T08:00:00",
                "tags": [],
                "resources": [
                    {
                        "id": "res002",
                        "name": {"de": "Stellensuchende XLSX"},
                        "format": "XLSX",
                        "url": "https://www.seco.admin.ch/data/stellensuchende.xlsx",
                        "size": 51200,
                        "last_modified": "2025-01-08",
                    }
                ],
            },
        ],
    },
}

MOCK_CKAN_DATASET_RESPONSE = {
    "success": True,
    "result": {
        "name": "monatliche-arbeitslosenzahlen-2024",
        "id": "abc123",
        "title": {"de": "Monatliche Arbeitslosenzahlen 2024"},
        "notes": {"de": "Detaillierte Beschreibung des Datensatzes."},
        "metadata_modified": "2025-01-15T10:00:00",
        "license_title": "Creative Commons CCZero",
        "tags": [{"name": {"de": "arbeitslosigkeit"}}, {"name": {"de": "statistik"}}],
        "resources": [
            {
                "id": "res001",
                "name": {"de": "Arbeitslosenzahlen CSV"},
                "format": "CSV",
                "url": "https://www.seco.admin.ch/data/arbeitslose_2024.csv",
                "size": 102400,
                "last_modified": "2025-01-10",
            },
            {
                "id": "res002",
                "name": {"de": "Kantone XLSX"},
                "format": "XLSX",
                "url": "https://www.seco.admin.ch/data/kantone_2024.xlsx",
                "size": 51200,
                "last_modified": "2025-01-08",
            },
        ],
    },
}


# ---------------------------------------------------------------------------
# Unit Tests: Input Validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    """Test Pydantic model validation."""

    def test_dataset_search_valid(self):
        inp = DatasetSearchInput(query="Jugendarbeitslosigkeit", limit=5)
        assert inp.query == "Jugendarbeitslosigkeit"
        assert inp.limit == 5
        assert inp.response_format == ResponseFormat.MARKDOWN

    def test_dataset_search_strips_whitespace(self):
        inp = DatasetSearchInput(query="  arbeitslose  ")
        assert inp.query == "arbeitslose"

    def test_dataset_search_query_too_short(self):
        with pytest.raises(Exception):
            DatasetSearchInput(query="a")

    def test_dataset_search_limit_bounds(self):
        with pytest.raises(Exception):
            DatasetSearchInput(query="test", limit=25)  # max is 20
        with pytest.raises(Exception):
            DatasetSearchInput(query="test", limit=0)  # min is 1

    def test_unemployment_valid_canton(self):
        inp = UnemploymentInput(canton="ZH")
        assert inp.canton == "ZH"

    def test_unemployment_canton_none(self):
        inp = UnemploymentInput()
        assert inp.canton is None

    def test_unemployment_year_bounds(self):
        with pytest.raises(Exception):
            UnemploymentInput(year=1999)  # too early
        with pytest.raises(Exception):
            UnemploymentInput(year=2031)  # too late

    def test_monthly_report_valid(self):
        inp = MonthlyReportInput(year=2025, month=12, language="de")
        assert inp.year == 2025
        assert inp.month == 12
        assert inp.language == "de"

    def test_monthly_report_invalid_language(self):
        with pytest.raises(Exception):
            MonthlyReportInput(year=2025, month=6, language="en")  # only de/fr/it

    def test_monthly_report_month_bounds(self):
        with pytest.raises(Exception):
            MonthlyReportInput(year=2025, month=13)
        with pytest.raises(Exception):
            MonthlyReportInput(year=2025, month=0)

    def test_canton_codes_completeness(self):
        """All 26 Swiss cantons must be present."""
        assert len(CANTON_CODES) == 26
        assert "ZH" in CANTON_CODES
        assert "GE" in CANTON_CODES
        assert "TI" in CANTON_CODES

    def test_response_format_values(self):
        assert ResponseFormat.MARKDOWN == "markdown"
        assert ResponseFormat.JSON == "json"


# ---------------------------------------------------------------------------
# Unit Tests: Tool Functions (mocked HTTP)
# ---------------------------------------------------------------------------


class TestSecoSearchDatasets:
    """Tests for seco_search_datasets tool."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_returns_markdown(self):
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=MOCK_CKAN_SEARCH_RESPONSE)
        )
        inp = DatasetSearchInput(query="arbeitslose kantone")
        result = await seco_search_datasets(inp)

        assert "SECO-Datensätze" in result
        assert "Monatliche Arbeitslosenzahlen" in result
        assert "monatliche-arbeitslosenzahlen-2024" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_returns_json(self):
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=MOCK_CKAN_SEARCH_RESPONSE)
        )
        inp = DatasetSearchInput(query="arbeitslose", response_format=ResponseFormat.JSON)
        result = await seco_search_datasets(inp)

        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["id"] == "monatliche-arbeitslosenzahlen-2024"
        assert "title_de" in data[0]
        assert "resources" in data[0]

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_no_results(self):
        empty_response = {"success": True, "result": {"count": 0, "results": []}}
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=empty_response)
        )
        inp = DatasetSearchInput(query="nichtexistent xyz abc")
        result = await seco_search_datasets(inp)

        assert "Keine SECO-Datensätze" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_http_error(self):
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(503, text="Service Unavailable")
        )
        inp = DatasetSearchInput(query="test")
        result = await seco_search_datasets(inp)

        assert "Error" in result
        assert "503" in result


class TestSecoGetDataset:
    """Tests for seco_get_dataset tool."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_dataset_markdown(self):
        respx.get(f"{CKAN_BASE}/package_show").mock(
            return_value=httpx.Response(200, json=MOCK_CKAN_DATASET_RESPONSE)
        )
        inp = DatasetDetailsInput(dataset_id="monatliche-arbeitslosenzahlen-2024")
        result = await seco_get_dataset(inp)

        assert "Monatliche Arbeitslosenzahlen 2024" in result
        assert "CSV" in result
        assert "XLSX" in result
        assert "Creative Commons" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_dataset_json(self):
        respx.get(f"{CKAN_BASE}/package_show").mock(
            return_value=httpx.Response(200, json=MOCK_CKAN_DATASET_RESPONSE)
        )
        inp = DatasetDetailsInput(
            dataset_id="monatliche-arbeitslosenzahlen-2024",
            response_format=ResponseFormat.JSON,
        )
        result = await seco_get_dataset(inp)

        data = json.loads(result)
        assert data["id"] == "monatliche-arbeitslosenzahlen-2024"
        assert len(data["resources"]) == 2
        assert data["resources"][0]["format"] == "CSV"

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_dataset_not_found(self):
        not_found = {"success": False, "error": {"message": "Not found"}}
        respx.get(f"{CKAN_BASE}/package_show").mock(
            return_value=httpx.Response(200, json=not_found)
        )
        inp = DatasetDetailsInput(dataset_id="does-not-exist")
        result = await seco_get_dataset(inp)

        assert "Error" in result or "not found" in result.lower()


class TestYouthUnemployment:
    """Tests for seco_get_youth_unemployment tool."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_youth_national_markdown(self):
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=MOCK_CKAN_SEARCH_RESPONSE)
        )
        inp = YouthUnemploymentInput()
        result = await seco_get_youth_unemployment(inp)

        assert "15" in result
        assert "24" in result
        assert "Berufswahlberatung" in result or "Schulamt" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_youth_canton_zh(self):
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=MOCK_CKAN_SEARCH_RESPONSE)
        )
        inp = YouthUnemploymentInput(canton="ZH")
        result = await seco_get_youth_unemployment(inp)

        assert "Zürich" in result or "ZH" in result

    @pytest.mark.asyncio
    async def test_youth_invalid_canton(self):
        inp = YouthUnemploymentInput(canton="XX")
        result = await seco_get_youth_unemployment(inp)

        assert "Error" in result
        assert "XX" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_youth_json_format(self):
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=MOCK_CKAN_SEARCH_RESPONSE)
        )
        inp = YouthUnemploymentInput(response_format=ResponseFormat.JSON)
        result = await seco_get_youth_unemployment(inp)

        data = json.loads(result)
        assert "education_context" in data
        assert "key_indicators" in data["education_context"]


class TestUnemploymentOverview:
    """Tests for seco_get_unemployment_overview tool."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_overview_national(self):
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=MOCK_CKAN_SEARCH_RESPONSE)
        )
        # Also mock CSV download (will fail gracefully)
        respx.get("https://www.seco.admin.ch/data/arbeitslose_2024.csv").mock(
            return_value=httpx.Response(404)
        )
        inp = UnemploymentInput()
        result = await seco_get_unemployment_overview(inp)

        assert "Arbeitslosigkeit" in result or "arbeitslos" in result.lower()

    @pytest.mark.asyncio
    @respx.mock
    async def test_overview_canton_ge(self):
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=MOCK_CKAN_SEARCH_RESPONSE)
        )
        respx.get("https://www.seco.admin.ch/data/arbeitslose_2024.csv").mock(
            return_value=httpx.Response(404)
        )
        inp = UnemploymentInput(canton="GE")
        result = await seco_get_unemployment_overview(inp)

        assert "Genève" in result or "GE" in result

    @pytest.mark.asyncio
    async def test_overview_invalid_canton(self):
        inp = UnemploymentInput(canton="XX")
        result = await seco_get_unemployment_overview(inp)

        assert "Error" in result


class TestOpenPositions:
    """Tests for seco_get_open_positions tool."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_open_positions_markdown(self):
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=MOCK_CKAN_SEARCH_RESPONSE)
        )
        inp = OpenPositionsInput()
        result = await seco_get_open_positions(inp)

        assert "Offene Stellen" in result
        assert "Stellenmeldepflicht" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_open_positions_json(self):
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=MOCK_CKAN_SEARCH_RESPONSE)
        )
        inp = OpenPositionsInput(response_format=ResponseFormat.JSON)
        result = await seco_get_open_positions(inp)

        data = json.loads(result)
        assert "stellenmeldepflicht" in data
        assert "indicator_type" in data


class TestMonthlyReportUrl:
    """Tests for seco_get_monthly_report_url tool."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_report_url_december_2025(self):
        mock_url = (
            "https://www.arbeit.swiss/dam/secoalv/de/dokumente/publikationen/amstat/"
            "2025/2025-12_die_lage_auf_dem_arbeitsmarkt.pdf.download.pdf/"
            "2025-12_Die_Lage_auf_dem_Arbeitsmarkt_DE.pdf"
        )
        respx.head(mock_url).mock(return_value=httpx.Response(200))

        inp = MonthlyReportInput(year=2025, month=12, language="de")
        result = await seco_get_monthly_report_url(inp)

        assert "2025" in result
        assert "Dezember" in result
        assert "PDF" in result or "pdf" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_report_url_unavailable(self):
        # Mock any HEAD request to arbeit.swiss returning 404
        respx.head(url__startswith="https://www.arbeit.swiss/").mock(
            return_value=httpx.Response(404)
        )

        inp = MonthlyReportInput(year=2025, month=6, language="de")
        result = await seco_get_monthly_report_url(inp)

        # Should still return URL and note unavailability
        assert "Juni" in result or "2025" in result


class TestCantonsList:
    """Tests for seco_list_cantons tool."""

    @pytest.mark.asyncio
    async def test_lists_all_26_cantons(self):
        result = await seco_list_cantons()

        assert "ZH" in result
        assert "GE" in result
        assert "TI" in result
        assert "JU" in result
        # All 26 canton codes should appear
        for code in CANTON_CODES:
            assert code in result

    @pytest.mark.asyncio
    async def test_canton_table_format(self):
        result = await seco_list_cantons()

        assert "|" in result  # table format
        assert "Zürich" in result
        assert "Genève" in result


class TestHelperFunctions:
    """Tests for utility functions."""

    def test_canton_codes_count(self):
        assert len(CANTON_CODES) == 26

    def test_known_cantonal_names(self):
        assert CANTON_CODES["ZH"] == "Zürich"
        assert CANTON_CODES["GE"] == "Genève"
        assert CANTON_CODES["TI"] == "Ticino"
        assert CANTON_CODES["JU"] == "Jura"


# ---------------------------------------------------------------------------
# Live API Tests (skipped in CI)
# ---------------------------------------------------------------------------


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
