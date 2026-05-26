"""
Unit tests for seco-labor-mcp (mocked HTTP via respx, no internet access).

Run: pytest tests/test_unit.py -v        # default in CI
Live tests live in tests/test_live.py and are skipped unless --run-live.
"""

import json

import httpx
import pytest
import respx

from seco_labor_mcp import server as _server_mod
from seco_labor_mcp.server import (
    CANTON_CODES,
    CKAN_BASE,
    DatasetDetailsInput,
    DatasetSearchInput,
    JobSeekersInput,
    MonthlyReportInput,
    OccupationInput,
    OpenPositionsInput,
    ResponseFormat,
    UnemploymentInput,
    UrlNotAllowedError,
    YouthUnemploymentInput,
    _detect_latest_period,
    _parse_csv,
    _select_rows_for_canton,
    _validate_external_url,
    seco_get_dataset,
    seco_get_job_seekers,
    seco_get_monthly_report_url,
    seco_get_open_positions,
    seco_get_unemployment_by_occupation,
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

    def test_occupation_input_default_markdown(self):
        inp = OccupationInput()
        assert inp.response_format == ResponseFormat.MARKDOWN

    def test_occupation_input_rejects_unknown_format(self):
        with pytest.raises(Exception):
            OccupationInput(response_format="csv")  # type: ignore[arg-type]

    def test_occupation_input_rejects_extra_fields(self):
        with pytest.raises(Exception):
            OccupationInput(canton="ZH")  # type: ignore[call-arg]


class TestOccupationTool:
    """Tests for seco_get_unemployment_by_occupation with the new Pydantic input."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_occupation_markdown(self):
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json={"result": {"results": []}})
        )
        result = await seco_get_unemployment_by_occupation(OccupationInput())
        assert "Berufshauptgruppe" in result or "Berufsgruppe" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_occupation_json(self):
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json={"result": {"results": []}})
        )
        inp = OccupationInput(response_format=ResponseFormat.JSON)
        result = await seco_get_unemployment_by_occupation(inp)
        data = json.loads(result)
        assert "education_implications" in data


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
    async def test_search_protocol_error_5xx_is_raised(self):
        """OBS-001: 5xx is a protocol-level failure and must propagate as an
        exception so the MCP layer reports isError, not as a success-string."""
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(503, text="Service Unavailable")
        )
        inp = DatasetSearchInput(query="test")
        with pytest.raises(httpx.HTTPStatusError):
            await seco_search_datasets(inp)

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_execution_error_429_returns_string(self):
        """OBS-001: 429 is an execution error — caller can back off and retry,
        so we return a user-facing string instead of raising."""
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(429, text="Too Many Requests")
        )
        inp = DatasetSearchInput(query="test")
        result = await seco_search_datasets(inp)
        assert "Rate limit" in result


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
# CSV parser tests (pure functions, no HTTP)
# ---------------------------------------------------------------------------


SAMPLE_CSV_SEMICOLON = (
    "Datum;Kanton;Arbeitslose;Quote_pct\n"
    "2025-10;CH;140000;3.0\n"
    "2025-10;ZH;25000;2.5\n"
    "2025-10;GE;15000;4.4\n"
    "2025-11;CH;143500;3.1\n"
    "2025-11;ZH;25800;2.6\n"
    "2025-11;GE;15200;4.5\n"
    "2025-12;CH;147275;3.2\n"
    "2025-12;ZH;26500;2.7\n"
    "2025-12;GE;15400;4.5\n"
)


class TestCsvParser:
    """Tests for the defensive CSV parser helpers."""

    def test_parse_semicolon_csv(self):
        parsed = _parse_csv(SAMPLE_CSV_SEMICOLON)
        assert parsed["parsed"] is True
        assert parsed["delimiter"] == ";"
        assert parsed["headers"] == ["Datum", "Kanton", "Arbeitslose", "Quote_pct"]
        assert len(parsed["rows"]) == 9

    def test_parse_comma_csv(self):
        comma_csv = "year,canton,unemployed\n2025,ZH,25000\n2025,GE,15000\n"
        parsed = _parse_csv(comma_csv)
        assert parsed["parsed"] is True
        assert parsed["delimiter"] == ","
        assert len(parsed["rows"]) == 2

    def test_parse_empty_csv(self):
        assert _parse_csv("")["parsed"] is False
        assert _parse_csv("only_header_no_rows\n")["parsed"] is False

    def test_detect_latest_period(self):
        parsed = _parse_csv(SAMPLE_CSV_SEMICOLON)
        assert _detect_latest_period(parsed) == "2025-12"

    def test_detect_period_returns_none_when_absent(self):
        parsed = _parse_csv("a;b\n1;2\n3;4\n")
        assert _detect_latest_period(parsed) is None

    def test_select_rows_canton_filter(self):
        parsed = _parse_csv(SAMPLE_CSV_SEMICOLON)
        zh = _select_rows_for_canton(parsed, "ZH", limit=10)
        assert len(zh) == 3
        assert all("ZH" in row for row in zh)

    def test_select_rows_no_canton(self):
        parsed = _parse_csv(SAMPLE_CSV_SEMICOLON)
        all_recent = _select_rows_for_canton(parsed, None, limit=4)
        assert len(all_recent) == 4

    def test_select_rows_unknown_canton(self):
        parsed = _parse_csv(SAMPLE_CSV_SEMICOLON)
        assert _select_rows_for_canton(parsed, "XX", limit=5) == []


class TestUnemploymentOverviewLiveCsv:
    """Tests that the overview tool surfaces parsed CSV data when available."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_overview_with_live_csv_json(self):
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=MOCK_CKAN_SEARCH_RESPONSE)
        )
        respx.get("https://www.seco.admin.ch/data/arbeitslose_2024.csv").mock(
            return_value=httpx.Response(
                200,
                content=SAMPLE_CSV_SEMICOLON.encode("utf-8"),
                headers={"content-type": "text/csv"},
            )
        )
        inp = UnemploymentInput(response_format=ResponseFormat.JSON)
        result = await seco_get_unemployment_overview(inp)
        data = json.loads(result)

        assert data["data_available"] is True
        assert "live" in data
        assert data["live"]["data_source"] == "live_csv"
        assert data["live"]["reference_period"] == "2025-12"
        assert data["live"]["total_rows"] == 9
        assert data["live"]["headers"] == ["Datum", "Kanton", "Arbeitslose", "Quote_pct"]
        # snapshot must NOT be included when live data is available
        assert "reference_snapshot" not in data

    @pytest.mark.asyncio
    @respx.mock
    async def test_overview_live_csv_canton_filter_zh(self):
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=MOCK_CKAN_SEARCH_RESPONSE)
        )
        respx.get("https://www.seco.admin.ch/data/arbeitslose_2024.csv").mock(
            return_value=httpx.Response(200, content=SAMPLE_CSV_SEMICOLON.encode("utf-8"))
        )
        inp = UnemploymentInput(canton="ZH", response_format=ResponseFormat.JSON)
        result = await seco_get_unemployment_overview(inp)
        data = json.loads(result)

        sample = data["live"]["sample_rows"]
        assert len(sample) == 3
        assert all("ZH" in row for row in sample)

    @pytest.mark.asyncio
    @respx.mock
    async def test_overview_live_csv_markdown(self):
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=MOCK_CKAN_SEARCH_RESPONSE)
        )
        respx.get("https://www.seco.admin.ch/data/arbeitslose_2024.csv").mock(
            return_value=httpx.Response(200, content=SAMPLE_CSV_SEMICOLON.encode("utf-8"))
        )
        inp = UnemploymentInput()
        result = await seco_get_unemployment_overview(inp)

        assert "Live-Daten" in result
        assert "2025-12" in result
        # The static snapshot warning must NOT appear when live data is shown
        assert "statischer Referenz-Snapshot" not in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_overview_falls_back_to_snapshot_when_csv_404(self):
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=MOCK_CKAN_SEARCH_RESPONSE)
        )
        respx.get("https://www.seco.admin.ch/data/arbeitslose_2024.csv").mock(
            return_value=httpx.Response(404)
        )
        inp = UnemploymentInput(response_format=ResponseFormat.JSON)
        result = await seco_get_unemployment_overview(inp)
        data = json.loads(result)

        assert data["data_available"] is False
        assert "reference_snapshot" in data
        assert data["reference_snapshot"]["data_source"] == "static_reference"

    @pytest.mark.asyncio
    @respx.mock
    async def test_overview_cache_reuses_response(self):
        """Second call within TTL must not trigger a second HTTP fetch."""
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=MOCK_CKAN_SEARCH_RESPONSE)
        )
        csv_route = respx.get("https://www.seco.admin.ch/data/arbeitslose_2024.csv").mock(
            return_value=httpx.Response(200, content=SAMPLE_CSV_SEMICOLON.encode("utf-8"))
        )
        await seco_get_unemployment_overview(UnemploymentInput())
        await seco_get_unemployment_overview(UnemploymentInput())
        assert csv_route.call_count == 1


