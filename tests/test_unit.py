"""
Unit tests for seco-labor-mcp (mocked HTTP via respx, no internet access).

Run: pytest tests/test_unit.py -v        # default in CI
Live tests live in tests/test_live.py and are skipped unless --run-live.
"""

import json

import httpx
import pytest
import respx
from pydantic import ValidationError

from seco_labor_mcp import server as _server_mod
from seco_labor_mcp import sources
from seco_labor_mcp.server import (
    CANTON_CODES,
    CKAN_BASE,
    DatasetDetailsInput,
    DatasetSearchInput,
    MonthlyReportInput,
    OccupationInput,
    OpenPositionsInput,
    ResponseFormat,
    UnemploymentInput,
    UrlNotAllowedError,
    YouthUnemploymentInput,
    _validate_external_url,
    seco_get_dataset,
    seco_get_monthly_report_url,
    seco_get_open_positions,
    seco_get_unemployment_by_occupation,
    seco_get_unemployment_overview,
    seco_get_youth_unemployment,
    seco_list_cantons,
    seco_search_datasets,
)


def assert_rejects(build, error_type: str, field: str) -> None:
    """Die Konstruktion muss an DIESEM Feld und aus DIESEM Grund scheitern.

    `pytest.raises(ValidationError)` allein reicht hier nicht: ein Tippfehler im
    Feldnamen scheitert ebenfalls, nur als `extra_forbidden` — der Test bliebe
    gruen, ohne die Schranke noch zu pruefen.

    Der Feldname allein reicht auch nicht. Die Bounds-Paare unten pruefen je
    beide Enden derselben Schranke (`limit=25` / `limit=0`); auf den Feldnamen
    gepruefte Assertions waeren fuer beide Haelften identisch und wuerden ein
    vertauschtes `ge`/`le` nicht bemerken. Deshalb der Fehlertyp:
    `less_than_equal` vs. `greater_than_equal`.

    Verglichen wird auf der strukturierten Fehlerliste statt per `match=` auf
    dem Meldungstext — der ist bei Pydantic-Upgrades und in lokalisierten
    Validatoren beweglich, `type` und `loc` sind es nicht.
    """
    with pytest.raises(ValidationError) as excinfo:
        build()
    assert [(e["type"], e["loc"]) for e in excinfo.value.errors()] == [(error_type, (field,))]


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
        assert_rejects(lambda: DatasetSearchInput(query="a"), "string_too_short", "query")

    def test_dataset_search_limit_bounds(self):
        assert_rejects(
            lambda: DatasetSearchInput(query="test", limit=25),  # max is 20
            "less_than_equal",
            "limit",
        )
        assert_rejects(
            lambda: DatasetSearchInput(query="test", limit=0),  # min is 1
            "greater_than_equal",
            "limit",
        )

    def test_unemployment_valid_canton(self):
        inp = UnemploymentInput(canton="ZH")
        assert inp.canton == "ZH"

    def test_unemployment_canton_none(self):
        inp = UnemploymentInput()
        assert inp.canton is None

    def test_unemployment_year_bounds(self):
        assert_rejects(
            lambda: UnemploymentInput(year=1999),  # too early
            "greater_than_equal",
            "year",
        )
        assert_rejects(
            lambda: UnemploymentInput(year=2031),  # too late
            "less_than_equal",
            "year",
        )

    def test_monthly_report_valid(self):
        inp = MonthlyReportInput(year=2025, month=12, language="de")
        assert inp.year == 2025
        assert inp.month == 12
        assert inp.language == "de"

    def test_monthly_report_invalid_language(self):
        assert_rejects(
            lambda: MonthlyReportInput(year=2025, month=6, language="en"),  # only de/fr/it
            "string_pattern_mismatch",
            "language",
        )

    def test_monthly_report_month_bounds(self):
        # `year` traegt hier ebenfalls Bounds. Ein auf den Fehlertyp allein
        # gepruefter Test bliebe gruen, wenn `month=` versehentlich zu `year=`
        # wuerde — deshalb steht das Feld mit in der Erwartung.
        assert_rejects(lambda: MonthlyReportInput(year=2025, month=13), "less_than_equal", "month")
        assert_rejects(
            lambda: MonthlyReportInput(year=2025, month=0), "greater_than_equal", "month"
        )

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
        assert_rejects(
            lambda: OccupationInput(response_format="csv"),  # type: ignore[arg-type]
            "enum",
            "response_format",
        )

    def test_occupation_input_rejects_extra_fields(self):
        # Hier ist `extra_forbidden` der Zweck des Tests, nicht die Fehlerquelle,
        # die es zu vermeiden gilt — entsprechend explizit erwartet.
        assert_rejects(
            lambda: OccupationInput(canton="ZH"),  # type: ignore[call-arg]
            "extra_forbidden",
            "canton",
        )


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

        # Nicht mehr "SECO-Datensätze": die Suche läuft ohne Herausgeberfilter,
        # und die Treffer stammen vom BFS, von Kantonen und weiteren Stellen.
        assert "SECO-Datensätze" not in result
        assert "Herausgeber" in result
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

        assert "Keine Datensätze" in result
        # Eine leere Antwort heisst jetzt wirklich "es gibt dazu nichts" und
        # nicht "der Filter hat niemanden getroffen".
        assert "ganzen Bestand" in result

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
        # Das Werkzeug liefert keine Zahlen mehr, sondern eine benannte Absage:
        # es gibt portalweit keine maschinenlesbare Quelle für 15–24-Jährige.
        assert data["data_available"] is False
        assert "seasonal_pattern_qualitative" in data
        assert "amstat" in json.dumps(data), "die Absage nennt, wo die Zahlen stehen"


