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
import io
import json
import re

import httpx
import pytest
import respx
from fixture_data import fixture_bytes, fixture_json, provenance, recorded_names

from seco_labor_mcp import kantone, sources, uvg
from seco_labor_mcp import server as _server_mod
from seco_labor_mcp.server import (
    CANTON_CODES,
    CKAN_BASE,
    DatasetDetailsInput,
    DatasetSearchInput,
    JobSeekersInput,
    ResponseFormat,
    UnemploymentInput,
    YouthUnemploymentInput,
    seco_get_dataset,
    seco_get_job_seekers,
    seco_get_unemployment_overview,
    seco_get_youth_unemployment,
    seco_search_datasets,
)

# Jeder externe Endpunkt dieses Servers und die Fixture dazu. Ein Endpunkt ohne
# Aufzeichnung faellt in `test_jeder_endpunkt_hat_eine_aufzeichnung`.
ENDPUNKTE = {
    "ckan/package_search": "ckan_package_search.json",
    "ckan/package_show": "ckan_package_show.json",
    "ckan/package_show (gepinnte Jahresreihe)": "ckan_package_show_jahresreihe.json",
    "die XLS-Ressource der gepinnten Jahresreihe": "bfs_jahresreihe.xlsx",
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


# --------------------------------------------------------------------------
# Die gepinnte BFS-Tabelle mit den SECO-Reihen
# --------------------------------------------------------------------------


def test_die_gepinnte_kennung_zeigt_auf_den_aufgezeichneten_datensatz():
    """Ein Literal-Register statt eines Namensabgleichs — und der Beleg dazu.

    Der Organisationsfilter war ein Namensabgleich und lief still ins Leere, als
    die Organisation verschwand. Die Kennung in `sources.py` ist dagegen eine
    UUID, und diese Zusicherung haelt sie gegen eine datierte Antwort der
    Quelle. Der Live-Test in `test_live.py` prueft dieselbe Kennung gegen die
    echte Quelle — zusammen ergibt das: verschwindet der Datensatz, wird ein
    Test rot statt eine Antwort leer.
    """
    ds = fixture_json("ckan_package_show_jahresreihe.json")["result"]
    assert ds["id"] == sources.JAHRESREIHE.ckan_id
    assert ds["name"] == sources.JAHRESREIHE.slug
    formate = {(r.get("format") or "").upper() for r in ds["resources"]}
    assert "XLS" in formate or "XLSX" in formate, (
        f"der Datensatz fuehrt keine Tabellenressource mehr: {sorted(formate)}"
    )


def test_die_drei_reihen_stehen_in_der_aufgezeichneten_tabelle():
    """Beschriftungen wörtlich, nicht über die Zeilenposition geraten."""
    daten = sources.parse_jahresreihe(fixture_bytes("bfs_jahresreihe.xlsx"))
    assert set(daten["series"]) == set(sources.REIHEN)
    for schluessel, praefix in sources.REIHEN.items():
        assert daten["labels"][schluessel].startswith(praefix)
    jahre = daten["years"]
    assert jahre == sorted(jahre) and len(jahre) > 20
    for schluessel, werte in daten["series"].items():
        assert werte, f"Reihe {schluessel} ist leer"
        assert set(werte) <= set(jahre)


def test_die_ilo_reihe_ist_nicht_die_registrierte():
    """Die Verwechslung, die dieser Umbau verhindern soll — an Zahlen.

    Beide Reihen stehen im selben Blatt untereinander und sehen dadurch
    vergleichbar aus. Wer die eine fuer die andere einsetzt, weil gerade nur
    die eine erreichbar ist, produziert eine Zahl, die plausibel aussieht und
    im Jahr 2000 um drei Viertel danebenliegt.
    """
    daten = sources.parse_jahresreihe(fixture_bytes("bfs_jahresreihe.xlsx"))
    registriert = daten["series"]["registrierte_arbeitslose"]
    ilo = daten["series"]["erwerbslose_ilo"]
    gemeinsam = sorted(set(registriert) & set(ilo))
    assert gemeinsam, "die beiden Reihen teilen keine Jahre"
    abstaende = [ilo[j] / registriert[j] for j in gemeinsam if registriert[j]]
    assert max(abstaende) > 1.3, (
        "die ILO-Reihe liegt nirgends deutlich ueber der registrierten — dann "
        "misst die Aufzeichnung nicht mehr, was dieser Test meint"
    )
    # Und die Stellensuchenden liegen ihrerseits ueber den Arbeitslosen: sie
    # schliessen Massnahmen und Zwischenverdienst ein.
    suchende = daten["series"]["registrierte_stellensuchende"]
    assert all(suchende[j] > registriert[j] for j in gemeinsam if j in suchende)


def test_die_tabelle_meldet_eine_formaenderung_statt_sie_zu_verschlucken():
    """Fehlt eine Reihe, ist eine benannte Ausnahme das Ergebnis, keine leere Reihe."""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(fixture_bytes("bfs_jahresreihe.xlsx")))
    ws = wb[sources.JAHRESREIHE.blatt]
    for zeile in ws.iter_rows(max_row=12):
        if isinstance(zeile[0].value, str) and zeile[0].value.startswith(
            sources.REIHEN["registrierte_arbeitslose"]
        ):
            zeile[0].value = "Irgendetwas anderes"
            break
    puffer = io.BytesIO()
    wb.save(puffer)
    with pytest.raises(sources.TabelleNichtLesbarError, match="Registrierte Arbeitslose"):
        sources.parse_jahresreihe(puffer.getvalue())


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
    assert "staatssekretariat-fur-wirtschaft-seco" in provenance(), (
        "der Befund nennt die Organisation, auf die frueher gefiltert wurde"
    )