# ---------------------------------------------------------------------------
# Live-CSV path for youth + job seekers
# ---------------------------------------------------------------------------


YOUTH_CSV = (
    "Datum;Kanton;Altersgruppe;Arbeitslose\n"
    "2025-11;CH;15-24;14200\n"
    "2025-11;ZH;15-24;2700\n"
    "2025-12;CH;15-24;15100\n"
    "2025-12;ZH;15-24;2880\n"
)

JOB_SEEKERS_CSV = (
    "Datum;Kanton;Stellensuchende;Arbeitslose\n"
    "2025-11;CH;230100;143500\n"
    "2025-11;GE;14800;13200\n"
    "2025-12;CH;233900;147275\n"
    "2025-12;GE;15100;13400\n"
)


def _ckan_search_with_csv(url: str, title: str = "Live") -> dict:
    """Build a minimal CKAN search response advertising a single CSV resource."""
    return {
        "success": True,
        "result": {
            "count": 1,
            "results": [
                {
                    "name": "live-dataset",
                    "id": "live123",
                    "title": {"de": title},
                    "notes": {"de": "Live test dataset."},
                    "metadata_modified": "2025-12-15T10:00:00",
                    "tags": [],
                    "resources": [
                        {
                            "id": "live-res",
                            "name": {"de": "Live CSV"},
                            "format": "CSV",
                            "url": url,
                            "size": 1024,
                            "last_modified": "2025-12-12",
                        }
                    ],
                }
            ],
        },
    }