class TestUnemploymentOverview:
    """Tests for seco_get_unemployment_overview tool."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_overview_national(self):
        """Die Uebersicht liest jetzt die gepinnte Tabelle, nicht die Suche.

        Die echten Zahlen und die Form der Antwort pruefen die
        Aufzeichnungstests; hier geht es nur darum, dass der Weg ueber
        `package_show` auf die gepinnte Kennung fuehrt.
        """
        route = respx.get(url__startswith=f"{CKAN_BASE}/package_show").mock(
            return_value=httpx.Response(500)
        )
        with pytest.raises(Exception):  # noqa: B017 — 5xx ist ein Protokollfehler
            await seco_get_unemployment_overview(UnemploymentInput())
        assert sources.JAHRESREIHE.ckan_id in str(route.calls.last.request.url)

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
    @respx.mock
    async def test_overview_invalid_canton(self):
        respx.get(f"{CKAN_BASE}/package_search").mock(
            return_value=httpx.Response(200, json=MOCK_CKAN_SEARCH_RESPONSE)
        )
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


class TestSsrfValidator:
    """Tests for _validate_external_url (SEC-004). All async because the
    validator does DNS resolution on the event loop's executor."""

    @pytest.mark.asyncio
    async def test_https_public_host_is_allowed(self):
        # No exception means the URL passed validation.
        await _validate_external_url("https://opendata.swiss/api/3/action/package_search")

    @pytest.mark.asyncio
    async def test_http_scheme_is_rejected(self):
        with pytest.raises(UrlNotAllowedError, match="https"):
            await _validate_external_url("http://opendata.swiss/foo")

    @pytest.mark.asyncio
    async def test_file_scheme_is_rejected(self):
        with pytest.raises(UrlNotAllowedError):
            await _validate_external_url("file:///etc/passwd")

    @pytest.mark.asyncio
    async def test_missing_host_is_rejected(self):
        with pytest.raises(UrlNotAllowedError):
            await _validate_external_url("https:///just-a-path")

    @pytest.mark.asyncio
    async def test_loopback_literal_is_rejected(self):
        with pytest.raises(UrlNotAllowedError, match="non-public"):
            await _validate_external_url("https://127.0.0.1/foo")

    @pytest.mark.asyncio
    async def test_private_rfc1918_literal_is_rejected(self):
        with pytest.raises(UrlNotAllowedError, match="non-public"):
            await _validate_external_url("https://10.0.0.1/admin")

    @pytest.mark.asyncio
    async def test_link_local_metadata_endpoint_is_rejected(self):
        # AWS/GCP/Azure metadata service shared address.
        with pytest.raises(UrlNotAllowedError, match="non-public"):
            await _validate_external_url("https://169.254.169.254/latest/meta-data/")

    @pytest.mark.asyncio
    async def test_fetch_skips_internal_url(self):
        """Der Abruf oeffnet gegen eine abgelehnte URL keinen Socket.

        Frueher prueste das denselben Satz gegen `_fetch_text_cached`, das bei
        Ablehnung `None` lieferte. Der neue Weg wirft stattdessen — eine
        Policy-Ablehnung soll den Aufrufer erreichen und nicht als leeres
        Ergebnis aussehen.
        """
        with pytest.raises(UrlNotAllowedError):
            await _server_mod._fetch_bytes_with_retry("http://169.254.169.254/x.xlsx")


