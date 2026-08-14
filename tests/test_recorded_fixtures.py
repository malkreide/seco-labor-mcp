"""Jeder externe Endpunkt, gefahren aus einer aufgezeichneten Antwort.

Die uebrige Suite arbeitet auf nachgebildeten Fixturen — `test_uvg.py` sagt das
in seinem eigenen Docstring: «Was diese Tests nicht koennen: eine falsche
Grundannahme fangen. Ein Mock bildet ab, was beim Schreiben erwartet wurde.»
Genau diese Luecke schliessen die Dateien hier: sie sind nicht nachgebildet,
sondern von der Quelle geholt, mit Datum.

Was handgeschrieben bleibt, bleibt es zu Recht: Timeouts, 5xx, ein kaputtes PDF.
Die lassen sich nicht auf Zuruf aufzeichnen.

Herkunft, Datum, Auswahlregel und SHA-256 je Datei stehen in
`tests/fixtures/PROVENANCE.md`; neu aufzeichnen mit
`python scripts/record_fixtures.py`.
"""

from __future__ import annotations

import datetime as dt
import re

import httpx
import pytest
import respx
from fixture_data import fixture_bytes, fixture_json, fixture_text, provenance, recorded_names

from seco_labor_mcp import server as _server_mod
from seco_labor_mcp import uvg
from seco_labor_mcp.server import (
    CKAN_BASE,
    SECO_ORG,
    DatasetDetailsInput,
    DatasetSearchInput,
    _try_live_csv,
    seco_get_dataset,
    seco_search_datasets,
)

# Jeder externe Endpunkt dieses Servers und die Fixture dazu. Ein Endpunkt ohne
# Aufzeichnung faellt in `test_jeder_endpunkt_hat_eine_aufzeichnung`.
ENDPUNKTE = {
    "ckan/package_search": "ckan_package_search.json",
    "ckan/package_show": "ckan_package_show.json",
    "die CSV-Ressource eines Datensatzes": "ckan_ressource.csv",
    "unfallstatistik/schluesselzahlen_d.htm": "uvg_schluesselzahlen.html",
    "unfallstatistik/publikationen_d.htm": "uvg_publikationen.html",
    "unfallstatistik/Ts{yy}.pdf": "uvg_jahresbericht_ts26.pdf",
    "unfallstatistik/WirtKl_{scheme}_{noga}.pdf": "uvg_branche_buv_41.pdf",
}


# --------------------------------------------------------------------------
# Herkunft
# --------------------------------------------------------------------------


def test_provenance_nennt_ein_brauchbares_aufnahmedatum():
    """Eine Aufzeichnung ohne Datum ist eine undatierte Behauptung ueber die Quelle."""
    match = re.search(r"Aufgezeichnet am \*\*(\d{4}-\d{2}-\d{2})\*\*", provenance())
    assert match, "PROVENANCE.md nennt kein Aufnahmedatum im erwarteten Format"
    when = dt.date.fromisoformat(match.group(1))
    assert when <= dt.datetime.now(dt.UTC).date(), "Aufnahmedatum liegt in der Zukunft"


def test_jede_fixture_steht_in_der_provenance():
    """Sonst waechst der Ordner und der Nachweis bleibt zurueck."""
    text = provenance()
    fehlend = [n for n in recorded_names() if f"## `{n}`" not in text]
    assert not fehlend, f"ohne Eintrag in PROVENANCE.md: {fehlend}"


def test_jeder_endpunkt_hat_eine_aufzeichnung():
    """Bewacht die Regel selbst: eine aufgezeichnete Antwort je externem Endpunkt."""
    fehlend = sorted(set(ENDPUNKTE.values()) - set(recorded_names()))
    assert not fehlend, f"Endpunkte ohne Aufzeichnung: {fehlend}"


@pytest.mark.parametrize("name", sorted(ENDPUNKTE.values()))
def test_jede_aufzeichnung_ist_nicht_leer(name):
    """Eine leere Aufzeichnung sieht aus wie eine gueltige und prueft nichts."""
    assert fixture_bytes(name), f"{name} ist leer — neu aufzeichnen"


# --------------------------------------------------------------------------
# CKAN — und der Befund, den nur eine Aufzeichnung datieren kann
# --------------------------------------------------------------------------