class TestYouthLiveCsv:
    """Live-CSV path for seco_get_youth_unemployment."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_youth_live_json(self):
        csv_url = "https://www.seco.admin.ch/data/jugend_altersgruppe.csv"
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=_ckan_search_with_csv(csv_url, "Jugend"))
        )
        respx.get(csv_url).mock(
            return_value=httpx.Response(200, content=YOUTH_CSV.encode("utf-8"))
        )
        inp = YouthUnemploymentInput(response_format=ResponseFormat.JSON)
        result = await seco_get_youth_unemployment(inp)
        data = json.loads(result)

        assert data["data"]["data_source"] == "live_csv"
        assert data["data"]["reference_period"] == "2025-12"
        assert data["data"]["headers"] == ["Datum", "Kanton", "Altersgruppe", "Arbeitslose"]
        assert "reference_snapshot" not in data["data"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_youth_live_markdown_shows_live_block(self):
        csv_url = "https://www.seco.admin.ch/data/jugend_altersgruppe.csv"
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=_ckan_search_with_csv(csv_url, "Jugend"))
        )
        respx.get(csv_url).mock(
            return_value=httpx.Response(200, content=YOUTH_CSV.encode("utf-8"))
        )
        result = await seco_get_youth_unemployment(YouthUnemploymentInput())
        assert "Live-Daten" in result
        assert "2025-12" in result
        assert "statischer Referenz-Snapshot" not in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_youth_canton_filter_zh(self):
        csv_url = "https://www.seco.admin.ch/data/jugend_altersgruppe.csv"
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=_ckan_search_with_csv(csv_url))
        )
        respx.get(csv_url).mock(
            return_value=httpx.Response(200, content=YOUTH_CSV.encode("utf-8"))
        )
        inp = YouthUnemploymentInput(canton="ZH", response_format=ResponseFormat.JSON)
        data = json.loads(await seco_get_youth_unemployment(inp))
        sample = data["data"]["sample_rows"]
        assert sample
        assert all("ZH" in row for row in sample)

    @pytest.mark.asyncio
    @respx.mock
    async def test_youth_falls_back_to_snapshot_on_404(self):
        csv_url = "https://www.seco.admin.ch/data/jugend_altersgruppe.csv"
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=_ckan_search_with_csv(csv_url))
        )
        respx.get(csv_url).mock(return_value=httpx.Response(404))
        inp = YouthUnemploymentInput(response_format=ResponseFormat.JSON)
        data = json.loads(await seco_get_youth_unemployment(inp))
        assert "reference_snapshot" in data["data"]
        assert data["data"]["reference_snapshot"]["data_source"] == "static_reference"


class TestJobSeekersLiveCsv:
    """Live-CSV path for seco_get_job_seekers."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_job_seekers_live_json(self):
        csv_url = "https://www.seco.admin.ch/data/stellensuchende_kantone.csv"
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=_ckan_search_with_csv(csv_url, "Stellensuchende"))
        )
        respx.get(csv_url).mock(
            return_value=httpx.Response(200, content=JOB_SEEKERS_CSV.encode("utf-8"))
        )
        inp = JobSeekersInput(response_format=ResponseFormat.JSON)
        result = await seco_get_job_seekers(inp)
        data = json.loads(result)

        assert "live" in data
        assert data["live"]["data_source"] == "live_csv"
        assert data["live"]["reference_period"] == "2025-12"
        assert data["live"]["headers"] == [
            "Datum", "Kanton", "Stellensuchende", "Arbeitslose",
        ]
        assert "reference_snapshot" not in data

    @pytest.mark.asyncio
    @respx.mock
    async def test_job_seekers_canton_filter_ge(self):
        csv_url = "https://www.seco.admin.ch/data/stellensuchende_kantone.csv"
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=_ckan_search_with_csv(csv_url))
        )
        respx.get(csv_url).mock(
            return_value=httpx.Response(200, content=JOB_SEEKERS_CSV.encode("utf-8"))
        )
        inp = JobSeekersInput(canton="GE", response_format=ResponseFormat.JSON)
        data = json.loads(await seco_get_job_seekers(inp))
        sample = data["live"]["sample_rows"]
        assert sample
        assert all("GE" in row for row in sample)

    @pytest.mark.asyncio
    @respx.mock
    async def test_job_seekers_falls_back_to_snapshot_on_404(self):
        csv_url = "https://www.seco.admin.ch/data/stellensuchende_kantone.csv"
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=_ckan_search_with_csv(csv_url))
        )
        respx.get(csv_url).mock(return_value=httpx.Response(404))
        inp = JobSeekersInput(response_format=ResponseFormat.JSON)
        data = json.loads(await seco_get_job_seekers(inp))
        assert "reference_snapshot" in data
        assert "live" not in data


