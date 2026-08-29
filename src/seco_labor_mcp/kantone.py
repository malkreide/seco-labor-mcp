"""Die kantonale Schicht: vier Kantone, vier Schemata, ein Ergebnisformat.

Der nationale Weg (``sources.py``) liefert Jahresdurchschnitte. Monatswerte und
kantonale Aufschlüsselungen gibt es national nicht maschinenlesbar — wohl aber
bei einzelnen **Kantonen**, die ihre RAV-Zahlen selbst publizieren. Vier tun
das in einer Form, die ein Server lesen kann; **22 nicht**.

Das ist die wichtigste Eigenschaft dieses Moduls, und sie steht deshalb im
Register und nicht in einem Kommentar: ``KANTONE`` ist die vollständige Liste
der Kantone, für die es Zahlen gibt. Für jeden anderen liefert der Server eine
benannte Absage. Eine Teilabdeckung, die sich wie eine vollständige anfühlt,
ist schlimmer als gar keine — wer für Bern eine Zahl bekommt, die in Wahrheit
aus Thurgau stammt, merkt es nie.

**Vier Kantone, vier Schemata.** Das ist keine Nachlässigkeit der Kantone,
sondern der Stand: jedes Statistikamt publiziert in seinem eigenen Portal mit
eigenen Spaltennamen, eigener Zeitachse und eigenem Begriffsumfang. Ein
gemeinsamer Parser müsste raten; stattdessen hat jeder Kanton hier einen
eigenen Adapter, der genau ein Schema liest und bei jeder Abweichung laut
scheitert.

Was die Adapter **nicht** tun: Kantone zu einer Schweizer Zahl addieren. Vier
von 26 sind keine Schweiz, und die Zeitachsen decken sich nicht einmal
untereinander (ZH jährlich seit 1991, ZG monatlich seit 1993, FR monatlich seit
2004, TG monatlich seit 2016).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any, Literal

Granularitaet = Literal["monatlich", "jaehrlich"]


class KantonsReiheNichtLesbarError(RuntimeError):
    """Die Antwort kam an, trug aber nicht die erwarteten Spalten."""


@dataclass(frozen=True)
class KantonsReihe:
    """Ein gepinnter kantonaler Datensatz.

    ``ckan_id`` ist die UUID auf opendata.swiss; ueber sie holt der Server die
    aktuelle Ressourcen-URL, statt die Portal-URL des Kantons zweitzupinnen.
    Die aendert sich, wenn ein Kanton sein Portal umzieht — die CKAN-Kennung
    ueberlebt das.
    """

    kanton: str
    ckan_id: str
    slug: str
    herausgeber: str
    granularitaet: Granularitaet
    ab: str
    kennzahlen: tuple[str, ...]
    gebietsebene: str
    hinweis: str = ""
    zweite_ckan_id: str = ""
    zweiter_slug: str = ""
    trennzeichen: str = ";"
    felder: tuple[str, ...] = field(default=())
    # Die Pflichtspalten des **zweiten** Datensatzes, wo es einen gibt. Ohne
    # dieses Feld wurde der zweite Abruf ungeprueft gelesen: `parse_zg` griff
    # mit `.get("quote")` zu, und eine umbenannte Spalte lieferte fuer jede
    # Zeile `None`. Ergebnis war keine Ausnahme, sondern eine Antwort ohne die
    # Quoten -- also ohne genau die Jugendarbeitslosigkeit, die der `hinweis`
    # als einzigen Weg zu dieser Zahl ausweist.
    felder_zweite: tuple[str, ...] = field(default=())

    @property
    def portal_url(self) -> str:
        return f"https://opendata.swiss/de/dataset/{self.slug}"


# Vollstaendig: fuer jeden anderen Kanton gibt es keine maschinenlesbare Reihe.
# Geprueft am 2026-08-15 ueber den Gesamtbestand von opendata.swiss, in vier
# Sprachen und mit neun Suchbegriffen.
KANTONE: dict[str, KantonsReihe] = {
    "TG": KantonsReihe(
        kanton="TG",
        ckan_id="63525843-bf53-493c-95fe-dae411ef96dd",
        slug=(
            "arbeitslose-und-stellensuchende-pro-monat-nach-altersklasse-"
            "geschlecht-nationalitat-und-no-2015"
        ),
        herausgeber="Kanton Thurgau",
        granularitaet="monatlich",
        ab="2016-01",
        kennzahlen=("Registrierte Arbeitslose", "Registrierte Stellensuchende"),
        gebietsebene="Kanton",
        hinweis=(
            "Einzige der vier Reihen mit Altersklassen — deshalb die einzige, "
            "aus der sich Jugendarbeitslosigkeit als **Anzahl** ergibt."
        ),
        felder=("altersklasse", "geschlecht", "jahr", "monat", "metrik", "anzahl"),
    ),
    "FR": KantonsReihe(
        kanton="FR",
        ckan_id="2be419d8-0dc5-4881-8e93-963d5a5cc772",
        slug="arbeitslosigkeit-ab-2004",
        herausgeber="Amt für Statistik und Daten Freiburg",
        granularitaet="monatlich",
        ab="2004-01",
        kennzahlen=("chomeurs_en_tout", "demandeurs_demploi_inscrits", "taux_de_chomage"),
        gebietsebene="Kanton und Schweiz",
        hinweis=(
            "Führt neben dem Kanton eine Zeile `Suisse / Schweiz` mit — der "
            "einzige maschinenlesbare Weg zu **monatlichen Schweizer Zahlen**, "
            "den die Prüfung vom 2026-08-15 gefunden hat."
        ),
        # Die ueber CKAN verlinkte Ressource traegt **beschriftete** Spalten
        # ("Total chômeurs"), nicht die technischen Namen des Portals
        # ("chomeurs_en_tout"). Beide Formen existieren; gelesen wird die, auf
        # die die gepinnte Kennung zeigt. Der Schema-Check hat den Unterschied
        # beim ersten Lauf gemeldet, statt eine leere Reihe zu liefern.
        felder=(
            "Date",
            "Niveau géographique",
            "Total chômeurs",
            "Demandeurs d'emploi inscrits",
            "Taux de chômage en %",
        ),
    ),
    "ZG": KantonsReihe(
        kanton="ZG",
        ckan_id="c336a3e1-4b8a-4e3b-af19-0df3ffe60d99",
        slug="arbeitsmarktstatistik",
        herausgeber="Kanton Zug",
        granularitaet="monatlich",
        ab="1993-01",
        kennzahlen=("Arbeitslose", "Langzeitarbeitslose", "Jugendarbeitslosenquote"),
        gebietsebene="Kanton",
        hinweis=(
            "Zwei Datensätze: Anzahlen und Quoten getrennt. Die "
            "Jugendarbeitslosigkeit steht nur als **Quote** zur Verfügung, "
            "nicht als Anzahl."
        ),
        zweite_ckan_id="b396e748-14db-4aef-b2ff-66103709739e",
        zweiter_slug="arbeitslosenquote",
        trennzeichen=",",
        # Der Datensatz fuehrt **zwei** CSV-Ressourcen: die Reihe hier
        # (`jahr,monat,kennzahl,anzahl`) und eine zweite nach Altersgruppen
        # (`jahr,monat,altersgruppe,anzahl`), geprueft am 2026-08-29. Sie
        # unterscheiden sich in genau einer Spalte, und `felder` ist deshalb
        # nicht nur eine Pruefung, sondern das Merkmal, an dem der Server die
        # richtige der beiden auswaehlt.
        felder=("jahr", "monat", "kennzahl", "anzahl"),
        felder_zweite=("jahr", "monat", "kennzahl", "quote"),
    ),
    "ZH": KantonsReihe(
        kanton="ZH",
        ckan_id="f2b15a2d-8d3d-413d-8d0d-e21553e997e4",
        slug="arbeitslose-anz",
        herausgeber="Statistisches Amt Kanton Zürich",
        granularitaet="jaehrlich",
        ab="1991",
        kennzahlen=("Arbeitslose [Anz.]",),
        gebietsebene="Gemeinde",
        hinweis=(
            "Als einzige **jährlich** und nach Gemeinde — nicht monatlich. Eine "
            "Gemeindezahl beantwortet eine andere Frage als ein Kantonsmonat "
            "und wird deshalb auch anders beschriftet."
        ),
        trennzeichen=",",
        felder=("BFS_NR", "GEBIET_NAME", "INDIKATOR_JAHR", "INDIKATOR_VALUE"),
    ),
}

MONATSNAMEN = {
    "januar": 1,
    "februar": 2,
    "märz": 3,
    "maerz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}


def _lies_csv(payload: bytes, trennzeichen: str) -> list[dict[str, str]]:
    text = payload.decode("utf-8-sig", errors="replace")
    return [z for z in csv.DictReader(io.StringIO(text), delimiter=trennzeichen) if any(z.values())]


def spalten(payload: bytes, trennzeichen: str) -> list[str]:
    """Die Kopfzeile einer CSV-Antwort — auch wenn keine Datenzeile folgt.

    Ueber `fieldnames` und nicht ueber die erste gelesene Zeile: eine Datei mit
    Kopfzeile und ohne Daten hat keine erste Zeile, ist aber sehr wohl die
    richtige Datei. Wer beides vermengt, meldet «Spalten fehlen» fuer eine
    Quelle, die gerade nur nichts zu sagen hat.
    """
    text = payload.decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text), delimiter=trennzeichen).fieldnames or [])


def fehlende_felder(payload: bytes, trennzeichen: str, felder: tuple[str, ...]) -> list[str]:
    """Welche erwarteten Spalten diese Antwort nicht fuehrt — leer heisst: passt.

    Der Server waehlt damit unter mehreren CSV-Ressourcen eines Datensatzes
    aus, statt die erste zu nehmen. Gepinnt ist dafuer nichts Zusaetzliches:
    geprueft wird dieselbe Spaltenliste, die der Adapter ohnehin braucht.
    """
    vorhanden = set(spalten(payload, trennzeichen))
    return [f for f in felder if f not in vorhanden]


def _pflichtspalten(zeilen: list[dict[str, str]], felder: tuple[str, ...], was: str) -> None:
    """Meldet ein geaendertes Schema, statt eine leere Reihe zu liefern.

    Ohne diese Pruefung liefe ein umbenanntes Feld auf `.get()` ins Leere und
    das Werkzeug antwortete mit null Treffern — nicht zu unterscheiden von
    «dieser Monat hat keine Daten».
    """
    if not zeilen:
        raise KantonsReiheNichtLesbarError(f"{was}: die Antwort enthaelt keine Zeilen")
    vorhanden = set(zeilen[0])
    fehlend = [f for f in felder if f not in vorhanden]
    if fehlend:
        raise KantonsReiheNichtLesbarError(
            f"{was}: Spalten fehlen: {fehlend}. Vorhanden: {sorted(vorhanden)}"
        )


def _pflichtfelder(zeilen: list[dict[str, str]], reihe: KantonsReihe) -> None:
    """Die Pflichtspalten der Hauptreihe eines Kantons."""
    _pflichtspalten(zeilen, reihe.felder, reihe.kanton)


def _zahl(wert: str) -> float | None:
    wert = (wert or "").strip().replace("'", "").replace("’", "")
    if not wert:
        return None
    try:
        return float(wert)
    except ValueError:
        return None


def parse_tg(payload: bytes, reihe: KantonsReihe) -> dict[str, Any]:
    """Thurgau: eine Zeile je Merkmalskombination, Wert in ``anzahl``.

    Aggregiert ueber Geschlecht, Nationalitaet und NOGA-Sektor — die Quelle
    fuehrt jede Kombination einzeln, und die Summe ueber alle ist der
    Kantonswert. Altersklasse bleibt erhalten, weil sie die Frage nach den
    Jugendlichen beantwortet.
    """
    zeilen = _lies_csv(payload, reihe.trennzeichen)
    _pflichtfelder(zeilen, reihe)
    punkte: dict[str, dict[str, dict[str, float]]] = {}
    for z in zeilen:
        wert = _zahl(z.get("anzahl", ""))
        if wert is None:
            continue
        try:
            periode = f"{int(z['jahr']):04d}-{int(z['monat']):02d}"
        except (ValueError, KeyError):
            continue
        alter = z.get("altersklasse") or "alle"
        kennzahl = z.get("metrik") or ""
        punkte.setdefault(periode, {}).setdefault(alter, {}).setdefault(kennzahl, 0.0)
        punkte[periode][alter][kennzahl] += wert
    if not punkte:
        raise KantonsReiheNichtLesbarError("TG: keine auswertbaren Zeilen")
    return {"kanton": "TG", "granularitaet": "monatlich", "nach_alter": punkte}


def parse_fr(payload: bytes, reihe: KantonsReihe) -> dict[str, Any]:
    """Freiburg: eine Zeile je Monat und Gebiet, Werte in eigenen Spalten."""
    zeilen = _lies_csv(payload, reihe.trennzeichen)
    _pflichtfelder(zeilen, reihe)
    punkte: dict[str, dict[str, dict[str, float | None]]] = {}
    for z in zeilen:
        periode = (z.get("Date") or "").strip()
        gebiet = "CH" if "Suisse" in (z.get("Niveau géographique") or "") else "FR"
        if not periode:
            continue
        punkte.setdefault(periode, {})[gebiet] = {
            "arbeitslose": _zahl(z.get("Total chômeurs", "")),
            "stellensuchende": _zahl(z.get("Demandeurs d'emploi inscrits", "")),
            "quote": _zahl(z.get("Taux de chômage en %", "")),
        }
    if not punkte:
        raise KantonsReiheNichtLesbarError("FR: keine auswertbaren Zeilen")
    return {"kanton": "FR", "granularitaet": "monatlich", "nach_gebiet": punkte}


def parse_zg(payload: bytes, reihe: KantonsReihe, quoten: bytes | None = None) -> dict[str, Any]:
    """Zug: Anzahlen und Quoten in zwei Dateien, Monat als deutscher Name."""
    zeilen = _lies_csv(payload, reihe.trennzeichen)
    _pflichtfelder(zeilen, reihe)
    punkte: dict[str, dict[str, float]] = {}

    def periode_von(z: dict[str, str]) -> str | None:
        monat = MONATSNAMEN.get((z.get("monat") or "").strip().lower())
        try:
            jahr = int(z["jahr"])
        except (ValueError, KeyError):
            return None
        return f"{jahr:04d}-{monat:02d}" if monat else None

    for z in zeilen:
        periode = periode_von(z)
        wert = _zahl(z.get("anzahl", ""))
        if periode and wert is not None:
            punkte.setdefault(periode, {})[z.get("kennzahl", "")] = wert
    if quoten:
        quotenzeilen = _lies_csv(quoten, reihe.trennzeichen)
        # Bis zum 2026-08-29 stand hier keine Pruefung. Eine umbenannte
        # `quote`-Spalte lieferte dann fuer jede Zeile `None`, keine Ausnahme
        # und eine Antwort ohne beide Quoten -- die Anzahlen aus der ersten
        # Datei standen ja noch da. Still unvollstaendig ist schlimmer als laut
        # kaputt, und die Jugendarbeitslosigkeit gibt es hier nur als Quote.
        _pflichtspalten(quotenzeilen, reihe.felder_zweite, f"{reihe.kanton} (Quoten)")
        for z in quotenzeilen:
            periode = periode_von(z)
            wert = _zahl(z.get("quote", ""))
            if periode and wert is not None:
                punkte.setdefault(periode, {})[z.get("kennzahl", "")] = wert
    if not punkte:
        raise KantonsReiheNichtLesbarError("ZG: keine auswertbaren Zeilen")
    return {"kanton": "ZG", "granularitaet": "monatlich", "nach_periode": punkte}


def parse_zh(payload: bytes, reihe: KantonsReihe) -> dict[str, Any]:
    """Zuerich: Jahreswerte — die einzige nicht-monatliche Reihe.

    **Gemeinden und Aggregate stehen in derselben Spalte.** «Zürich - ganzer
    Kanton», «Bezirk Horgen» und «Region Glattal» sehen in `GEBIET_NAME` aus
    wie Gemeinden; eine nach Groesse sortierte Liste stellt dann den
    Kantonswert an die Spitze der «groessten Gemeinden». Unterschieden werden
    sie an `BFS_NR`: Aggregate tragen 0, Gemeinden ihre echte Nummer.

    Der Adapter trennt beides und liefert `nach_gemeinde` und `aggregate` —
    wer sie mischt, vergleicht einen Kanton mit einer Gemeinde.
    """
    zeilen = _lies_csv(payload, reihe.trennzeichen)
    _pflichtfelder(zeilen, reihe)
    gemeinden: dict[str, dict[str, float]] = {}
    aggregate: dict[str, dict[str, float]] = {}
    for z in zeilen:
        wert = _zahl(z.get("INDIKATOR_VALUE", ""))
        jahr = (z.get("INDIKATOR_JAHR") or "").strip()
        gebiet = (z.get("GEBIET_NAME") or "").strip()
        if wert is None or not jahr or not gebiet:
            continue
        ziel = aggregate if (z.get("BFS_NR") or "").strip() in {"", "0"} else gemeinden
        ziel.setdefault(jahr, {})[gebiet] = wert
    if not gemeinden:
        raise KantonsReiheNichtLesbarError("ZH: keine auswertbaren Gemeindezeilen")
    return {
        "kanton": "ZH",
        "granularitaet": "jaehrlich",
        "nach_gemeinde": gemeinden,
        "aggregate": aggregate,
    }


PARSER = {"TG": parse_tg, "FR": parse_fr, "ZG": parse_zg, "ZH": parse_zh}


def herkunftszeile(reihe: KantonsReihe) -> str:
    return (
        f"Datenquelle: SECO (RAV-Register), veröffentlicht durch "
        f"{reihe.herausgeber} ({reihe.portal_url})"
    )
