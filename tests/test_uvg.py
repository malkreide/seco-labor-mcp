"""
Offline-Tests für die UVG-Erweiterung (Unfallstatistik UVG / SSUV).

Die Parser-Tests arbeiten auf Textfixturen, die den echten Extraktionen aus
``Ts26.pdf`` und ``WirtKl_BUV_43.pdf`` nachgebildet sind — inklusive der
Eigenheiten, die in der Live-Probe aufgefallen sind: Leerzeichen als
Tausendertrenner, Silbentrennung mitten in der Beschriftung, Sternchen für
statistische Signifikanz und fehlende Trendzellen.

Was diese Tests **nicht** können: eine falsche Grundannahme fangen. Ein Mock
bildet ab, was beim Schreiben erwartet wurde. Dafür gibt es die Live-Tests in
``test_live.py`` — insbesondere die Summenprobe gegen das gedruckte Total.
"""

import httpx
import pytest
import respx

from seco_labor_mcp import uvg
from seco_labor_mcp.server import (
    UvgBranchInput,
    UvgOverviewInput,
    UvgTrendInput,
    seco_get_uvg_overview,
    seco_get_uvg_trends,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Layout-Extraktion: Spalten durch grosse Whitespace-Läufe getrennt, Ziffern
# innerhalb einer Zahl durch kleine. Nachgebildet nach Ts26.pdf S. 27.
GAP = " " * 40

LAYOUT_PAGE = "\n".join(
    [
        "Tabelle 2.4",
        "Berufsunfallversicherung (BUV )",
        f"Wirtschaftszweig1{GAP}Anerkannte{GAP}Durchschnitt der Jahre 2020 – 2024",
        "in Mio. CHF",
        f"I Primärer Sek tor (Land- und Forstwir tschaf t){GAP}4 8  31{GAP}5{GAP}0{GAP}4{GAP}0{GAP}26,9",
        f"01          –         03 Landwir tschaf t{GAP}4 8  31{GAP}5{GAP}0{GAP}4{GAP}0{GAP}26,9",
        f"II Sekundärer Sektor (Gewerbe und Industrie){GAP}9 0  0 02{GAP}333{GAP}21{GAP}27{GAP}124{GAP}813,7",
        f"10          –         12 Herstellung von Nahrungsmitteln und Tabakerzeug-{GAP}6  31{GAP}11{GAP}1{GAP}1{GAP}0{GAP}31, 3",
        f"nissen{GAP}5",
        "19 – 20 Kokerei, Mineralölverarbeitung und Herstellung",
        f"von chemischen Erzeugnissen{GAP}883{GAP}3{GAP}1{GAP}1{GAP}1{GAP}7,  4",
        f"III Tertiärer Sektor (Handel und Dienstleistungen){GAP}16   6 5  3  4{GAP}234{GAP}8{GAP}33{GAP}26{GAP}876,6",
        f"Unbekannt{GAP}79{GAP}0{GAP}0{GAP}0{GAP}3{GAP}2,0",
        f"Total{GAP}261 4 4 6{GAP}573{GAP}29{GAP}64{GAP}153{GAP}1  719 ,   2",
    ]
)

# Textmodus derselben Seite: saubere Wörter, aber mehrdeutige Zahlen.
TEXT_PAGE = "\n".join(
    [
        "Tabelle 2.4",
        "Ergebnisse nach Wirtschaftszweig 1",
        "Berufsunfallversicherung (BUV)",
        "I Primärer Sektor (Land- und Forstwirtschaft, Fischerei) 4 831 5 0 4 0 26,9",
        "  01 – 03 Landwirtschaft, Forstwirtschaft und Fischerei 4 831 5 0 4 0 26,9",
        "II Sekundärer Sektor (Gewerbe und Industrie) 90 002 333 21 27 124 813,7",
        "  10 – 12 Herstellung von Nahrungsmitteln und Tabakerzeug -",
        "nissen 5 631 11 1 1 0 31,3",
        "  19 – 20 Kokerei, Mineralölverarbeitung und Herstellung",
        "von chemischen Erzeugnissen 883 3 1 1 1 7,4",
        "III Tertiärer Sektor (Handel und Dienstleistungen) 166 534 234 8 33 26 876,6",
        "Unbekannt 79 0 0 0 3 2,0",
        "Total 261 446 573 29 64 153 1 719,2",
        "UVG-Statistik 2026",
    ]
)

SERIES_PAGE = "\n".join(
    [
        "Zeitreihen zum Unfallgeschehen nach Branche (NOGA 2008), UVG",
        "UVG nach Branche (NOGA 2008) Version: 2.01.00 / 09.01.2026",
        "43 Vorbereitende Baustellenarbeiten und sonstiges Ausbaugewerbe 43 UVG",
        "Erfolgskennzahlen  [1] 2015 2016 2017 2018 2019 2020 2021 2022 2023 2024 Mittel Trend Mittel Trend",
        "Fallrisiko 171 170 162* 162 165* 152* *155 *153 153 *145 159 -13.7% 62 -7.9%",
        "Schwere Unfälle UE / 100'000 VB 956 1'057* 1'023 1'038 *1'103 1'112 1'132 1'162 1'200 1'181 1'096 22.2% 320 17.0%",
        # Quelle lässt den Branchen-Trend weg, wenn er nicht berechenbar ist.
        "Berufskrankheiten BK / 100'000 VB 81 314 288 336 285 3'036 1'981 1'834 231 155 854 151 115.4%",
    ]
)

KEY_FIGURES_HTML = """<html><body>
<table><tr><td>Schlüsselzahlen</td><td>2021</td><td>2022</td><td>2023</td><td>2024</td><td>2025</td></tr></table>
<table>
  <tr><td colspan="7"><b>Fälle</b></td></tr>
  <tr><td>Neu registrierte Fälle total</td><td>&nbsp;</td>
      <td>831 511</td><td>910 904</td><td>908 313</td><td>914 741</td><td>936 965</td></tr>
  <tr><td>BUV</td><td>&nbsp;</td>
      <td>276 886</td><td>293 132</td><td>286 154</td><td>280 323</td><td>281 162</td></tr>
  <tr><td>NBUV</td><td>&nbsp;</td>
      <td>536 208</td><td>600 715</td><td>606 945</td><td>617 528</td><td>636 323</td></tr>
  <tr><td>Anerkannte Berufskrankheiten</td><td>&nbsp;</td>
      <td>14 251</td><td>11 867</td><td>3 184</td><td>2 979</td><td>&nbsp;</td></tr>
  <tr><td colspan="7"><b>Kosten</b></td></tr>
  <tr><td>Laufende Kosten total</td><td>Mio. CHF</td>
      <td>4 969,1</td><td>6 869,3</td><td>5 507,6</td><td>5 603,5</td><td>&nbsp;</td></tr>
</table></body></html>"""


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch):
    """Backoff im Test auf null setzen — geprüft wird die Anzahl Versuche,
    nicht die Wartezeit."""
    monkeypatch.setattr(uvg, "UVG_BACKOFF_SECONDS", (0.0, 0.0, 0.0))
    uvg.uvg_cache_clear()
    yield
    uvg.uvg_cache_clear()


