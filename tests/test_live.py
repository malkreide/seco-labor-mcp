"""
Live API tests for seco-labor-mcp.

These require internet access to opendata.swiss and SECO endpoints.
By default they are skipped (see conftest.py); run them explicitly with:

    pytest tests/test_live.py --run-live -v

CI excludes this file via `pytest -m "not live"`.
"""

import pytest

from seco_labor_mcp import kantone, sources, uvg
from seco_labor_mcp.server import (
    CANTON_CODES,
    DatasetSearchInput,
    YouthUnemploymentInput,
    _bfs_jahresreihe,
    _ckan_get_dataset,
    _kantonsreihe,
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
        assert "Keine Datensätze" not in result, (
            "die Suche liefert portalweit nichts mehr — das war das Symptom des "
            "Organisationsfilters und darf nicht zurückkommen"
        )

    @pytest.mark.asyncio
    async def test_die_gepinnte_kennung_existiert_noch(self):
        """Der Mechanismus, der den letzten Ausfall gemeldet hätte.

        Der frühere Organisationsfilter war ein Namensabgleich: verschwand die
        Organisation, wurde nicht ein Test rot, sondern eine Antwort leer.
        `sources.py` pinnt stattdessen eine Kennung, und dieser Test hält sie
        gegen die echte Quelle. Verschwindet der Datensatz, ist das hier ein
        roter Test und kein stiller Ausfall.
        """
        for datensatz in sources.GEPINNTE_DATENSAETZE:
            paket = await _ckan_get_dataset(datensatz.ckan_id)
            assert paket.get("success") is True, (
                f"{datensatz.slug}: CKAN meldet keinen Erfolg — Kennung geprüft?"
            )
            ds = paket["result"]
            assert ds["id"] == datensatz.ckan_id
            formate = {(r.get("format") or "").upper() for r in ds.get("resources", [])}
            assert formate & {"XLS", "XLSX"}, (
                f"{datensatz.slug} führt keine Tabellenressource mehr: {sorted(formate)}"
            )

    @pytest.mark.asyncio
    async def test_die_gepinnten_kantone_existieren_noch(self):
        """Vier Kantone, vier Kennungen — jede gegen die echte Quelle.

        Derselbe Mechanismus wie fuer die nationale Reihe: verschwindet ein
        kantonaler Datensatz oder verliert er seine CSV-Ressource, ist das hier
        ein roter Test und nicht eine Antwort, die still auf die Absage
        zurueckfaellt.
        """
        for kuerzel, reihe in sorted(kantone.KANTONE.items()):
            paket = await _ckan_get_dataset(reihe.ckan_id)
            assert paket.get("success") is True, f"{kuerzel}: CKAN meldet keinen Erfolg"
            ds = paket["result"]
            assert ds["id"] == reihe.ckan_id
            formate = {(r.get("format") or "").upper() for r in ds.get("resources", [])}
            assert "CSV" in formate, f"{kuerzel} fuehrt keine CSV mehr: {sorted(formate)}"

    @pytest.mark.asyncio
    async def test_jeder_kantonsadapter_liest_die_echte_antwort(self):
        """Die Aufzeichnung belegt die Form von einem Tag; nur live faellt ein Wechsel auf.

        Ein Kanton, der eine Spalte umbenennt, laesst hier
        `KantonsReiheNichtLesbarError` fliegen — die Fehlermeldung nennt die
        vorhandenen Spalten, was das Nachziehen zu einer Minute Arbeit macht.
        """
        for kuerzel in sorted(kantone.KANTONE):
            daten = await _kantonsreihe(kuerzel)
            assert daten["kanton"] == kuerzel
            inhalt = next(v for k, v in daten.items() if k.startswith("nach_"))
            assert inhalt, f"{kuerzel}: keine Datenpunkte"

    @pytest.mark.asyncio
    async def test_die_jahresreihe_stimmt_noch_mit_der_quelle_ueberein(self):
        """Beschriftungen, Jahre und der Abstand der Reihen — in einem Abruf.

        Bewusst ein Test und nicht drei: die Mappe liegt hinter einem Host, der
        die TLS-Verhandlung sporadisch abbricht (beim Aufzeichnen zweimal in
        Folge, einmal auch im Live-Lauf). Drei Tests holten dieselben 17 kB
        dreimal und verdreifachten damit die Angriffsfläche für einen Aussetzer,
        ohne eine einzige Zusicherung mehr zu tragen.

        Die aufgezeichnete Fixture belegt die Form von einem Tag; nur der
        Live-Lauf merkt, wenn die Quelle sie danach ändert.
        """
        daten = await _bfs_jahresreihe()

        # 1. Die Beschriftungen stehen wörtlich, nicht über Zeilenpositionen.
        assert set(daten["series"]) == set(sources.REIHEN)
        for schluessel, praefix in sources.REIHEN.items():
            assert daten["labels"][schluessel].startswith(praefix)
            assert daten["series"][schluessel], f"Reihe {schluessel} ist leer"

        # 2. Die Reihe wächst weiter.
        jahre = daten["years"]
        assert jahre[-1] >= 2024, f"jüngstes Jahr {jahre[-1]} — Reihe eingefroren?"

        # 3. Die Verwechslung, die dieser Server nicht machen darf: die
        #    ILO-Erwerbslosigkeit liegt deutlich über den registrierten
        #    Arbeitslosen, und die Stellensuchenden über beiden.
        registriert = daten["series"]["registrierte_arbeitslose"]
        ilo = daten["series"]["erwerbslose_ilo"]
        suchende = daten["series"]["registrierte_stellensuchende"]
        gemeinsam = sorted(set(registriert) & set(ilo) & set(suchende))
        assert max(ilo[j] / registriert[j] for j in gemeinsam if registriert[j]) > 1.3
        assert all(suchende[j] > registriert[j] for j in gemeinsam)

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