def test_der_filter_trifft_niemanden():
    """Der gepinnte Organisationsfilter schliesst zurzeit alles aus.

    Beide Aufzeichnungen stammen aus derselben Minute und derselben Suche; der
    einzige Unterschied ist `fq=organization:…`. Mit Filter null Treffer, ohne
    Filter mehrere tausend. Damit ist der Filter die Ursache und nicht die
    Suche, nicht das Netz und nicht die Quelle.

    Faellt dieser Test, weil die Organisation zurueck ist, ist das eine gute
    Nachricht — dann gehoert die Aufzeichnung erneuert und der Befund aus
    PROVENANCE.md gestrichen.
    """
    mit = fixture_json("ckan_package_search.json")
    ohne = fixture_json("ckan_package_search_ohne_organisation.json")
    assert mit["success"] is True, "die Quelle meldet Erfolg, nicht einen Fehler"
    assert mit["result"]["count"] == 0, (
        "der Organisationsfilter liefert wieder Treffer — Aufzeichnung erneuern "
        "und den Befund in PROVENANCE.md streichen"
    )
    assert ohne["result"]["count"] > 0, "ohne Filter antwortet derselbe Endpunkt normal"
    assert SECO_ORG in provenance(), "der Befund nennt die gepinnte Organisation"


@respx.mock
async def test_die_datensatzsuche_findet_deshalb_nichts():
    """Die Wirkung des Befunds, am echten Tool statt an der Vermutung."""
    respx.get(url__startswith=f"{CKAN_BASE}/package_search").mock(
        return_value=httpx.Response(200, json=fixture_json("ckan_package_search.json"))
    )
    antwort = await seco_search_datasets(DatasetSearchInput(query="arbeitslose kantone"))
    assert "Keine SECO-Datensätze" in antwort, (
        "solange der Filter niemanden trifft, ist die leere Antwort das ehrliche "
        "Ergebnis — kein Grund, etwas zu erfinden"
    )


@respx.mock
async def test_datensatz_details_aus_der_aufzeichnung():
    """Der Befund, den diese Aufzeichnung als Absturz aufgedeckt hat.

    CKAN schickt `last_modified` mit — aber als `null`. Gemessen am 2026-08-14
    in **165 von 165** Ressourcen aus 38 Datensaetzen. `r.get("last_modified",
    "")` greift bei einem vorhandenen Schluessel nicht zum Vorgabewert, und das
    anschliessende `[:10]` lief auf `None`: `TypeError`, fuer jeden Datensatz
    mit Ressourcen. Der handgeschriebene Stub setzte dort einen String.

    Der Test faehrt das Tool an der echten Antwort und verlangt keinen Wert,
    sondern eine Antwort: das Datum fehlt, weil die Quelle keines schickt, und
    das ist die richtige Ausgabe — kein Absturz und keine Erfindung.
    """
    aufzeichnung = fixture_json("ckan_package_show.json")
    ressourcen = aufzeichnung["result"]["resources"]
    assert all(r.get("last_modified") is None for r in ressourcen), (
        "die Quelle fuellt `last_modified` wieder — dann prueft dieser Test nichts mehr"
    )
    respx.get(url__startswith=f"{CKAN_BASE}/package_show").mock(
        return_value=httpx.Response(200, json=aufzeichnung)
    )
    antwort = await seco_get_dataset(DatasetDetailsInput(dataset_id=aufzeichnung["result"]["name"]))
    assert not antwort.startswith("Error"), antwort[:200]
    assert ressourcen[0]["url"] in antwort, "die Ressourcen stehen in der Antwort"
    assert "Aktualisiert" in antwort, "das Datum des Datensatzes kommt aus `metadata_modified`"


def test_der_titel_kommt_als_sprachwoerterbuch():
    """Eine Form, die ein Stub leicht als blanken String geraten haette.

    `_extract_title` faengt beides ab — belegt ist erst hier, welche der beiden
    Formen die Quelle wirklich schickt.
    """
    ds = fixture_json("ckan_package_show.json")["result"]
    assert isinstance(ds["title"], dict), "CKAN liefert den Titel je Sprache"
    assert ds["title"].get("de"), "und mindestens die deutsche Fassung ist gefuellt"