# ---------------------------------------------------------------------------
# Zahlen-Parsing
# ---------------------------------------------------------------------------


class TestParseNumber:
    @pytest.mark.parametrize(
        ("token", "expected"),
        [
            ("1 097 154", 1097154),  # Leerzeichen als Tausendertrenner
            ("261 4 4 6", 261446),  # Layout-Modus streut Ziffern
            ("1'057", 1057),  # Apostroph in den Branchen-PDF
            ("137,5", 137.5),  # Komma-Dezimaltrenner (Jahresausgabe)
            ("4.25", 4.25),  # Punkt-Dezimaltrenner (Branchen-PDF)
            ("0,8 %", 0.8),
            ("-13.7%", -13.7),
            ("0", 0),
        ],
    )
    def test_values(self, token, expected):
        assert uvg.parse_number(token)[0] == expected

    @pytest.mark.parametrize("token", ["162*", "*145", "1'057*"])
    def test_asterisk_marks_significance(self, token):
        value, significant = uvg.parse_number(token)
        assert value is not None
        assert significant is True, "Der Stern ist Information, kein Rauschen"

    def test_plain_value_not_significant(self):
        assert uvg.parse_number("162") == (162, False)

    @pytest.mark.parametrize("token", ["", "   ", "–", "n/a"])
    def test_unparsable(self, token):
        assert uvg.parse_number(token)[0] is None


class TestCodeMatching:
    def test_expands_range(self):
        assert uvg.expand_code("41 – 42") == {41, 42}

    def test_expands_mixed_list(self):
        assert uvg.expand_code("77, 79 – 82") == {77, 79, 80, 81, 82}

    def test_query_inside_range_matches(self):
        """Wer nach 42 fragt, meint die Zeile '41 – 42'."""
        assert uvg.code_matches("42", "41 – 42") is True

    def test_exact_match(self):
        assert uvg.code_matches("43", "43") is True

    def test_no_false_positive(self):
        assert uvg.code_matches("44", "41 – 42") is False