class TestBytesFetchRetry:
    """Retry-Verhalten von `_fetch_bytes_with_retry`.

    Die Vorgaengerin dieser Klasse prueft `_fetch_text_cached`, den Abrufweg
    des CSV-Zweigs. Der ist mit dem Umbau auf die gepinnte BFS-Tabelle
    entfallen; die Zusicherungen ueber das Retry-Verhalten gelten aber
    unveraendert weiter und stehen deshalb hier, gegen den neuen Weg.

    Ein Unterschied ist gewollt: der alte Pfad gab bei jedem Scheitern `None`
    zurueck, der neue wirft. Eine leere Antwort war beim CSV-Zweig noch
    vertretbar, weil daneben ein statischer Snapshot stand; jetzt ist der
    Abruf die einzige Quelle, und ein stiller `None` waere eine leere Reihe
    ohne Grund.
    """

    @pytest.fixture(autouse=True)
    def _fast_backoff(self, monkeypatch):
        """Wartezeit auf null und SSRF-Pruefung ueberbrueckt.

        Gepatcht wird der Modul-Alias `_sleep`, nicht `asyncio.sleep`: Letzteres
        ersetzt die Funktion auf dem geteilten Modulobjekt, also auch fuer httpx,
        respx und pytest-asyncio.

        Die SSRF-Pruefung loest DNS wirklich auf; gegen `example.test` schlaegt
        das fehl, bevor respx ueberhaupt gefragt wird. Hier geht es um das
        Retry-Verhalten, nicht um die Policy — die hat eigene Tests.
        """

        async def _allow(_url: str) -> None:
            return None

        async def _instant(_seconds):
            return None

        monkeypatch.setattr(_server_mod, "_sleep", _instant)
        monkeypatch.setattr(_server_mod, "_validate_external_url", _allow)

    @pytest.mark.asyncio
    @respx.mock
    async def test_transient_5xx_then_success(self):
        url = "https://example.test/data.xlsx"
        route = respx.get(url).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(500),
                httpx.Response(200, content=b"nutzlast"),
            ]
        )
        assert await _server_mod._fetch_bytes_with_retry(url) == b"nutzlast"
        assert route.call_count == 3

    @pytest.mark.asyncio
    @respx.mock
    async def test_gives_up_after_all_retries(self):
        url = "https://example.test/down.xlsx"
        route = respx.get(url).mock(return_value=httpx.Response(503))
        with pytest.raises(_server_mod.UpstreamUnreachableError):
            await _server_mod._fetch_bytes_with_retry(url)
        assert route.call_count == 4, "ein Versuch plus drei Retries"

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_is_retried(self):
        url = "https://example.test/limited.xlsx"
        route = respx.get(url).mock(return_value=httpx.Response(429))
        with pytest.raises(_server_mod.UpstreamUnreachableError):
            await _server_mod._fetch_bytes_with_retry(url)
        assert route.call_count == 4

    @pytest.mark.asyncio
    @respx.mock
    async def test_404_is_not_retried(self):
        """Ein 404 ist eine Antwort, kein Ausfall — und wird durchgereicht."""
        url = "https://example.test/missing.xlsx"
        route = respx.get(url).mock(return_value=httpx.Response(404))
        with pytest.raises(httpx.HTTPStatusError):
            await _server_mod._fetch_bytes_with_retry(url)
        assert route.call_count == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_redirect_is_not_retried(self):
        """follow_redirects=False: ein 302 ist endgueltig, nicht transient."""
        url = "https://example.test/moved.xlsx"
        route = respx.get(url).mock(
            return_value=httpx.Response(302, headers={"location": "https://elsewhere.test/x"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await _server_mod._fetch_bytes_with_retry(url)
        assert route.call_count == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_network_error_is_retried(self):
        url = "https://example.test/flaky.xlsx"
        route = respx.get(url).mock(side_effect=httpx.ConnectError("boom"))
        with pytest.raises(_server_mod.UpstreamUnreachableError):
            await _server_mod._fetch_bytes_with_retry(url)
        assert route.call_count == 4

    @pytest.mark.asyncio
    @respx.mock
    async def test_der_fehler_nennt_die_ursache(self):
        """`httpx.ConnectError` traegt ein leeres `str()` — der Typ muss dastehen."""
        url = "https://example.test/leer.xlsx"
        respx.get(url).mock(side_effect=httpx.ConnectError(""))
        with pytest.raises(_server_mod.UpstreamUnreachableError) as exc:
            await _server_mod._fetch_bytes_with_retry(url)
        assert "ConnectError" in str(exc.value)
        assert "kein weiterer Hinweis" in str(exc.value)

    @pytest.mark.asyncio
    async def test_rejected_url_is_validated_once(self, monkeypatch):
        """Eine von der SSRF-Policy abgelehnte URL wird nicht erneut aufgeloest.

        Ein zweiter Anlauf brauchte eine zweite DNS-Aufloesung fuer ein Ziel,
        das wir bereits verweigert haben.
        """
        calls = 0

        async def counting(url: str) -> None:
            nonlocal calls
            calls += 1
            raise _server_mod.UrlNotAllowedError("nope")

        monkeypatch.setattr(_server_mod, "_validate_external_url", counting)
        with pytest.raises(_server_mod.UrlNotAllowedError):
            await _server_mod._fetch_bytes_with_retry("https://169.254.169.254/x.xlsx")
        assert calls == 1