@respx.mock
async def test_der_weg_von_der_ressource_in_die_csv(monkeypatch):
    """Der zweite Weg des Servers: Datensatz → Ressourcenliste → Datei.

    Er laeuft heute nie an, weil die Suche keinen Datensatz liefert. Genau
    deshalb wird er hier mit dem aufgezeichneten Datensatz direkt gefuettert —
    sonst bliebe der ganze CSV-Zweig ungeprueft, bis der Filter repariert ist.

    Die SSRF-Pruefung ist ueberbrueckt, wie in `TestCsvFetchRetry`: sie loest
    DNS wirklich auf und kehrt ohne Netz zurueck, bevor respx gefragt wird. Hier
    geht es um den Weg in die CSV, nicht um die Policy — die hat ihre eigenen
    Tests.
    """

    async def _erlauben(_url: str) -> None:
        return None

    monkeypatch.setattr(_server_mod, "_validate_external_url", _erlauben)
    ds = fixture_json("ckan_package_show.json")["result"]
    ressource = next(r for r in ds["resources"] if (r.get("format") or "").upper() == "CSV")
    respx.get(ressource["url"]).mock(
        return_value=httpx.Response(200, text=fixture_text("ckan_ressource.csv"))
    )
    live = await _try_live_csv([ds])
    assert live is not None, "die aufgezeichnete CSV soll sauber parsen"
    assert live["headers"], "die Kopfzeile ist die Satzform und bleibt unveraendert"
    assert live["total_rows"] > 1
    assert live["delimiter"] == ",", "diese Quelle trennt mit Komma, nicht mit Semikolon"


def test_die_aufgezeichnete_csv_traegt_ganze_zeitreihen():
    """Gekuerzt ist die Zahl der Zeilen, nicht die der Spalten.

    Die Datei beginnt mit einer einzigen Gemeinde im aeltesten Jahr. Eine
    Kopfauswahl haette weder die Spanne noch das juengste Jahr belegt — und
    `_detect_latest_period` liest genau die Jahresspalte.
    """
    zeilen = [z for z in fixture_text("ckan_ressource.csv").splitlines() if z]
    kopf = zeilen[0].split(",")
    assert "INDIKATOR_JAHR" in kopf and "GEBIET_NAME" in kopf
    jahr = kopf.index("INDIKATOR_JAHR")
    gebiet = kopf.index("GEBIET_NAME")
    daten = [z.split(",") for z in zeilen[1:]]
    gebiete = {z[gebiet] for z in daten}
    assert len(gebiete) == 2, f"zwei Zeitreihen erwartet, gefunden: {sorted(gebiete)}"
    for name in gebiete:
        jahre = sorted(int(z[jahr]) for z in daten if z[gebiet] == name)
        assert len(jahre) > 10, f"{name} traegt nur {len(jahre)} Jahre — Auswahlregel pruefen"
        assert jahre == list(range(jahre[0], jahre[-1] + 1)), f"{name} hat Luecken"


# --------------------------------------------------------------------------
# unfallstatistik.ch — die Parser an der echten Quelle
# --------------------------------------------------------------------------


def test_schluesselzahlen_aus_der_aufzeichnung():
    """Die HTML-Tabelle, so wie sie ankommt — nicht so, wie ein Stub sie setzt."""
    ergebnis = uvg.parse_key_figures(
        fixture_bytes("uvg_schluesselzahlen.html").decode("utf-8-sig", errors="replace")
    )
    assert ergebnis["parsed"], ergebnis.get("reason")
    assert len(ergebnis["years"]) == 5, "die Quelle zeigt fuenf Jahresspalten"
    assert ergebnis["years"] == sorted(ergebnis["years"]), "aufsteigend, wie im Kopf"
    assert ergebnis["rows"], "und mindestens eine Datenzeile"


def test_die_luecken_verschieben_die_jahre_nicht():
    """Die meisten Zeilen sind kuerzer als der Tabellenkopf — und das ist richtig.

    Nicht jedes Jahr ist in jeder Zeile gefuellt: die Quelle setzt dort `&nbsp;`,
    und der Parser laesst die Zelle weg statt einen Wert zu erfinden. 16 der 21
    aufgezeichneten Zeilen fuehren deshalb vier statt fuenf Werte.

    Entscheidend ist, dass jeder verbliebene Wert **sein eigenes Jahr** behaelt.
    Die Aufzeichnung enthaelt beide Faelle: «Versicherte Betriebe» fehlt das
    juengste Jahr, «UV IV» das aelteste. Wuerde der Parser die Werte einfach von
    links auffuellen, stuende bei «UV IV» der Wert von 2022 unter 2021 — eine
    Zahl beim falschen Jahr, die kein Formfehler ist und die niemandem
    auffiele. Ein erfundener Stub haette ueberall volle Zeilen gesetzt und diese
    Frage nie gestellt.
    """
    ergebnis = uvg.parse_key_figures(
        fixture_bytes("uvg_schluesselzahlen.html").decode("utf-8-sig", errors="replace")
    )
    jahre = ergebnis["years"]
    vorne, hinten = 0, 0
    for zeile in ergebnis["rows"]:
        gelesen = [w["year"] for w in zeile["values"]]
        assert gelesen, f"{zeile['label']!r} ohne einen einzigen Wert"
        # Teilfolge in unveraenderter Reihenfolge: jeder Wert steht bei einem
        # Jahr des Kopfes, und die Reihenfolge bleibt.
        rest = iter(jahre)
        assert all(j in rest for j in gelesen), (
            f"{zeile['label']!r} liest {gelesen} — keine Teilfolge von {jahre}"
        )
        vorne += gelesen[0] != jahre[0]
        hinten += gelesen[-1] != jahre[-1]
    assert hinten, "keine Zeile ohne juengstes Jahr — dann prueft dieser Test nichts"
    assert vorne, (
        "keine Zeile ohne aeltestes Jahr — genau die widerlegt ein Auffuellen "
        "von links; ohne sie ist die Zusicherung nur halb"
    )