# ---------------------------------------------------------------------------
# Tabellen-Parser
# ---------------------------------------------------------------------------


class TestBranchTable:
    def _parse(self):
        return uvg.parse_branch_table([LAYOUT_PAGE], [TEXT_PAGE], "2.4_BUV")

    def test_parses(self):
        assert self._parse()["parsed"] is True

    def test_labels_come_from_text_mode(self):
        """Der Layout-Modus zerlegt Wörter ('Sek tor'); angezeigt wird die
        saubere Fassung aus dem Textmodus."""
        rows = self._parse()["rows"]
        sector = next(r for r in rows if r["row_type"] == "sector" and r["code"] == "I")
        assert "Sek tor" not in sector["label"]
        assert sector["label"].startswith("Primärer Sektor")

    def test_hyphenated_label_is_rejoined(self):
        rows = self._parse()["rows"]
        row = next(r for r in rows if r.get("code") == "10 – 12")
        assert "Tabakerzeugnissen" in row["label"]

    def test_wrapped_row_keeps_leading_digits(self):
        """Der Umbruch trennt '5' von '631'. Wer die Fortsetzungszeile
        ignoriert, verliert eine Zehnerpotenz."""
        rows = self._parse()["rows"]
        row = next(r for r in rows if r.get("code") == "10 – 12")
        assert row["accepted_cases"] == 5631

    def test_forward_wrapped_label(self):
        rows = self._parse()["rows"]
        row = next(r for r in rows if r.get("code") == "19 – 20")
        assert "chemischen Erzeugnissen" in row["label"]
        assert row["accepted_cases"] == 883

    def test_header_fragment_does_not_swallow_sector_row(self):
        """Regression: 'in Mio. CHF' wurde als Beschriftungsanfang der
        Sektorzeile gelesen, worauf deren Wert aus der Summe fiel."""
        rows = self._parse()["rows"]
        assert any(r["row_type"] == "sector" and r["code"] == "I" for r in rows)

    def test_unknown_row_is_kept(self):
        rows = self._parse()["rows"]
        assert any(r["row_type"] == "unknown" for r in rows)

    def test_totals_check_matches(self):
        """Sektorzeilen plus 'Unbekannt' müssen das gedruckte Total ergeben."""
        check = self._parse()["totals_check"]
        assert check["available"] is True
        assert check["match"] is True, f"Summenprobe fehlgeschlagen: {check}"

    def test_ambiguous_number_resolved_by_layout(self):
        """Im Textmodus ist '166 534 234' als 166534234 genauso lesbar wie als
        166 534 | 234 — greedy raten trifft die falsche Lesart. Die
        Layout-Spalten lösen das eindeutig auf."""
        rows = self._parse()["rows"]
        tertiary = next(r for r in rows if r["row_type"] == "sector" and r["code"] == "III")
        assert tertiary["accepted_cases"] == 166534
        assert tertiary["disability_pensions_accident"] == 234


class TestBranchSeries:
    def _parse(self):
        return uvg.parse_branch_series([SERIES_PAGE])

    def test_parses_metadata(self):
        result = self._parse()
        assert result["parsed"] is True
        assert result["version"] == "2.01.00"
        assert result["published"] == "2026-01-09"

    def test_years_ignore_noga_and_version_years(self):
        """'NOGA 2008' und das Versionsjahr 2026 sind keine Datenspalten."""
        assert self._parse()["years"] == list(range(2015, 2025))

    def test_significance_preserved(self):
        series = self._parse()["indicators"][0]["series"]
        by_year = {p["year"]: p for p in series}
        assert by_year[2017]["significant"] is True
        assert by_year[2018]["significant"] is False

    def test_missing_trend_does_not_drop_indicator(self):
        """Fehlt die Trendzelle, muss die Kennzahl trotzdem erscheinen —
        sonst verschwindet sie kommentarlos aus dem Ergebnis."""
        indicators = self._parse()["indicators"]
        names = [i["indicator"] for i in indicators]
        assert any("Berufskrankheiten" in n for n in names)
        row = next(i for i in indicators if "Berufskrankheiten" in i["indicator"])
        assert row["mean"] == 854
        assert row["trend_pct"] is None
        assert row["reference_trend_pct"] == 115.4


