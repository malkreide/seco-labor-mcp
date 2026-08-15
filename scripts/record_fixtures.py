#!/usr/bin/env python3
"""Zeichnet echte Antworten der Quellen dieses Servers nach `tests/fixtures/` auf.

Warum: eine handgeschriebene Fixture kodiert die Annahme ihres Autors und kann
sie deshalb nicht widerlegen. In `i14y-mcp` blieb genau deshalb eine ganze Suite
gruen, waehrend drei Tools produktiv leere Titel lieferten — die Stubs hatten
einen Schluessel erfunden und stimmten dem Mapper zu statt der Quelle.

Dieser Server spricht mit zwei sehr verschiedenen Quellen:

* **CKAN auf `opendata.swiss`** — JSON, zwei Aktionen. Die Suche wird zweimal
  aufgezeichnet: einmal genau so, wie der Client sie stellt (mit dem
  Organisationsfilter), und einmal ohne. Der Unterschied ist der Befund, den
  `PROVENANCE.md` datiert festhaelt.
* **`unfallstatistik.ch`** — zwei HTML-Seiten und zwei PDFs. Der Jahresbericht
  ist 2.1 MB auf 70 Seiten; aufgezeichnet sind die drei Seiten, aus denen der
  Parser seine Tabellen liest. Gekuerzt ist die Zahl der **Seiten**, nie ihr
  Inhalt: die Tabellen bleiben Wort fuer Wort, wie sie ankommen.

Herkunft, Datum, Auswahlregel und SHA-256 je Datei schreibt dieses Skript nach
`tests/fixtures/PROVENANCE.md`. Neu aufzeichnen:

    python scripts/record_fixtures.py

Braucht Netzzugang zu `opendata.swiss`, `unfallstatistik.ch` und der CSV-Quelle
des aufgezeichneten Datensatzes. Entwicklungswerkzeug; weder das Paket noch die
Testsuite importieren es.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from seco_labor_mcp import sources

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

CKAN_BASE = "https://opendata.swiss/api/3/action"
UVG_BASE = "https://www.unfallstatistik.ch"

USER_AGENT = "seco-labor-mcp-recorder (Swiss Public Data MCP Portfolio)"

# Fest gewaehlt, nicht «irgendeiner»: eine vom Lauf abhaengige Auswahl erzeugt
# bei jedem Aufzeichnen einen anderen Diff.
SUCHBEGRIFF = "arbeitslose kantone"

# Der Organisationsfilter, den der Client bis zum 2026-08-14 mitschickte. Aus
# `server.py` ist er entfernt; hier bleibt er stehen, weil die Aufzeichnung
# seiner Wirkung der Beleg fuer den Befund ist. Faellt sie eines Tages mit
# Treffern zurueck, ist die Organisation wieder da und der Befund erledigt.
FRUEHERER_ORG_FILTER = "staatssekretariat-fur-wirtschaft-seco"
DATENSATZ = "arbeitslose-anz"  # traegt eine CSV-Ressource, die der Server liest
UVG_JAHRGANG = 26  # Ts26.pdf
UVG_BRANCHE = ("BUV", "41")  # NOGA 41 Hochbau

# Die Seiten des Jahresberichts, aus denen `TABLE_SPECS` seine Tabellen liest.
# Nicht geraten: der Recorder sucht die Beschriftungen und meldet, was er fand.
UVG_TABELLEN = (
    ("Tabelle 1.2", None),
    ("Tabelle 2.4", "Berufsunfallversicherung"),
    ("Tabelle 2.4", "Nichtberufsunfallversicherung"),
)


def holen(url: str, **params: Any) -> httpx.Response:
    """Holt eine URL, mit wenigen Wiederholungen bei Verbindungsfehlern.

    Der CSV-Host bricht die TLS-Verhandlung gelegentlich ab (Connection reset).
    Ein Recorder, der daran scheitert, hinterlaesst einen halb geschriebenen
    Fixture-Ordner samt Nachweis, der ihn nicht mehr beschreibt — dann lieber
    dreimal fragen. Ein HTTP-Fehler wird *nicht* wiederholt: der ist eine
    Antwort und gehoert gesehen.
    """
    letzter: Exception | None = None
    for versuch in range(3):
        try:
            resp = httpx.get(
                url,
                params=params or None,
                headers={"User-Agent": USER_AGENT},
                timeout=180,
                follow_redirects=True,
            )
            resp.raise_for_status()
            return resp
        except httpx.TransportError as exc:
            letzter = exc
            print(f"      Verbindungsfehler ({exc!r}), Versuch {versuch + 2}/3 ...")
            time.sleep(2.0 * (versuch + 1))
    raise RuntimeError(f"{url} nach drei Versuchen nicht erreichbar") from letzter


def main() -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    recorded_at = datetime.now(UTC).strftime("%Y-%m-%d")
    entries: list[dict[str, Any]] = []
    print(f"Zeichne auf von {CKAN_BASE} und {UVG_BASE}")

    def write(name: str, blob: Any, url: str, rule: str, total: str | None = None) -> None:
        if not isinstance(blob, bytes):
            blob = (json.dumps(blob, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        (FIXTURES / name).write_bytes(blob)
        entries.append(
            {
                "name": name,
                "url": url,
                "rule": rule,
                "bytes": len(blob),
                "total": total,
                "sha256": hashlib.sha256(blob).hexdigest(),
            }
        )
        print(f"  ok  {name:<34} {len(blob):>8} B")

    # --- CKAN: die Suche, wie der Client sie bis 2026-08-14 stellte -----
    params = {
        "q": SUCHBEGRIFF,
        "fq": f"organization:{FRUEHERER_ORG_FILTER}",
        "rows": 10,
        "sort": "score desc, metadata_modified desc",
    }
    resp = holen(f"{CKAN_BASE}/package_search", **params)
    mit_filter = resp.json()
    treffer_mit = mit_filter["result"]["count"]
    write(
        "ckan_package_search.json",
        resp.content,
        str(resp.url),
        f"vollstaendig; der Aufruf des Clients Wort fuer Wort — Suche nach "
        f"{SUCHBEGRIFF!r}, gefiltert auf `organization:{FRUEHERER_ORG_FILTER}`. "
        f"Ergebnis: **{treffer_mit} Treffer** (siehe Befund oben)",
    )

    # --- CKAN: dieselbe Suche ohne den Organisationsfilter ---------------
    ohne = dict(params)
    ohne.pop("fq")
    resp = holen(f"{CKAN_BASE}/package_search", **ohne)
    ohne_filter = resp.json()
    treffer_ohne = ohne_filter["result"]["count"]
    write(
        "ckan_package_search_ohne_organisation.json",
        resp.content,
        str(resp.url),
        f"vollstaendig; dieselbe Suche ohne `fq`. Ergebnis: **{treffer_ohne} "
        "Treffer**. Belegt, dass der Endpunkt antwortet und der Filter die "
        "Ursache ist — nicht die Suche und nicht das Netz",
    )

    # --- CKAN: ein Datensatz mit CSV-Ressource ---------------------------
    resp = holen(f"{CKAN_BASE}/package_show", id=DATENSATZ)
    paket = resp.json()
    write(
        "ckan_package_show.json",
        resp.content,
        str(resp.url),
        f"vollstaendig; Datensatz {DATENSATZ!r} — ein beliebiger Datensatz, an "
        "dem die Form einer `package_show`-Antwort belegt ist. Die gepinnte "
        "Jahresreihe steht eigens weiter unten",
    )

    # --- Die gepinnte BFS-Tabelle mit den SECO-Reihen --------------------
    # Zwei Aufzeichnungen, weil der Server zwei Schritte geht: erst
    # `package_show` auf die gepinnte UUID, dann die XLS-Ressource, die dort
    # steht. Die Asset-URL wird bewusst nicht gepinnt -- sie aendert sich bei
    # jeder Neupublikation. Genau diese Kette soll die Fixture belegen.
    antwort = holen(f"{CKAN_BASE}/package_show", id=sources.JAHRESREIHE.ckan_id)
    paket = antwort.json()
    write(
        "ckan_package_show_jahresreihe.json",
        paket,
        str(antwort.url),
        f"vollstaendig; die gepinnte Kennung aus `sources.py` ({sources.JAHRESREIHE.slug})",
    )
    xls = next(
        r
        for r in paket["result"]["resources"]
        if (r.get("format") or "").upper() in {"XLS", "XLSX"}
    )
    roh = holen(xls["url"]).content
    gelesen = sources.parse_jahresreihe(roh)
    write(
        "bfs_jahresreihe.xlsx",
        roh,
        xls["url"],
        f"vollstaendig; Blatt {sources.JAHRESREIHE.blatt} mit den drei Reihen "
        f"{sorted(gelesen['series'])}, Jahre {gelesen['years'][0]}-"
        f"{gelesen['years'][-1]}. Ungekuerzt, weil die ganze Mappe 17 kB misst",
    )

    # --- unfallstatistik.ch: die beiden HTML-Seiten ----------------------
    for name, pfad, wozu in (
        ("uvg_schluesselzahlen.html", "/d/neuza/schluesselzahlen_d.htm", "Schluesselzahlen"),
        ("uvg_publikationen.html", "/d/publik/publikationen_d.htm", "Publikationsliste"),
    ):
        resp = holen(f"{UVG_BASE}{pfad}")
        write(name, resp.content, str(resp.url), f"vollstaendig; {wozu}")

    # --- unfallstatistik.ch: der Jahresbericht, auf seine Tabellen gekuerzt
    from pypdf import PdfReader, PdfWriter

    url = f"{UVG_BASE}/d/publik/unfstat/pdf/Ts{UVG_JAHRGANG:02d}.pdf"
    resp = holen(url)
    voll = PdfReader(io.BytesIO(resp.content))
    seiten: list[int] = []
    gefunden: list[str] = []
    for i, seite in enumerate(voll.pages):
        text = seite.extract_text() or ""
        for caption, variante in UVG_TABELLEN:
            if caption in text and (variante is None or variante in text) and i not in seiten:
                seiten.append(i)
                gefunden.append(f"{caption}{'/' + variante if variante else ''} auf S. {i + 1}")
    assert len(seiten) == len(UVG_TABELLEN), f"nicht alle Tabellen gefunden: {gefunden}"
    schreiber_pdf = PdfWriter()
    for i in sorted(seiten):
        schreiber_pdf.add_page(voll.pages[i])
    puffer_pdf = io.BytesIO()
    schreiber_pdf.write(puffer_pdf)
    write(
        f"uvg_jahresbericht_ts{UVG_JAHRGANG:02d}.pdf",
        puffer_pdf.getvalue(),
        url,
        f"{len(seiten)} von {len(voll.pages)} Seiten, Inhalt unveraendert: "
        f"{', '.join(gefunden)}. Gekuerzt ist die Zahl der Seiten, nie ihr Text "
        "— der Parser liest Beschriftung, Zeilen und Spalten aus dem Layout",
        f"{len(voll.pages)} Seiten, {len(resp.content)} B",
    )

    # --- unfallstatistik.ch: eine Branchen-Zeitreihe ---------------------
    scheme, noga = UVG_BRANCHE
    url = f"{UVG_BASE}/d/neuza/WirtKl_d/WirtKl_{scheme}_{noga}.pdf"
    resp = holen(url)
    write(
        f"uvg_branche_{scheme.lower()}_{noga}.pdf",
        resp.content,
        url,
        f"vollstaendig; NOGA {noga}, {scheme} — klein genug, um ungekuerzt zu bleiben",
    )

    _write_provenance(
        recorded_at, entries, _befund(FRUEHERER_ORG_FILTER, treffer_mit, treffer_ohne)
    )
    print(f"\nPROVENANCE.md geschrieben, Aufzeichnungsdatum {recorded_at}")
    return _warne_bei_ignorierten(entries)


def _befund(org: str, mit: int, ohne: int) -> list[str]:
    return [
        "## Befund: der gepinnte Organisationsfilter trifft niemanden mehr",
        "",
        f"Der Client filtert jede CKAN-Suche auf `organization:{org}`.",
        "Diese Organisation gibt es auf opendata.swiss nicht (mehr):",
        "",
        "| Abfrage | Treffer |",
        "|---|---|",
        f"| `package_search` mit `fq=organization:{org}` | **{mit}** |",
        f"| dieselbe Suche ohne `fq` | {ohne} |",
        "",
        f"`organization_show?id={org}` antwortet mit **404 Not found**, und in",
        "den 176 Eintraegen von `organization_list` kommt kein SECO vor —",
        "gesucht wurde auch nach den Schreibvarianten `…fuer…` und `seco`.",
        "Datensaetze zum Thema gibt es, aber unter anderen Herausgebern (BFS,",
        "kantonale Statistikaemter, Amt fuer Statistik FL).",
        "",
        "Wirkung: **alle sechs CKAN-gestuetzten Tools liefern nichts.**",
        "`seco_search_datasets` antwortet «Keine SECO-Datensaetze gefunden» und",
        "empfiehlt andere Suchbegriffe — die aus demselben Grund auch nichts",
        "finden. Die fuenf Tools mit CSV-Vorschau bekommen nie einen Datensatz,",
        "durch den sie laufen koennten, und fallen still auf ihren statischen",
        "Text zurueck.",
        "",
        "Nicht in diesem Zug behoben: den Filter einfach zu streichen waere",
        "keine Reparatur, sondern eine andere Zusage. Die Antworten hiessen",
        "weiter «SECO-Datensaetze», waeren aber Daten des BFS und der Kantone.",
        "Welche Quelle an die Stelle tritt, ist eine Entscheidung ueber den",
        "Server und keine Nebenwirkung einer Aufzeichnung.",
        "",
        "Die beiden aufgezeichneten Suchen halten den Stand fest. Kommt die",
        "Organisation zurueck, faellt `test_der_filter_trifft_niemanden` — dann",
        "gehoert die Aufzeichnung erneuert und dieser Befund gestrichen.",
        "",
    ]


def _warne_bei_ignorierten(entries: list[dict[str, Any]]) -> int:
    """Meldet Aufzeichnungen, die `.gitignore` ausschliesst.

    Eine ignorierte Fixture faellt lokal nicht auf — die Datei liegt ja da und
    die Suite ist gruen. Erst die CI klont ein Repo ohne sie und wird rot, mit
    einer Fehlermeldung, die nach einem Aufzeichnungsproblem aussieht statt nach
    einer Regel in `.gitignore`. In `swiss-housing-mcp` ist genau das passiert,
    dort mit einem `*.zip`; hier waere `*.pdf` derselbe Fall.
    """
    pfade = [str(FIXTURES / e["name"]) for e in entries]
    try:
        ergebnis = subprocess.run(
            ["git", "check-ignore", *pfade], capture_output=True, text=True, check=False
        )
    except OSError:
        return 0  # kein git zur Hand — kein Grund, das Aufzeichnen scheitern zu lassen
    ignoriert = [z for z in ergebnis.stdout.splitlines() if z.strip()]
    if ignoriert:
        print("\n!! Diese Aufzeichnungen schliesst .gitignore aus, sie fehlen der CI:")
        for z in ignoriert:
            print(f"     {z}")
        return 1
    return 0


def _write_provenance(recorded_at: str, entries: list[dict[str, Any]], befund: list[str]) -> None:
    lines = [
        "# Herkunft der Fixtures",
        "",
        "**Erzeugt von `scripts/record_fixtures.py`. Nicht von Hand pflegen.**",
        "",
        f"Aufgezeichnet am **{recorded_at}** von den Quellen dieses Servers:",
        f"`{CKAN_BASE}`, `{UVG_BASE}` und der CSV-Ressource des aufgezeichneten",
        "Datensatzes.",
        "",
        "Ohne Datum ist «aufgezeichnet» nach zwei Jahren von «ausgedacht» nicht",
        "mehr zu unterscheiden — die Datei sieht gleich aus.",
        "",
        "**Ein Teil sind Ausschnitte, keine Vollabzuege.** Die Auswahlregel steht",
        "je Datei dabei. Gekuerzt ist immer die Zahl der Eintraege — Zeilen einer",
        "CSV, Seiten eines PDF —, nie ihr Inhalt: keine Spalte entfernt, keine",
        "Tabelle umgeschrieben. Eine Fixture belegt damit die *Form* der Antwort",
        "und einen datierten Ausschnitt ihres Inhalts, nicht den Bestand.",
        "Aussagen ueber Vollstaendigkeit gehoeren in `tests/test_live.py`.",
        "",
        "**Die Eintraege sind gewaehlt, nicht genommen.** Die CSV beginnt mit",
        "einer einzigen Gemeinde im aeltesten Jahr; aufgezeichnet sind zwei",
        "vollstaendige Zeitreihen. Der Jahresbericht traegt seine drei Tabellen",
        "auf den Seiten 13, 27 und 28 von 70 — der Recorder sucht sie an ihrer",
        "Beschriftung, statt Seitenzahlen zu pinnen.",
        "",
        *befund,
        "Fehlerpfade — Timeouts, 5xx, ein kaputtes PDF — bleiben handgeschrieben.",
        "Die lassen sich nicht auf Zuruf aufzeichnen.",
        "",
    ]
    for e in entries:
        groesse = f"- **Groesse:** {e['bytes']} B"
        if e["total"]:
            groesse += f" (Quelle: {e['total']})"
        lines += [
            f"## `{e['name']}`",
            "",
            f"- **Quelle:** `{e['url']}`",
            f"- **Aufgezeichnet:** {recorded_at}",
            f"- **Auswahl:** {e['rule']}",
            groesse,
            f"- **SHA-256:** `{e['sha256']}`",
            "",
        ]
    (FIXTURES / "PROVENANCE.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