@respx.mock
async def test_die_suche_schickt_keinen_organisationsfilter_mehr():
    """Hält die Behebung fest, an der abgeschickten Anfrage.

    Der Filter war die Ursache des Ausfalls: ein Namensabgleich auf eine
    Organisation, die es nicht mehr gibt. Diese Zusicherung liest die
    tatsächlich gestellte Anfrage, nicht die Absicht — kehrt der Filter zurück,
    fällt sie, und zwar bevor wieder jede Suche leer antwortet.
    """
    route = respx.get(url__startswith=f"{CKAN_BASE}/package_search").mock(
        return_value=httpx.Response(
            200, json=fixture_json("ckan_package_search_ohne_organisation.json")
        )
    )
    antwort = await seco_search_datasets(DatasetSearchInput(query="arbeitslose kantone"))
    gestellt = str(route.calls.last.request.url)
    assert "organization" not in gestellt, f"die Suche filtert wieder: {gestellt}"
    assert "Keine Datensätze" not in antwort, antwort[:200]


@respx.mock
async def test_jeder_treffer_nennt_seinen_herausgeber():
    """Ohne Filter stammen die Treffer von anderen Häusern — das muss dranstehen.

    Die aufgezeichnete ungefilterte Suche liefert Datensätze des BFS, mehrerer
    Kantone und des liechtensteinischen Amts für Statistik. Sie unter der
    Überschrift «SECO-Datensätze» zu zeigen wäre genau die Verwechslung, die
    dieser Umbau behebt.
    """
    aufzeichnung = fixture_json("ckan_package_search_ohne_organisation.json")
    respx.get(url__startswith=f"{CKAN_BASE}/package_search").mock(
        return_value=httpx.Response(200, json=aufzeichnung)
    )
    antwort = await seco_search_datasets(DatasetSearchInput(query="arbeitslose", limit=5))
    assert "SECO-Datensätze" not in antwort, "die Treffer stammen nicht von SECO"
    assert "Herausgeber" in antwort
    herausgeber = {
        (ds.get("organization") or {}).get("name") for ds in aufzeichnung["result"]["results"][:5]
    }
    assert len(herausgeber) > 1, (
        "die Aufzeichnung führt nur einen Herausgeber — dann prüft dieser Test wenig"
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


# --------------------------------------------------------------------------
# Die Werkzeuge an der aufgezeichneten Tabelle
# --------------------------------------------------------------------------


def _mock_jahresreihe() -> None:
    """Beide Schritte des Servers: `package_show` und dann die XLS-Ressource."""
    aufzeichnung = fixture_json("ckan_package_show_jahresreihe.json")
    respx.get(url__startswith=f"{CKAN_BASE}/package_show").mock(
        return_value=httpx.Response(200, json=aufzeichnung)
    )
    xls = next(
        r
        for r in aufzeichnung["result"]["resources"]
        if (r.get("format") or "").upper() in {"XLS", "XLSX"}
    )
    respx.get(xls["url"]).mock(
        return_value=httpx.Response(200, content=fixture_bytes("bfs_jahresreihe.xlsx"))
    )


@respx.mock
async def test_die_uebersicht_liefert_wieder_zahlen():
    """Vorher lief dieses Werkzeug nie an eine Quelle — jetzt schon."""
    _mock_jahresreihe()
    roh = await seco_get_unemployment_overview(
        UnemploymentInput(response_format=ResponseFormat.JSON)
    )
    daten = json.loads(roh)
    assert daten["registrierte_arbeitslose_seco"] > 0
    assert daten["granularity"] == "annual_national"
    assert "SECO" in daten["source"] and "BFS" in daten["source"], (
        "die Herkunft nennt beide Häuser: SECOs Zahl, BFS' Veröffentlichung"
    )
    # Die drei Reihen kommen getrennt heraus und nicht ineinander gerechnet.
    assert daten["erwerbslose_ilo_bfs"] != daten["registrierte_arbeitslose_seco"]


@respx.mock
async def test_die_uebersicht_erfindet_keine_kantonale_zahl():
    """Statt der früheren Rangliste vom April 2025 eine benannte Absage.

    Ein Warnhinweis neben einer Zahl verliert gegen die Zahl: gelesen wird die
    Quote, nicht der Hinweis. Eine Absage kann man nicht falsch zitieren.

    Geprüft an Bern: seit der kantonalen Schicht liefert Zürich echte Werte,
    und der Test hätte sonst still aufgehört, eine Absage zu prüfen.
    """
    _mock_jahresreihe()
    roh = await seco_get_unemployment_overview(
        UnemploymentInput(canton="BE", response_format=ResponseFormat.JSON)
    )
    daten = json.loads(roh)
    assert daten["data_available"] is False
    assert "amstat.ch" in " ".join(daten["where"])
    text = await seco_get_unemployment_overview(UnemploymentInput(canton="BE"))
    assert "%" not in text, f"eine Quote in einer Absage ist eine Zahl zu viel: {text[:200]}"


@respx.mock
async def test_die_stellensuchenden_zeigen_den_abstand():
    """Die Differenz ist die Aussage dieser Reihe, nicht die Zahl allein."""
    _mock_jahresreihe()
    daten = json.loads(
        await seco_get_job_seekers(JobSeekersInput(response_format=ResponseFormat.JSON))
    )
    assert daten["registrierte_stellensuchende_seco"] > daten["registrierte_arbeitslose_seco"]
    assert daten["differenz_in_massnahmen"] > 0


async def test_die_jugendarbeitslosigkeit_nennt_keine_beispielzahl():
    """Die erfundene Zahl ist weg — und darf nicht zurückkommen.

    Vorher stand hier «+2'186 Jugendarbeitslose (+18.6%)» als Beispielwert aus
    einem Snapshot. Eine als Beispiel eingeführte Zahl wird als Zahl zitiert;
    der Zusatz «Snapshot» überlebt das Zitieren nicht.
    """
    text = await seco_get_youth_unemployment(YouthUnemploymentInput())
    assert "2'186" not in text and "18.6" not in text
    # Keine Tausendertrenner und keine Prozentwerte. Jahreszahlen wie das
    # Pruefdatum sind erlaubt — sie datieren den Befund, statt ihn zu ersetzen.
    assert not re.search(r"\d[\.\d]*\s?%", text), f"Prozentwert in der Absage: {text[:300]}"
    assert not re.search(r"\d['’]\d", text), f"Tausenderzahl in der Absage: {text[:300]}"
    assert "keine zahlen verfügbar" in text.lower()
    daten = json.loads(
        await seco_get_youth_unemployment(
            YouthUnemploymentInput(response_format=ResponseFormat.JSON)
        )
    )
    assert daten["data_available"] is False
    assert "amstat" in json.dumps(daten)


@respx.mock
async def test_eine_formaenderung_der_tabelle_wird_gemeldet():
    """Kommt die Mappe ohne die erwartete Reihe, ist das ein Fehler und keine Null."""
    aufzeichnung = fixture_json("ckan_package_show_jahresreihe.json")
    respx.get(url__startswith=f"{CKAN_BASE}/package_show").mock(
        return_value=httpx.Response(200, json=aufzeichnung)
    )
    xls = next(
        r
        for r in aufzeichnung["result"]["resources"]
        if (r.get("format") or "").upper() in {"XLS", "XLSX"}
    )
    respx.get(xls["url"]).mock(return_value=httpx.Response(200, content=b"kein xlsx"))
    # Bewusst eine Ausnahme und keine Zeichenkette: eine Formaenderung ist
    # nichts, was das Modell mit anderen Argumenten umgehen koennte. `OBS-001`
    # laesst genau diese Klasse durch, damit FastMCP `isError: true` daraus
    # macht — dieselbe Regel wie bei `UpstreamSchemaError`.
    with pytest.raises(sources.TabelleNichtLesbarError, match="nicht lesbar"):
        await seco_get_unemployment_overview(UnemploymentInput(response_format=ResponseFormat.JSON))


# --------------------------------------------------------------------------
# Die kantonale Schicht: vier Kantone, vier Schemata
# --------------------------------------------------------------------------

KANTONS_FIXTURES = {
    "TG": "kanton_tg.csv",
    "FR": "kanton_fr.csv",
    "ZG": "kanton_zg.csv",
    "ZH": "kanton_zh.csv",
}


def _kantonsdaten(kuerzel: str) -> dict:
    reihe = kantone.KANTONE[kuerzel]
    payload = fixture_bytes(KANTONS_FIXTURES[kuerzel])
    if kuerzel == "ZG":
        return kantone.parse_zg(payload, reihe, fixture_bytes("kanton_zg_quoten.csv"))
    return kantone.PARSER[kuerzel](payload, reihe)


@pytest.mark.parametrize("kuerzel", sorted(KANTONS_FIXTURES))
def test_jeder_kanton_hat_eine_aufzeichnung(kuerzel):
    """Ein gepinnter Kanton ohne Aufzeichnung ist eine ungeprüfte Zusage."""
    assert KANTONS_FIXTURES[kuerzel] in recorded_names()
    assert fixture_bytes(KANTONS_FIXTURES[kuerzel])


@pytest.mark.parametrize("kuerzel", sorted(KANTONS_FIXTURES))
def test_jeder_adapter_liest_seine_aufzeichnung(kuerzel):
    """Vier Schemata, vier Adapter — jeder gegen die echte Antwort seines Kantons."""
    daten = _kantonsdaten(kuerzel)
    assert daten["kanton"] == kuerzel
    assert daten["granularitaet"] == kantone.KANTONE[kuerzel].granularitaet
    inhalt = next(v for k, v in daten.items() if k.startswith("nach_"))
    assert inhalt, f"{kuerzel}: der Adapter liefert keine Datenpunkte"


@pytest.mark.parametrize("kuerzel", sorted(KANTONS_FIXTURES))
def test_ein_umbenanntes_feld_wird_gemeldet(kuerzel):
    """Ohne diese Prüfung würde ein Schemawechsel zu null Treffern statt zu einem Fehler.

    Genau das ist beim ersten Lauf passiert: die über CKAN verlinkte Freiburger
    Ressource trägt beschriftete Spalten (`Total chômeurs`), nicht die
    technischen Namen des Portals. Der Adapter hat es gemeldet, statt eine
    leere Reihe zu liefern.
    """
    reihe = kantone.KANTONE[kuerzel]
    roh = fixture_bytes(KANTONS_FIXTURES[kuerzel]).decode("utf-8-sig")
    zeilen = roh.split("\n")
    zeilen[0] = zeilen[0].replace(reihe.felder[0], "umbenannt", 1)
    kaputt = "\n".join(zeilen).encode("utf-8")
    with pytest.raises(kantone.KantonsReiheNichtLesbarError, match="Spalten fehlen"):
        if kuerzel == "ZG":
            kantone.parse_zg(kaputt, reihe, None)
        else:
            kantone.PARSER[kuerzel](kaputt, reihe)


def test_zuerich_trennt_gemeinden_von_bezirken():
    """Der Fund, den erst die echte Antwort gezeigt hat.

    «Zürich - ganzer Kanton», «Bezirk Horgen» und «Region Glattal» stehen in
    derselben Spalte wie die Gemeinden. Eine nach Grösse sortierte Liste
    stellt dann den Kantonswert an die Spitze der «grössten Gemeinden».
    Unterschieden werden sie an `BFS_NR`: Aggregate tragen 0.
    """
    daten = _kantonsdaten("ZH")
    jahr = sorted(daten["nach_gemeinde"])[-1]
    gemeinden = daten["nach_gemeinde"][jahr]
    aggregate = daten["aggregate"][jahr]
    assert any("ganzer Kanton" in g for g in aggregate), "der Kantonswert gehört zu den Aggregaten"
    assert not any("Bezirk" in g or "Region" in g for g in gemeinden), (
        f"Aggregate unter den Gemeinden: {[g for g in gemeinden if 'Bezirk' in g]}"
    )
    kantonswert = next(w for g, w in aggregate.items() if "ganzer Kanton" in g)
    groesste = max(gemeinden.values())
    assert kantonswert > groesste, (
        "der Kantonswert muss über der grössten Gemeinde liegen — sonst ist die "
        "Trennung nicht die, für die sie gehalten wird"
    )


def test_freiburg_fuehrt_die_schweizer_zeile_mit():
    """Der zweite Fund: eine kantonale Quelle trägt die Monatszahl der Schweiz.

    PR #28 hielt fest, es gebe keine maschinenlesbare monatliche Reihe für die
    Schweiz. Das stimmt für Datensätze *über* die Schweiz; die Freiburger Reihe
    führt sie als Vergleichszeile mit. Der Befund gehört korrigiert, nicht
    stehengelassen.
    """
    daten = _kantonsdaten("FR")
    periode = sorted(daten["nach_gebiet"])[-1]
    werte = daten["nach_gebiet"][periode]
    assert set(werte) == {"FR", "CH"}
    assert werte["CH"]["arbeitslose"] > werte["FR"]["arbeitslose"] * 10, (
        "die Schweizer Zeile soll deutlich über der kantonalen liegen"
    )
    assert werte["FR"]["stellensuchende"] > werte["FR"]["arbeitslose"], (
        "Stellensuchende schliessen die Arbeitslosen ein"
    )


def test_zug_fuehrt_die_jugend_nur_als_quote():
    """Eine Quote ist keine Anzahl — und Zug liefert nur die Quote."""
    daten = _kantonsdaten("ZG")
    werte = daten["nach_periode"][sorted(daten["nach_periode"])[-1]]
    assert "Jugendarbeitslosenquote" in werte
    assert werte["Jugendarbeitslosenquote"] < 100, "eine Quote in Prozent, keine Anzahl"
    assert werte["Arbeitslose"] > 100, "die Anzahl steht daneben und ist eine andere Grösse"


def test_thurgau_fuehrt_die_jugend_als_anzahl():
    """Und Thurgau nur die Anzahl — die beiden Kantone sind nicht vergleichbar."""
    daten = _kantonsdaten("TG")
    periode = sorted(daten["nach_alter"])[-1]
    jung = daten["nach_alter"][periode]["15-24 Jahre"]
    assert jung["Registrierte Arbeitslose"] > 1, "eine Anzahl, keine Quote"
    assert jung["Registrierte Stellensuchende"] > jung["Registrierte Arbeitslose"]


def test_das_register_nennt_genau_die_kantone_mit_daten():
    """Die Teilabdeckung steht im Register, nicht in einem Kommentar."""
    assert set(kantone.KANTONE) == set(KANTONS_FIXTURES)
    assert len(kantone.KANTONE) < 26, "vier von 26 — keine gesamtschweizerische Abdeckung"
    for kuerzel, reihe in kantone.KANTONE.items():
        assert kuerzel in CANTON_CODES
        assert reihe.granularitaet in ("monatlich", "jaehrlich")
        assert reihe.herausgeber and reihe.ab


# --------------------------------------------------------------------------
# Die Werkzeuge über der kantonalen Schicht
# --------------------------------------------------------------------------


def _mock_kanton(kuerzel: str) -> None:
    """`package_show` auf die gepinnte Kennung, dann die CSV-Ressource."""
    reihe = kantone.KANTONE[kuerzel]
    url = f"https://example.test/{kuerzel}.csv"
    paket = {
        "success": True,
        "result": {
            "id": reihe.ckan_id,
            "name": reihe.slug,
            "metadata_modified": "2026-08-15T00:00:00",
            "resources": [{"format": "CSV", "url": url}],
        },
    }
    routen = [(reihe.ckan_id, paket, url, KANTONS_FIXTURES[kuerzel])]
    if reihe.zweite_ckan_id:
        url2 = f"https://example.test/{kuerzel}_quoten.csv"
        routen.append(
            (
                reihe.zweite_ckan_id,
                {
                    "success": True,
                    "result": {
                        "id": reihe.zweite_ckan_id,
                        "name": reihe.zweiter_slug,
                        "metadata_modified": "2026-08-15T00:00:00",
                        "resources": [{"format": "CSV", "url": url2}],
                    },
                },
                url2,
                "kanton_zg_quoten.csv",
            )
        )
    for ckan_id, antwort, res_url, fixture in routen:
        respx.get(
            url__startswith=f"{CKAN_BASE}/package_show", params__contains={"id": ckan_id}
        ).mock(return_value=httpx.Response(200, json=antwort))
        respx.get(res_url).mock(return_value=httpx.Response(200, content=fixture_bytes(fixture)))


@pytest.mark.parametrize("kuerzel", sorted(KANTONS_FIXTURES))
@respx.mock
async def test_die_uebersicht_liefert_kantonale_zahlen(kuerzel, monkeypatch):
    """Wo eine Reihe existiert, kommt eine Zahl heraus — mit ihrer Herkunft."""

    async def _erlauben(_url: str) -> None:
        return None

    monkeypatch.setattr(_server_mod, "_validate_external_url", _erlauben)
    _mock_kanton(kuerzel)
    daten = json.loads(
        await seco_get_unemployment_overview(
            UnemploymentInput(canton=kuerzel, response_format=ResponseFormat.JSON)
        )
    )
    assert daten["canton"] == kuerzel
    assert daten["granularity"] == (
        "annual" if kantone.KANTONE[kuerzel].granularitaet == "jaehrlich" else "monthly"
    )
    assert kantone.KANTONE[kuerzel].herausgeber in daten["source"]
    assert "SECO" in daten["source"], "die Datenquelle bleibt SECO, auch wenn ein Kanton publiziert"
    warnung = daten["not_comparable_across_cantons"]
    assert "addiert" in warnung and "keine Schweizer Zahl" in warnung, warnung


@respx.mock
async def test_ein_kanton_ohne_reihe_bekommt_weiter_eine_absage():
    """22 Kantone publizieren nicht — und bekommen keine fremde Zahl."""
    daten = json.loads(
        await seco_get_unemployment_overview(
            UnemploymentInput(canton="BE", response_format=ResponseFormat.JSON)
        )
    )
    assert daten["data_available"] is False
    assert set(daten["cantons_with_data"]) == set(kantone.KANTONE)
    text = await seco_get_unemployment_overview(UnemploymentInput(canton="BE"))
    assert "keine Daten" in text
    assert not re.search(r"\d['’]\d", text), f"Zahl in der Absage: {text[:300]}"


@respx.mock
async def test_die_jugendzahl_kommt_nur_aus_den_zwei_kantonen(monkeypatch):
    """TG als Anzahl, ZG als Quote — und beide nicht als dasselbe Feld."""

    async def _erlauben(_url: str) -> None:
        return None

    monkeypatch.setattr(_server_mod, "_validate_external_url", _erlauben)
    _mock_kanton("TG")
    tg = json.loads(
        await seco_get_youth_unemployment(
            YouthUnemploymentInput(canton="TG", response_format=ResponseFormat.JSON)
        )
    )
    assert tg["measure"] == "count"
    assert tg["youth_15_24"]["Registrierte Arbeitslose"] > 1
    assert "youth_unemployment_rate_pct" not in tg


@respx.mock
async def test_zug_liefert_eine_quote_und_nennt_sie_so(monkeypatch):
    async def _erlauben(_url: str) -> None:
        return None

    monkeypatch.setattr(_server_mod, "_validate_external_url", _erlauben)
    _mock_kanton("ZG")
    zg = json.loads(
        await seco_get_youth_unemployment(
            YouthUnemploymentInput(canton="ZG", response_format=ResponseFormat.JSON)
        )
    )
    assert zg["measure"] == "rate_pct"
    assert zg["youth_unemployment_rate_pct"] < 100
    assert "youth_15_24" not in zg, "eine Quote darf nicht im Anzahl-Feld landen"


async def test_ein_kanton_mit_reihe_aber_ohne_alter_sagt_das_auch():
    """Zürich publiziert Arbeitslose, aber nicht nach Alter — ein dritter Fall.

    Ihn wie «keine Quelle» zu beantworten schickte jemanden zu amstat.ch, der
    zwei Zeilen weiter eine kantonale Reihe bekommen hätte.
    """
    daten = json.loads(
        await seco_get_youth_unemployment(
            YouthUnemploymentInput(canton="ZH", response_format=ResponseFormat.JSON)
        )
    )
    assert daten["data_available"] is False
    assert daten["available_from_this_canton"] == "seco_get_unemployment_overview"
    assert set(daten["cantons_with_youth_data"]) == {"TG", "ZG"}