class TestKeyFigures:
    def test_parses_years_and_rows(self):
        result = uvg.parse_key_figures(KEY_FIGURES_HTML)
        assert result["parsed"] is True
        assert result["years"] == [2021, 2022, 2023, 2024, 2025]

    def test_values_and_sections(self):
        rows = uvg.parse_key_figures(KEY_FIGURES_HTML)["rows"]
        buv = next(r for r in rows if r["label"] == "BUV")
        assert buv["section"] == "Fälle"
        assert {v["year"]: v["value"] for v in buv["values"]}[2024] == 280323

    def test_missing_cells_are_omitted_not_zeroed(self):
        """Die jüngste Spalte ist teils leer. Eine leere Zelle ist keine Null."""
        rows = uvg.parse_key_figures(KEY_FIGURES_HTML)["rows"]
        row = next(r for r in rows if r["label"] == "Anerkannte Berufskrankheiten")
        assert [v["year"] for v in row["values"]] == [2021, 2022, 2023, 2024]


# ---------------------------------------------------------------------------
# HTTP-Verhalten
# ---------------------------------------------------------------------------


class TestFetchResilience:
    @respx.mock
    @pytest.mark.asyncio
    async def test_happy_path(self):
        route = respx.get(uvg.UVG_KEY_FIGURES_URL).mock(
            return_value=httpx.Response(200, content=b"ok", headers={"last-modified": "X"})
        )
        payload, last_modified, provenance = await uvg._fetch_bytes(uvg.UVG_KEY_FIGURES_URL)
        assert (payload, last_modified, provenance) == (b"ok", "X", "live")
        assert route.call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_retries_then_succeeds(self):
        route = respx.get(uvg.UVG_KEY_FIGURES_URL).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(503),
                httpx.Response(200, content=b"spaet"),
            ]
        )
        payload, _, _ = await uvg._fetch_bytes(uvg.UVG_KEY_FIGURES_URL)
        assert payload == b"spaet"
        assert route.call_count == 3

    @respx.mock
    @pytest.mark.asyncio
    async def test_gives_up_after_all_retries(self):
        route = respx.get(uvg.UVG_KEY_FIGURES_URL).mock(return_value=httpx.Response(503))
        with pytest.raises(uvg.UvgSourceUnavailableError):
            await uvg._fetch_bytes(uvg.UVG_KEY_FIGURES_URL)
        assert route.call_count == 4, "ein Versuch plus drei Retries"

    @respx.mock
    @pytest.mark.asyncio
    async def test_4xx_is_not_retried(self):
        """403 ist eine Antwort, kein Ausfall — Wiederholen bringt nichts."""
        route = respx.get(uvg.UVG_KEY_FIGURES_URL).mock(return_value=httpx.Response(403))
        with pytest.raises(uvg.UvgSourceUnavailableError):
            await uvg._fetch_bytes(uvg.UVG_KEY_FIGURES_URL)
        assert route.call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_429_is_retried(self):
        route = respx.get(uvg.UVG_KEY_FIGURES_URL).mock(return_value=httpx.Response(429))
        with pytest.raises(uvg.UvgSourceUnavailableError):
            await uvg._fetch_bytes(uvg.UVG_KEY_FIGURES_URL)
        assert route.call_count == 4

    @respx.mock
    @pytest.mark.asyncio
    async def test_network_error_is_retried(self):
        route = respx.get(uvg.UVG_KEY_FIGURES_URL).mock(side_effect=httpx.ConnectError("down"))
        with pytest.raises(uvg.UvgSourceUnavailableError):
            await uvg._fetch_bytes(uvg.UVG_KEY_FIGURES_URL)
        assert route.call_count == 4

    @respx.mock
    @pytest.mark.asyncio
    async def test_stale_cache_beats_nothing(self):
        """Nach einem erfolgreichen Abruf darf ein späterer Ausfall auf den
        Cache zurückfallen, statt gar nichts zu liefern."""
        url = uvg.UVG_KEY_FIGURES_URL
        respx.get(url).mock(return_value=httpx.Response(200, content=b"frisch"))
        await uvg._fetch_bytes(url)
        uvg._UVG_CACHE[url] = (
            uvg._UVG_CACHE[url][0] - uvg.UVG_CACHE_TTL * 2,
            b"alt",
            None,
        )
        respx.get(url).mock(return_value=httpx.Response(503))
        payload, _, provenance = await uvg._fetch_bytes(url)
        assert (payload, provenance) == (b"alt", "cached")


# ---------------------------------------------------------------------------
# Tool-Ebene
# ---------------------------------------------------------------------------