@pytest.mark.parametrize("tabelle", ["1.2", "2.4_BUV", "2.4_NBUV"])
def test_die_jahrestabellen_lesen_sich_aus_dem_echten_pdf(tabelle):
    """Alle drei Tabellen aus dem aufgezeichneten Jahresbericht.

    Der Parser verbindet Zahlen aus dem Layout-Modus mit Beschriftungen aus dem
    Textmodus. Ob das traegt, entscheidet die Satzweise des echten Dokuments —
    Silbentrennung, Leerzeichen in Zahlen, Sternchen — und keine nachgebildete
    Seite.
    """
    pdf = fixture_bytes("uvg_jahresbericht_ts26.pdf")
    ergebnis = uvg.parse_branch_table(
        uvg._pdf_pages(pdf, layout=True), uvg._pdf_pages(pdf), tabelle
    )
    assert ergebnis["parsed"], ergebnis.get("reason")
    assert ergebnis["rows"], "die Tabelle traegt Zeilen"
    spalten = uvg.TABLE_SPECS[tabelle]["columns"]
    assert all(set(spalten) <= set(r) for r in ergebnis["rows"]), (
        f"jede Zeile fuehrt alle Spalten {spalten}"
    )
    assert any(r["row_type"] == "branch" for r in ergebnis["rows"]), (
        "mindestens eine NOGA-Zeile — sonst hat die Verbindung ueber den Code nicht getragen"
    )
    assert ergebnis["printed_total"], "die gedruckte Total-Zeile gehoert dazu"


def test_die_gekuerzten_seiten_tragen_ihre_tabellen_vollstaendig():
    """Gekuerzt ist die Zahl der Seiten, nie ihr Inhalt.

    Drei von 70 Seiten sind aufgezeichnet — die drei, auf denen die Tabellen
    stehen. Der Recorder sucht sie an ihrer Beschriftung, statt Seitenzahlen zu
    pinnen: verschiebt die Quelle ihre Tabellen, faellt das Aufzeichnen auf,
    nicht erst der Parser.
    """
    seiten = uvg._pdf_pages(fixture_bytes("uvg_jahresbericht_ts26.pdf"))
    assert len(seiten) == 3, f"{len(seiten)} Seiten aufgezeichnet — Auswahlregel pruefen"
    gesamt = "\n".join(seiten)
    assert "Tabelle 1.2" in gesamt
    assert "Berufsunfallversicherung" in gesamt
    assert "Nichtberufsunfallversicherung" in gesamt


def test_die_branchenreihe_liest_apostrophe_als_tausendertrenner():
    """Dieselbe Quelle, zwei Zahlenformate — belegt statt behauptet.

    Die Jahrestabellen trennen Tausender mit einem Leerzeichen, diese
    PDF-Familie mit einem Apostroph. Eine erfundene Fixture haette leicht
    ueberall dasselbe Format gezeigt.
    """
    roh = fixture_bytes("uvg_branche_buv_41.pdf")
    assert "'" in "\n".join(uvg._pdf_pages(roh)), "die Aufzeichnung traegt Apostroph-Zahlen"
    ergebnis = uvg.parse_branch_series(uvg._pdf_pages(roh))
    assert ergebnis["parsed"], ergebnis.get("reason")
    assert len(ergebnis["years"]) == 10, "eine 10-Jahres-Reihe"
    assert ergebnis["years"] == sorted(ergebnis["years"])


def test_die_publikationsliste_nennt_ausgaben():
    """Aus ihr leitet `resolve_latest_edition` her, welcher Jahrgang existiert."""
    text = fixture_bytes("uvg_publikationen.html").decode("utf-8-sig", errors="replace")
    assert re.search(r"Ts\d{2}", text) or re.search(r"20\d{2}", text), (
        "die Seite soll Ausgaben oder Jahre nennen"
    )