# ---------------------------------------------------------------------------
# SEC-004 SSRF validator
# ---------------------------------------------------------------------------


class TestSsrfValidator:
    """Tests for _validate_external_url (SEC-004)."""

    def test_https_public_host_is_allowed(self):
        # No exception means the URL passed validation.
        _validate_external_url("https://opendata.swiss/api/3/action/package_search")

    def test_http_scheme_is_rejected(self):
        with pytest.raises(UrlNotAllowedError, match="https"):
            _validate_external_url("http://opendata.swiss/foo")

    def test_file_scheme_is_rejected(self):
        with pytest.raises(UrlNotAllowedError):
            _validate_external_url("file:///etc/passwd")

    def test_missing_host_is_rejected(self):
        with pytest.raises(UrlNotAllowedError):
            _validate_external_url("https:///just-a-path")

    def test_loopback_literal_is_rejected(self):
        with pytest.raises(UrlNotAllowedError, match="non-public"):
            _validate_external_url("https://127.0.0.1/foo")

    def test_private_rfc1918_literal_is_rejected(self):
        with pytest.raises(UrlNotAllowedError, match="non-public"):
            _validate_external_url("https://10.0.0.1/admin")

    def test_link_local_metadata_endpoint_is_rejected(self):
        # AWS/GCP/Azure metadata service shared address.
        with pytest.raises(UrlNotAllowedError, match="non-public"):
            _validate_external_url("https://169.254.169.254/latest/meta-data/")

    @pytest.mark.asyncio
    async def test_csv_fetch_skips_internal_url(self):
        """_fetch_text_cached must return None when the URL is rejected,
        without ever opening a socket to it."""
        result = await _server_mod._fetch_text_cached("http://169.254.169.254/csv")
        assert result is None