class TestOverviewTool:
    @respx.mock
    @pytest.mark.asyncio
    async def test_envelope_fields(self):
        respx.get(uvg.UVG_KEY_FIGURES_URL).mock(
            return_value=httpx.Response(200, content=KEY_FIGURES_HTML.encode("utf-8"))
        )
        envelope = await uvg.uvg_overview_impl()
        for field in ("source", "provenance", "retrieved_at", "source_freshness", "degraded"):
            assert field in envelope
        assert envelope["degraded"] is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_attribution_carries_licence_restriction(self):
        """Die Nicht-kommerziell-Klausel gehört in jede Response — das README
        wird dem Modell nicht weitergereicht."""
        respx.get(uvg.UVG_KEY_FIGURES_URL).mock(
            return_value=httpx.Response(200, content=KEY_FIGURES_HTML.encode("utf-8"))
        )
        envelope = await uvg.uvg_overview_impl()
        assert "kommerzielle Nutzung" in envelope["source"]
        assert "KSUV" in envelope["source"] and "SSUV" in envelope["source"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_non_occupational_excluded_by_default(self):
        respx.get(uvg.UVG_KEY_FIGURES_URL).mock(
            return_value=httpx.Response(200, content=KEY_FIGURES_HTML.encode("utf-8"))
        )
        labels = [r["label"] for r in (await uvg.uvg_overview_impl())["rows"]]
        assert "BUV" in labels
        assert "NBUV" not in labels

    @respx.mock
    @pytest.mark.asyncio
    async def test_non_occupational_opt_in(self):
        respx.get(uvg.UVG_KEY_FIGURES_URL).mock(
            return_value=httpx.Response(200, content=KEY_FIGURES_HTML.encode("utf-8"))
        )
        labels = [r["label"] for r in (await uvg.uvg_overview_impl(include_nbuv=True))["rows"]]
        assert "NBUV" in labels

    @respx.mock
    @pytest.mark.asyncio
    async def test_degraded_envelope_on_outage(self):
        respx.get(uvg.UVG_KEY_FIGURES_URL).mock(return_value=httpx.Response(503))
        envelope = await uvg.uvg_overview_impl()
        assert envelope["degraded"] is True
        assert envelope["provenance"] == "unavailable"
        assert "erneut versuchen" in envelope["note"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_markdown_wrapper_shows_outage(self):
        respx.get(uvg.UVG_KEY_FIGURES_URL).mock(return_value=httpx.Response(503))
        text = await seco_get_uvg_overview(UvgOverviewInput())
        assert "nicht erreichbar" in text


class TestTrendsTool:
    @pytest.mark.asyncio
    async def test_invalid_noga_returns_hint_not_silence(self):
        envelope = await uvg.uvg_trends_impl(noga="Baugewerbe")
        assert envelope["returned"] == 0
        assert "zweistellige" in envelope["hint"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_unknown_branch_gets_actionable_hint(self):
        """Ein leeres Resultat muss den nächsten Schritt nennen, nicht eine
        Erklärung anbieten, die das Modell als Freibrief liest."""
        url = uvg.UVG_BRANCH_PDF_URL.format(scheme="BUV", noga="04")
        respx.get(url).mock(return_value=httpx.Response(404))
        envelope = await uvg.uvg_trends_impl(noga="04")
        assert envelope["returned"] == 0
        assert "seco_get_uvg_by_branch" in envelope["hint"]
        assert "Erst danach auf Abwesenheit schliessen" in envelope["hint"]


class TestToolContracts:
    def test_branch_input_rejects_unknown_table(self):
        with pytest.raises(Exception):
            UvgBranchInput(table="9.9")

    def test_branch_input_omitting_noga_is_allowed(self):
        assert UvgBranchInput().noga is None

    def test_trend_input_requires_noga(self):
        with pytest.raises(Exception):
            UvgTrendInput()

    def test_overview_years_bounded(self):
        with pytest.raises(Exception):
            UvgOverviewInput(years=9)

    @pytest.mark.parametrize("tool", [seco_get_uvg_overview, seco_get_uvg_trends])
    def test_docstring_does_not_excuse_empty_results(self, tool):
        """Keine Formulierung darf dem Modell eine Erklärung für eine
        Leermenge mitgeben, statt eines nächsten Schritts."""
        doc = (tool.__doc__ or "").lower()
        for phrase in ["usually means", "may simply mean", "bedeutet meist", "heisst meist"]:
            assert phrase not in doc
