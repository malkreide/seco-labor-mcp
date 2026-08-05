"""
Live API tests for seco-labor-mcp.

These require internet access to opendata.swiss and SECO endpoints.
By default they are skipped (see conftest.py); run them explicitly with:

    pytest tests/test_live.py --run-live -v

CI excludes this file via `pytest -m "not live"`.
"""

import pytest

from seco_labor_mcp import uvg
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


@pytest.mark.live
class TestLiveUvg:
    """Unfallstatistik UVG (SSUV) gegen die echte Quelle.

    Diese Klasse trägt die einzige Testart, die eine falsche Grundannahme
    fangen kann. Die Offline-Tests in `test_uvg.py` prüfen den Parser gegen
    Fixturen — also gegen genau das, was beim Schreiben erwartet wurde. Wenn
    die Quelle ihr Layout ändert, sind die Fixturen weiter grün und trotzdem
    falsch. Nur die Summenprobe unten merkt das.
    """

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        uvg.uvg_cache_clear()
        yield
        uvg.uvg_cache_clear()

    @pytest.mark.asyncio
    async def test_overview_live(self):
        envelope = await uvg.uvg_overview_impl()
        assert envelope["degraded"] is False, envelope.get("note")
        labels = [row["label"] for row in envelope["rows"]]
        assert "BUV" in labels
        assert any("Berufskrankheiten" in label for label in labels)

    @pytest.mark.asyncio
    async def test_attribution_names_the_real_publisher(self):
        """Herausgeber ist KSUV/SSUV c/o Suva, nicht das SECO. Das Präfix der
        Tools adressiert diesen Server, die Quellenangabe die Quelle."""
        envelope = await uvg.uvg_overview_impl()
        assert "KSUV" in envelope["source"]
        assert "kommerzielle Nutzung" in envelope["source"]

    @pytest.mark.parametrize("table", ["1.2", "2.4_BUV", "2.4_NBUV"])
    @pytest.mark.asyncio
    async def test_totals_canary(self, table):
        """Canary: Die geparsten Zeilen müssen sich auf das in derselben
        Publikation gedruckte Total addieren.

        Die Toleranz ist Absicht. Die Quelle rundet selbst — in der Ausgabe
        2025 ergeben die gedruckten Sektorzeilen der Tabelle 1.2 zusammen
        4 469 213 bei einem gedruckten Total von 4 469 212. Geprüft wird
        deshalb nicht auf exakte Gleichheit, sondern auf «kein Kollaps»: ein
        gebrochenes Layout verfehlt das Total um Grössenordnungen, nicht um 1.
        """
        envelope = await uvg.uvg_by_branch_impl(table=table)
        assert envelope["degraded"] is False, envelope.get("note")
        check = envelope["totals_check"]
        assert check["available"] is True, "Total-Zeile nicht mehr auffindbar"
        assert check["within_tolerance"] is True, (
            f"Summenprobe {table}: Zeilen {check['sum_rows']} vs. gedrucktes Total "
            f"{check['printed_total']} (Delta {check['delta']}) — Layout gebrochen?"
        )

    @pytest.mark.asyncio
    async def test_branch_grid_is_complete(self):
        """Ohne `noga` muss das vollständige Raster kommen: Sektorzeilen,
        Branchenzeilen und die Kategorie «Unbekannt». Untergrenzen grosszügig
        unter dem Ist-Stand (53 Zeilen), damit Bestandspflege den Test nicht
        rot färbt, ein Einbruch aber schon."""
        envelope = await uvg.uvg_by_branch_impl()
        rows = envelope["rows"]
        assert len(rows) >= 40, f"nur {len(rows)} Zeilen — Raster geschrumpft?"
        types = {row["row_type"] for row in rows}
        assert {"sector", "branch", "unknown"} <= types, f"fehlende Zeilentypen: {types}"

    @pytest.mark.asyncio
    async def test_range_code_is_findable(self):
        """Die Publikation fasst 41 und 42 zu einer Zeile zusammen; eine
        Abfrage nach 42 muss sie trotzdem finden."""
        envelope = await uvg.uvg_by_branch_impl(noga="42")
        assert envelope["returned"] >= 1
        assert "hint" not in envelope

    @pytest.mark.asyncio
    async def test_freshness_comes_from_the_file(self):
        """Die Indexseite branchen_d.htm nennt ein veraltetes Datum. Der
        ausgewiesene Stand muss aus dem PDF stammen, nicht aus dem HTML."""
        envelope = await uvg.uvg_trends_impl(noga="43")
        freshness = envelope["source_freshness"]
        assert freshness["version"], "Versionsstring fehlt"
        assert freshness["published"] >= "2024-01-01", freshness

    @pytest.mark.asyncio
    async def test_trends_indicator_floor(self):
        """Recall-Untergrenze: Die Quelle führt zwölf Kennzahlen je Branche.
        Fällt das auf wenige, hat der Parser Zeilen verloren."""
        for noga in ("43", "86"):
            envelope = await uvg.uvg_trends_impl(noga=noga)
            assert envelope["degraded"] is False, envelope.get("note")
            assert envelope["returned"] >= 10, (
                f"NOGA {noga}: nur {envelope['returned']} Kennzahlen "
                f"(übersprungen: {envelope.get('skipped_rows')})"
            )

    @pytest.mark.asyncio
    async def test_significance_flag_is_present(self):
        """Der Stern der Quelle muss als Flag ankommen und nicht verloren
        gehen — sonst liest sich jede Veränderung als bedeutsam."""
        envelope = await uvg.uvg_trends_impl(noga="43")
        points = [p for ind in envelope["indicators"] for p in ind["series"]]
        assert any(p["significant"] for p in points), "kein einziger Signifikanz-Marker"

    @pytest.mark.asyncio
    async def test_unknown_branch_returns_hint(self):
        """Leermenge muss den nächsten Schritt nennen, nicht bloss leer sein."""
        envelope = await uvg.uvg_trends_impl(noga="04")
        assert envelope["returned"] == 0
        assert "hint" in envelope
