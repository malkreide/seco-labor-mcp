"""
Unfallstatistik UVG (SSUV) — Loader, Parser und Tool-Implementationen
=====================================================================

Berufsunfall- und Berufskrankheitsstatistiken der Sammelstelle für die Statistik
der Unfallversicherung UVG (SSUV), Geschäftsstelle c/o Suva, Luzern.

Architektur C (dump-first). Begründung und vollständige Live-Probe:
siehe ``PROBE_REPORT_UVG.md`` im Repo-Root.

Die Quelle hat **keine API**. Ein Link-Scan über sämtliche Datenseiten (Probe vom
2026-08-05) ergab 165 PDFs und null Dateien mit ``.csv``, ``.xlsx`` oder ``.json``.
Verwertbar sind genau drei Zugänge:

  1. ``schluesselzahlen_d.htm``  — echte HTML-Tabelle, 5 Jahre, Gesamtschweiz
  2. ``Ts{YY}.pdf``              — Jahresausgabe, 70 S., Tabellen 1.2 und 2.4 nach NOGA
  3. ``WirtKl_{BUV|NBUV}_{NN}.pdf`` — 10-Jahres-Zeitreihe je NOGA-Wirtschaftsabteilung

Nutzungsrechte: Der Code dieses Servers steht unter MIT. Die **Daten** nicht — die
SSUV erlaubt «Abdruck ausser für kommerzielle Nutzung mit Quellenangabe». Diese
Einschränkung ist nicht unsere, sie lässt sich nicht per Repo-Lizenz aufheben, und
sie wird deshalb in jedem Envelope mitgeliefert (``UVG_ATTRIBUTION``).
"""

from __future__ import annotations

import asyncio
import html as _html
import re
import time
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any
from urllib.parse import urlsplit

import httpx

from . import retry_policy

# ---------------------------------------------------------------------------
# Endpunkte
# ---------------------------------------------------------------------------

UVG_BASE = "https://www.unfallstatistik.ch"
UVG_KEY_FIGURES_URL = f"{UVG_BASE}/d/neuza/schluesselzahlen_d.htm"
UVG_ANNUAL_PDF_URL = UVG_BASE + "/d/publik/unfstat/pdf/Ts{yy:02d}.pdf"
UVG_BRANCH_PDF_URL = UVG_BASE + "/d/neuza/WirtKl_d/WirtKl_{scheme}_{noga}.pdf"
UVG_PUBLICATIONS_URL = f"{UVG_BASE}/d/publik/publikationen_d.htm"

# Erste Ausgabe der PDF-Serie: Ts00.pdf. Live geprüft: Ts10.pdf liegt seit
# 2010-06-30 unverändert online — 16 Jahre stabile Archiv-URLs.
UVG_FIRST_EDITION_YY = 0

# ---------------------------------------------------------------------------
# Attribution — gehört nach Portfolio-Regel in JEDE Response, nicht ins README
# ---------------------------------------------------------------------------

UVG_SOURCE_NAME = (
    "Unfallstatistik UVG, Hrsg. Koordinationsgruppe für die Statistik der "
    "Unfallversicherung (KSUV), Sammelstelle SSUV c/o Suva, Luzern — unfallstatistik.ch"
)

UVG_LICENCE_NOTE = (
    "Nutzungsbedingungen der Quelle: «Abdruck – ausser für kommerzielle Nutzung – "
    "mit Quellenangabe gestattet.» Das ist keine offene Lizenz. Die Einschränkung "
    "betrifft die Daten und gilt unabhängig von der MIT-Lizenz dieses Servers."
)


def uvg_attribution(edition: str | None = None) -> str:
    """Vollständige Quellenangabe inklusive Nicht-kommerziell-Hinweis."""
    name = f"{UVG_SOURCE_NAME} ({edition})" if edition else UVG_SOURCE_NAME
    return f"{name}. {UVG_LICENCE_NOTE}"


# ---------------------------------------------------------------------------
# HTTP: Retry mit exponentiellem Backoff
# ---------------------------------------------------------------------------

# Portfolio-Standard 2s/4s/8s. Anders als die CSV-Helfer in server.py, die
# einen einzigen GET absetzen, retryt dieser Pfad — die Quelle liefert PDFs
# von 2 MB, und genau die sind es, die bei Lastspitzen mit 5xx abbrechen.
UVG_BACKOFF_SECONDS = (2.0, 4.0, 8.0)

UVG_CACHE_TTL = timedelta(hours=24)
# Eine jährlich aktualisierte Quelle braucht keine kurze TTL. 24 h ist bereits
# grosszügig kurz; die Obergrenze schützt nur gegen unbegrenztes Wachstum.
UVG_CACHE_MAX = 24

# url -> (fetched_at, payload, last_modified)
_UVG_CACHE: OrderedDict[str, tuple[datetime, bytes, str | None]] = OrderedDict()


class UvgSourceUnavailableError(RuntimeError):
    """Quelle nach allen Retries nicht erreichbar und kein Cache vorhanden."""


def _cache_put(url: str, payload: bytes, last_modified: str | None) -> None:
    _UVG_CACHE[url] = (datetime.now(UTC), payload, last_modified)
    while len(_UVG_CACHE) > UVG_CACHE_MAX:
        _UVG_CACHE.popitem(last=False)


def uvg_cache_clear() -> None:
    """Cache leeren (Tests, sowie manueller Refresh)."""
    _UVG_CACHE.clear()


async def _fetch_bytes(url: str, *, allow_404: bool = False) -> tuple[bytes, str | None, str]:
    """Lade ``url`` mit Retry 2s/4s/8s.

    Rückgabe: ``(payload, last_modified_header, provenance)``.
    ``provenance`` ist ``"live"`` bei frischem Abruf, ``"cached"`` aus dem Cache.

    4xx werden — ausser 429 — nie wiederholt: Ein 404 auf ``Ts27.pdf`` ist eine
    Antwort, kein Ausfall, und die Erkennung der aktuellen Ausgabe verlässt sich
    genau darauf (siehe ``resolve_latest_edition``).
    """
    # Lokale Importe: server.py importiert dieses Modul, deshalb dürfen wir
    # server.py nicht auf Modulebene importieren. Zur Aufrufzeit ist es geladen.
    from .server import _client_scope, _validate_external_url

    now = datetime.now(UTC)
    cached = _UVG_CACHE.get(url)
    if cached and now - cached[0] < UVG_CACHE_TTL:
        return cached[1], cached[2], "cached"

    await _validate_external_url(url)

    last_error: Exception | None = None
    deadline = time.monotonic() + retry_policy.RETRY_TOTAL_BUDGET
    attempts = 0

    for attempt in range(len(UVG_BACKOFF_SECONDS) + 1):
        if attempt:
            delay = retry_policy.compute_delay(attempt, last_error)
            # Eine Wartezeit, die das Budget überdauert, wartet für niemanden:
            # Der Aufrufende hat aufgegeben, bevor sie endet. Dann lieber Schluss.
            if delay >= deadline - time.monotonic():
                break
            await asyncio.sleep(delay)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        attempts += 1
        try:
            async with _client_scope() as client:
                # httpx begrenzt pro Operation, und sein Read-Timeout beginnt
                # mit jedem Chunk von vorn — ein tröpfelndes PDF überdauert
                # jede Einzelschranke, ohne dass ein Read abläuft.
                # `asyncio.timeout` ist die Wanduhr, die das Budget zusagt.
                async with asyncio.timeout(remaining):
                    resp = await client.get(url)
                    if resp.status_code == 404 and allow_404:
                        raise FileNotFoundError(url)
                    resp.raise_for_status()
                    payload = resp.content
                last_modified = resp.headers.get("last-modified")
                _cache_put(url, payload, last_modified)
                return payload, last_modified, "live"
        except FileNotFoundError:
            raise
        except TimeoutError as exc:  # Budget weg, nicht bloss dieser Versuch
            last_error = exc
            break
        except httpx.HTTPStatusError as exc:
            last_error = exc
            code = exc.response.status_code
            if 400 <= code < 500 and code != 429:
                break
        except httpx.RequestError as exc:
            last_error = exc

    # Abgelaufener Cache ist besser als nichts — das ist der degraded-Pfad.
    if cached:
        return cached[1], cached[2], "cached"
    # Typ und Host statt nur `str(last_error)`: httpx.ConnectTimeout,
    # ReadTimeout und ConnectError tragen ein LEERES str() und sind genau die
    # Fehler, die ein echter Ausfall produziert. Die Meldung endete deshalb nach
    # dem Doppelpunkt und nannte weder Fehlerart noch Host. Wer wrappt, muss den
    # Typ nennen.
    host = urlsplit(url).hostname
    if last_error is None:
        raise UvgSourceUnavailableError(
            f"{url}: kein Versuch unternommen, das Budget von "
            f"{retry_policy.RETRY_TOTAL_BUDGET:g}s war schon aufgebraucht (host={host})"
        )
    grund = (
        f"alle {len(UVG_BACKOFF_SECONDS) + 1} Versuche verbraucht"
        if attempts >= len(UVG_BACKOFF_SECONDS) + 1
        else f"Budget von {retry_policy.RETRY_TOTAL_BUDGET:g}s nach {attempts} aufgebraucht"
    )
    detail = str(last_error) or "keine weitere Angabe"
    raise UvgSourceUnavailableError(
        f"{url} nach {attempts} Versuch(en) — {grund}: "
        f"{type(last_error).__name__}: {detail} (host={host})"
    ) from last_error


# ---------------------------------------------------------------------------
# Zahlen-Parsing
# ---------------------------------------------------------------------------
#
# Fundstück aus der Live-Probe: Die Quelle nutzt ZWEI unvereinbare Zahlenformate.
#
#   Jahresausgabe Ts{YY}.pdf : "1 097 154" und "137,5"   (U+0020 / Komma)
#   Branchen-PDF WirtKl_*.pdf: "1'057"     und "4.25"    (Apostroph / Punkt)
#
# Der Leerzeichen-Trenner ist der gefährliche Fall: Er ist dasselbe Zeichen, das
# auch Spalten trennt. Ein split() zersägt "1 097 154" in drei Zahlen und liefert
# trotzdem plausible Integers — ein Parser, der nicht abstürzt, sondern lügt.
# Aus dem Text allein ist die Zerlegung nicht rekonstruierbar: "166 534 234" ist
# als 166534234 genauso gültig wie als 166 534 | 234. Deshalb kommen die Zahlen
# der Jahrestabellen aus dem Layout-Modus, wo die Spaltenabstände des Satzes
# erhalten sind (siehe _COLUMN_GAP und _merge_layout_rows).

_SIGNIFICANT_RE = re.compile(r"\*")


def parse_number(token: str) -> tuple[float | int | None, bool]:
    """Zerlege einen Zahlwert in ``(wert, signifikant)``.

    Der Stern markiert laut ``Beschrieb_Branchen_d.pdf`` S. 5 eine *statistisch
    signifikante* Veränderung gegenüber dem Vorjahr. Ihn beim Parsen wegzuwerfen
    wäre Informationsverlust genau dort, wo ein Modell sonst «Anstieg» sagt, wo
    «nicht signifikanter Anstieg» richtig wäre. Er wird deshalb als eigenes
    Flag erhalten statt stillschweigend entfernt.
    """
    raw = (token or "").strip()
    if not raw:
        return None, False
    significant = bool(_SIGNIFICANT_RE.search(raw))
    cleaned = raw.replace("*", "").replace("%", "").strip()
    # Tausendertrenner beider Schreibweisen entfernen …
    cleaned = cleaned.replace("’", "").replace("'", "").replace(" ", "").replace(" ", "")
    # … und Komma-Dezimaltrenner auf Punkt normalisieren.
    if "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    if cleaned in {"", "-", "–", "."}:
        return None, significant
    try:
        value = float(cleaned)
    except ValueError:
        return None, significant
    if value.is_integer() and "." not in cleaned:
        return int(value), significant
    return value, significant


# Spaltengrenze im Layout-Modus. Empirisch bestimmt, nicht geraten: Auf den
# Tabellenseiten 13 und 27 der Ausgabe 2026 reichen Lücken innerhalb von Zahlen
# und Labels bis 10 Leerzeichen, die kleinste Lücke ZWISCHEN zwei Spalten misst
# 113. Der Schwellwert liegt im leeren Band dazwischen.
_COLUMN_GAP = re.compile(r" {20,}")

# Textmodus zerlegt "261 446" nicht eindeutig — als Tausendertrenner steht dort
# dasselbe Zeichen wie zwischen den Spalten, und «261 446 573» ist als 261446573
# genauso lesbar wie als 261 446 | 573. Der Layout-Modus setzt stattdessen die
# Spaltenabstände des Satzes um; damit ist die Zerlegung eindeutig. Preis dafür:
# er streut Leerzeichen in Wörter ("Sek tor", "Forstwir tschaf t"). Zahlen kommen
# deshalb aus dem Layout-Modus, Beschriftungen aus dem Textmodus.


def _layout_cells(line: str) -> list[str]:
    return [c.strip() for c in _COLUMN_GAP.split(line.strip()) if c.strip()]


_DIGIT_ONLY = re.compile(r"^[\d\s]+$")
_CODE_RE = re.compile(r"^\s*(?P<code>I{1,3}|\d{2}(?:\s*[,–—-]\s*\d{2})*)(?=\s|$)")


def _row_key(label: str) -> str:
    """Verbindungsschlüssel zwischen Layout- und Textmodus.

    Der NOGA-Code beziehungsweise das Schlüsselwort steht am Zeilenanfang und
    übersteht beide Extraktionen unbeschadet — anders als der Fliesstext.
    """
    collapsed = re.sub(r"\s+", " ", label).strip()
    m = _CODE_RE.match(collapsed)
    if m:
        return re.sub(r"\s*[,–—-]\s*", "-", m.group("code")).replace(" ", "")
    return collapsed.split()[0].lower() if collapsed else ""


# ---------------------------------------------------------------------------
# PDF-Text
# ---------------------------------------------------------------------------


def _pdf_pages(payload: bytes, *, layout: bool = False) -> list[str]:
    """Seitenweise Textextraktion. Import lokal, damit ein fehlendes pypdf
    nur die UVG-Tools trifft und nicht den Serverstart."""
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(payload))
    if layout:
        return [(page.extract_text(extraction_mode="layout") or "") for page in reader.pages]
    return [(page.extract_text() or "") for page in reader.pages]


def _pdf_metadata(payload: bytes) -> dict[str, str]:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(payload))
    meta = reader.metadata or {}
    return {str(k).lstrip("/"): str(v) for k, v in meta.items()}


def _pdf_date(raw: str | None) -> str | None:
    """PDF-Datum ``D:20260609104131+02'00'`` -> ``2026-06-09``."""
    if not raw:
        return None
    m = re.search(r"(\d{4})(\d{2})(\d{2})", raw)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def _append_label(head: str, tail: str) -> str:
    """Setze eine umgebrochene Beschriftung zusammen.

    Endet der Kopf auf einen Trennstrich, ist es Silbentrennung und die Teile
    werden direkt verklebt (``"… Dienst-" + "leistungen"``); sonst mit Leerzeichen.
    """
    head = head.rstrip()
    if head.endswith("-"):
        # Der Trennstrich steht mal direkt am Wort ("Tabakerzeug-"), mal durch
        # Blocksatz abgesetzt ("verbunde       -"). Beides muss restlos weg,
        # sonst entsteht "Tabakerzeug nissen" statt "Tabakerzeugnissen".
        return head[:-1].rstrip() + tail.lstrip()
    return f"{head} {tail.lstrip()}".strip()


def _merge_layout_rows(page_text: str, n_values: int) -> list[tuple[str, list[str]]]:
    """Zerlege eine Tabellenseite in ``(label, werte)`` und heile Zeilenumbrüche.

    Umgebrochene Tabellenzeilen treten in zwei Formen auf, beide in der Probe
    beobachtet und beide regelmässig:

    * **Rückwärts** — eine Zeile mit genau zwei Zellen ``["nissen", "5"]`` folgt
      auf eine vollständige Datenzeile. Sie trägt den Rest der Beschriftung *und*
      die führenden Ziffern des ersten Werts: ``"5"`` + ``"6 31"`` ergibt 5631.
      Wer diese Zeile ignoriert, verliert stillschweigend eine Zehnerpotenz.
    * **Vorwärts** — eine Zeile mit einer Zelle trägt den Anfang der Beschriftung,
      die Datenzeile folgt (``"19 – 20 Kokerei, …"`` / ``"von chemischen …"``).
    """
    rows: list[tuple[str, list[str]]] = []
    pending_prefix: str | None = None

    for raw_line in page_text.split("\n"):
        cells = _layout_cells(raw_line)
        if not cells:
            continue

        if len(cells) == n_values + 1:
            label, values = cells[0], cells[1:]
            # Ein Präfix nur übernehmen, wenn die Datenzeile nicht bereits einen
            # eigenen Code trägt. Sonst schluckt eine Kopfzeile wie "in Mio. CHF"
            # die folgende Sektorzeile, und deren Wert fehlt in der Summe —
            # in der Probe genau der Fall, der Sektor I aus 2.4 NBUV tilgte.
            if pending_prefix and not _CODE_RE.match(re.sub(r"\s+", " ", label)):
                label = _append_label(pending_prefix, label)
            rows.append((label, values))
            pending_prefix = None
            continue

        if len(cells) == 2 and rows and _DIGIT_ONLY.match(cells[1]):
            prev_label, prev_values = rows[-1]
            merged_values = list(prev_values)
            merged_values[0] = cells[1] + merged_values[0]
            rows[-1] = (_append_label(prev_label, cells[0]), merged_values)
            pending_prefix = None
            continue

        # Einzelne Zelle ohne Zahlen: Beschriftungsanfang der folgenden Datenzeile.
        pending_prefix = cells[0] if len(cells) == 1 and not _DIGIT_ONLY.match(cells[0]) else None

    return rows


def _raw_label_map(page_text: str) -> dict[str, str]:
    """Saubere Beschriftungen aus dem Textmodus, indiziert nach Zeilenschlüssel.

    Der Layout-Modus streut Leerzeichen in Wörter; für die Anzeige ist das
    unbrauchbar. Der Textmodus setzt Wörter korrekt, und weil keine
    Beschriftung dieser Tabellen eine Ziffer enthält, endet das Label
    zuverlässig vor der ersten Ziffer des Zahlenteils.
    """
    labels: dict[str, str] = {}
    buffer = ""
    for raw_line in page_text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if buffer:
            # Nur anfügen, wenn die Folgezeile keinen eigenen Code trägt. Sonst
            # verschluckt eine Überschrift wie "Berufsunfallversicherung (BUV)"
            # die nachfolgende Sektorzeile.
            if not _CODE_RE.match(line):
                line = _append_label(buffer, line)
            buffer = ""
        # Beschriftung endet vor der ersten Ziffer, die nicht zum Code gehört.
        m = re.match(r"^(?P<label>(?:I{1,3}|\d{2}(?:\s*[,–—-]\s*\d{2})*)?\s*[^\d]+)", line)
        if not m:
            continue
        label = re.sub(r"\s+", " ", m.group("label")).strip()
        if not label or not re.search(r"[A-Za-zÄÖÜäöü]", label):
            continue
        # Zeile besteht vollständig aus Beschriftung: die Werte stehen erst in
        # der Folgezeile, egal ob mit Trennstrich umgebrochen oder ohne.
        if len(m.group("label")) == len(line):
            buffer = label
            continue
        labels.setdefault(_row_key(label), label)
    return labels


# ---------------------------------------------------------------------------
# Ausgabe-Erkennung
# ---------------------------------------------------------------------------


async def resolve_latest_edition(max_probe: int = 3) -> tuple[int, bytes, str | None]:
    """Ermittle die aktuelle Jahresausgabe durch direktes Proben von ``Ts{YY}.pdf``.

    Bewusst **nicht** über die Indexseite: ``jahr_d.htm`` verlinkte am Probetag
    (2026-08-05) durchgehend auf ``Ts25.pdf``, obwohl ``Ts26.pdf`` seit dem
    12. Juni 2026 online lag. Der eigene Index der Site hinkt eine Ausgabe
    hinterher — wer ihn scrapt, liefert stillschweigend veraltete Zahlen.

    Das direkte Proben ist billig und verlässlich, weil die Site sauber 404t
    (live geprüft: ``Ts27.pdf`` -> 404, ``Ts26.pdf`` -> 200).
    """
    current_yy = datetime.now(UTC).year % 100
    last_error: Exception | None = None
    for offset in range(max_probe + 1):
        yy = current_yy - offset
        if yy < UVG_FIRST_EDITION_YY:
            break
        url = UVG_ANNUAL_PDF_URL.format(yy=yy)
        try:
            payload, last_modified, _ = await _fetch_bytes(url, allow_404=True)
            return yy, payload, last_modified
        except FileNotFoundError:
            continue
        except UvgSourceUnavailableError as exc:
            last_error = exc
            continue
    raise UvgSourceUnavailableError(
        f"Keine Jahresausgabe in Ts{current_yy - max_probe:02d}..Ts{current_yy:02d} gefunden: {last_error}"
    )


def edition_label(yy: int) -> str:
    return f"UVG-Statistik {2000 + yy}"


# ---------------------------------------------------------------------------
# Parser 1 — Schlüsselzahlen (HTML)
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_ROW_RE = re.compile(r"<tr.*?</tr>", re.S | re.I)
_CELL_RE = re.compile(r"<t[dh].*?</t[dh]>", re.S | re.I)
_TABLE_RE = re.compile(r"<table.*?</table>", re.S | re.I)


def _cell_text(cell: str) -> str:
    return _html.unescape(_TAG_RE.sub(" ", cell)).replace("\xa0", " ").strip()


def parse_key_figures(html_text: str) -> dict[str, Any]:
    """Parse die Schlüsselzahlen-Tabelle (Gesamtschweiz, 5 Jahre).

    Aufbau je Datenzeile: Label | Einheit | 5 Jahreswerte. Abschnittsüberschriften
    (Versicherungsbestand / Fälle / Kosten) stehen in einer Zelle mit ``colspan``.
    """
    tables = _TABLE_RE.findall(html_text)
    if not tables:
        return {"parsed": False, "reason": "keine Tabelle im Dokument"}
    table = max(tables, key=len)

    years = [
        int(y)
        for y in re.findall(
            r"\b(20[0-9]{2})\b", _cell_text(html_text[: html_text.find(table) + 4000])
        )
    ]
    # Nur aufsteigende, aufeinanderfolgende Jahre am Tabellenkopf behalten.
    years = sorted({y for y in years if 2000 <= y <= datetime.now(UTC).year})[-5:]

    section = ""
    rows: list[dict[str, Any]] = []
    for row_html in _ROW_RE.findall(table):
        cells = [_cell_text(c) for c in _CELL_RE.findall(row_html)]
        if not cells:
            continue
        filled = [c for c in cells if c]
        if len(filled) == 1 and not re.search(r"\d", filled[0]):
            section = filled[0]
            continue
        if len(cells) < 3:
            continue
        label, unit, value_cells = cells[0], cells[1], cells[2:]
        if not label:
            continue
        values: list[dict[str, Any]] = []
        for idx, cell in enumerate(value_cells):
            value, significant = parse_number(cell)
            if value is None:
                continue
            values.append(
                {
                    "year": years[idx] if idx < len(years) else None,
                    "value": value,
                    "significant": significant,
                }
            )
        if values:
            rows.append(
                {"section": section, "label": label, "unit": unit or None, "values": values}
            )

    return {"parsed": True, "years": years, "rows": rows}


# ---------------------------------------------------------------------------
# Parser 2 — Jahresausgabe, Tabellen 1.2 und 2.4 (NOGA)
# ---------------------------------------------------------------------------

# Sektor- und NOGA-Zeilen der Publikation. Bereichsangaben wie "41 – 42" und
# "77, 79 – 82" kommen so im Raster vor und werden unverändert übernommen —
# eine eigene Normalisierung würde vom Publikationsstand abweichen.
_SECTOR_RE = re.compile(r"^(?P<code>I{1,3})\s+(?P<rest>[A-ZÄÖÜ].*)$")
_NOGA_RE = re.compile(r"^(?P<code>\d{2}(?:\s*[,–-]\s*\d{2})*)\s+(?P<rest>\D.*)$")

TABLE_SPECS: dict[str, dict[str, Any]] = {
    "1.2": {
        "caption": "Tabelle 1.2",
        "columns": [
            "full_time_equivalents",
            "share_pct",
            "risk_buv_per_1000",
            "risk_nbuv_per_1000",
        ],
        "hint_page": 13,
    },
    "2.4_BUV": {
        "caption": "Tabelle 2.4",
        "variant": "Berufsunfallversicherung",
        "columns": [
            "accepted_cases",
            "disability_pensions_accident",
            "disability_pensions_occupational_disease",
            "fatalities_accident",
            "fatalities_occupational_disease",
            "running_costs_mchf",
        ],
        "hint_page": 27,
    },
    "2.4_NBUV": {
        "caption": "Tabelle 2.4",
        "variant": "Nichtberufsunfallversicherung",
        "columns": [
            "accepted_cases",
            "disability_pensions",
            "fatalities",
            "running_costs_mchf",
        ],
        "hint_page": 28,
    },
}


def _find_table_page(pages: list[str], spec: dict[str, Any]) -> int | None:
    """Suche die Tabellenseite über die Bildunterschrift, nicht über die Seitenzahl.

    Die Gegenprobe Ts25 vs. Ts26 ergab identische Seitenpositionen für alle 18
    Tabellen — zwei Ausgaben sind aber eine schmale Basis für eine Serie, die bis
    2000 zurückreicht. Die Seitenzahl dient daher nur als Startpunkt der Suche.
    """
    caption = spec["caption"]
    variant = spec.get("variant")

    def matches(page_text: str) -> bool:
        if caption not in page_text:
            return False
        return variant in page_text if variant else True

    hint = spec.get("hint_page")
    order = list(range(len(pages)))
    if isinstance(hint, int) and 0 < hint <= len(pages):
        order.sort(key=lambda i: abs(i - (hint - 1)))
    for i in order:
        if matches(pages[i]):
            return i
    return None


def parse_branch_table(
    pages_layout: list[str], pages_text: list[str], table: str
) -> dict[str, Any]:
    """Parse eine NOGA-Tabelle der Jahresausgabe.

    Zahlen stammen aus dem Layout-Modus (eindeutige Spalten), Beschriftungen aus
    dem Textmodus (korrekt gesetzte Wörter); verbunden werden beide über den
    NOGA-Code am Zeilenanfang.

    Liefert immer auch die Zeile «Unbekannt» und die gedruckte Zeile «Total»
    nebst Summenprobe. Wer nur die drei Sektoren addiert, landet bei 261 367
    statt 261 446 — eine Abweichung, klein genug um unbemerkt zu bleiben, und
    genau deshalb ausgewiesen.
    """
    spec = TABLE_SPECS.get(table)
    if spec is None:
        return {"parsed": False, "reason": f"unbekannte Tabelle {table!r}"}
    page_index = _find_table_page(pages_text, spec)
    if page_index is None:
        return {"parsed": False, "reason": f"{spec['caption']} im Dokument nicht gefunden"}

    columns: list[str] = spec["columns"]
    clean_labels = _raw_label_map(pages_text[page_index])

    rows: list[dict[str, Any]] = []
    printed_total: dict[str, Any] | None = None

    for raw_label, raw_values in _merge_layout_rows(pages_layout[page_index], len(columns)):
        key = _row_key(raw_label)
        label = clean_labels.get(key, re.sub(r"\s+", " ", raw_label).strip())

        values: dict[str, Any] = {}
        flags: list[str] = []
        for column, raw in zip(columns, raw_values, strict=True):
            value, significant = parse_number(raw)
            values[column] = value
            if significant:
                flags.append(column)
        if all(v is None for v in values.values()):
            continue

        entry: dict[str, Any] = {"label": label, "significant_fields": flags, **values}

        if key == "total":
            printed_total = entry
            continue
        if key == "unbekannt":
            entry.update(row_type="unknown", code=None)
        elif (sector := _SECTOR_RE.match(label)) is not None:
            entry.update(
                row_type="sector", code=sector.group("code"), label=sector.group("rest").strip()
            )
        elif (noga := _NOGA_RE.match(label)) is not None:
            entry.update(
                row_type="branch", code=noga.group("code"), label=noga.group("rest").strip()
            )
        else:
            continue
        rows.append(entry)

    return {
        "parsed": bool(rows),
        "table": table,
        "page": page_index + 1,
        "columns": columns,
        "rows": rows,
        "printed_total": printed_total,
        "totals_check": _totals_check(rows, printed_total, columns[0]),
    }


def _totals_check(
    rows: list[dict[str, Any]], printed_total: dict[str, Any] | None, key: str
) -> dict[str, Any]:
    """Summenprobe gegen die gedruckte Zeile «Total».

    Diese Invariante ist in der Live-Probe exakt aufgegangen: Sektorzeilen
    (261 367) plus «Unbekannt» (79) ergaben das gedruckte Total (261 446).
    Sie prüft Zahlenerkennung und Zeilenabgrenzung in einem Schritt — und wenn
    das Layout eines Tages bricht, meldet sie es, statt still falsch zu rechnen.
    """
    if printed_total is None or printed_total.get(key) is None:
        return {"available": False, "reason": "keine gedruckte Total-Zeile gefunden"}
    summed = sum(
        r.get(key) or 0
        for r in rows
        if r.get("row_type") in {"sector", "unknown"} and r.get(key) is not None
    )
    printed = printed_total[key]
    delta = summed - printed
    # Toleranz, weil die Quelle selbst rundet: In der Ausgabe 2025 ergeben die
    # gedruckten Sektorzeilen der Tabelle 1.2 zusammen 4 469 213, gedruckt ist
    # 4 469 212. Der Rohtext bestätigt beide Zahlen — die Differenz stammt aus
    # der Publikation, nicht aus der Extraktion (Vollbeschäftigte sind laut
    # Quelle aus der Lohnsumme geschätzt). Eine Abweichung von 1 auf 4,5 Mio.
    # ist Rundung; ein gebrochenes Layout sieht völlig anders aus.
    tolerance = max(1, round(abs(printed) * 0.001))
    return {
        "available": True,
        "field": key,
        "sum_rows": summed,
        "printed_total": printed,
        "match": delta == 0,
        "within_tolerance": abs(delta) <= tolerance,
        "tolerance": tolerance,
        "delta": delta,
    }


# ---------------------------------------------------------------------------
# Parser 3 — Branchen-Zeitreihen (WirtKl_*.pdf)
# ---------------------------------------------------------------------------

_VERSION_RE = re.compile(r"Version:\s*(?P<version>[\d.]+)\s*/\s*(?P<date>\d{2}\.\d{2}\.\d{4})")


def _header_years(page_text: str) -> list[int]:
    """Finde die Jahresspalten: die Zeile mit der längsten Folge
    lückenlos aufsteigender Jahreszahlen."""
    best: list[int] = []
    for line in page_text.split("\n"):
        found = [int(y) for y in re.findall(r"\b(20\d{2})\b", line)]
        run: list[int] = []
        for year in found:
            if run and year == run[-1] + 1:
                run.append(year)
            else:
                if len(run) > len(best):
                    best = run
                run = [year]
        if len(run) > len(best):
            best = run
    return best if len(best) >= 3 else []


def parse_branch_series(pages: list[str]) -> dict[str, Any]:
    """Parse eine 10-Jahres-Zeitreihe je NOGA-Wirtschaftsabteilung.

    In dieser PDF-Familie ist der Tausendertrenner ein Apostroph (``1'057``),
    nicht ein Leerzeichen. Damit ist die Zerlegung eindeutig und ein einfacher
    Split von rechts genügt — die Mehrdeutigkeit der Jahrestabellen tritt hier
    nicht auf. Dieselbe Quelle, zwei Zahlenformate.
    """
    if not pages:
        return {"parsed": False, "reason": "leeres Dokument"}
    head = pages[0]

    version = None
    published = None
    m = _VERSION_RE.search(head)
    if m:
        version = m.group("version")
        day, month, year = m.group("date").split(".")
        published = f"{year}-{month}-{day}"

    # Jahre NUR aus der Kopfzeile der Kennzahlentabelle. Über die ganze Seite
    # gesucht liefert dieselbe Regex auch "NOGA 2008" und das Versionsdatum
    # 2026 — und damit eine Spaltenzahl, die es nie gab.
    years = _header_years(head)
    if not years:
        return {"parsed": False, "reason": "keine Jahresspalten im Kopf gefunden"}

    # Zeilenaufbau: <Label> <Jahreswerte…> <Mittel> <Trend%> <Mittel-UVG> <Trend-UVG%>
    #
    # Die vier Kennwerte am Schluss sind nicht garantiert vollständig: Lässt sich
    # der Trend der Branche nicht berechnen, druckt die Quelle die Zelle nicht.
    # Bei NOGA 86 trifft das «Berufskrankheiten BK / 100'000 VB» und
    # «Invalidenrenten BK / 100'000 VB». Eine fest verdrahtete Spaltenzahl hätte
    # genau diese beiden Kennzahlen kommentarlos verschwinden lassen — der
    # Aufrufer sähe zehn statt zwölf und hätte keinen Anhaltspunkt, dass etwas
    # fehlt. Deshalb wird der Zahlenschwanz gezählt, nicht vorausgesetzt.
    n_years = len(years)
    full, short = n_years + 4, n_years + 3

    label_line = next((ln for ln in head.split("\n") if re.match(r"^\s*\d{2}\s+\S", ln)), "")
    branch_label = re.sub(r"^\s*\d{2}\s+", "", label_line).strip()
    branch_label = re.sub(r"\s+\d{2}\s+UVG\s*$", "", branch_label).strip()

    indicators: list[dict[str, Any]] = []
    skipped: list[str] = []

    for line in head.split("\n"):
        tokens = line.strip().split()
        if len(tokens) < short + 1:
            continue

        # Längster rein numerischer Suffix. Bricht zuverlässig am Label ab, weil
        # dessen letztes Wort nie eine Zahl ist ("… / 100'000 VB").
        values: list[tuple[Any, bool]] = []
        index = len(tokens)
        while index > 0:
            value, significant = parse_number(tokens[index - 1])
            if value is None:
                break
            values.insert(0, (value, significant))
            index -= 1

        label = " ".join(tokens[:index]).strip()
        if not label or not re.search(r"[A-Za-zÄÖÜäöü]", label):
            continue
        if len(values) not in (full, short):
            if len(values) >= n_years:
                skipped.append(label)
            continue

        series = [
            {"year": year, "value": value, "significant": significant}
            for year, (value, significant) in zip(years, values[:n_years], strict=True)
        ]
        rest = [v for v, _ in values[n_years:]]
        # Die letzten beiden Werte sind immer die UVG-Gesamtreferenz; dazwischen
        # steht der Trend der Branche, sofern die Quelle ihn ausweist.
        indicators.append(
            {
                "indicator": label,
                "series": series,
                "mean": rest[0],
                "trend_pct": rest[1] if len(values) == full else None,
                "reference_mean": rest[-2],
                "reference_trend_pct": rest[-1],
            }
        )

    return {
        "parsed": bool(indicators),
        "branch_label": branch_label or None,
        "version": version,
        "published": published,
        "years": years,
        "indicators": indicators,
        "skipped_rows": skipped,
    }


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


def build_envelope(
    *,
    provenance: str,
    edition: str | None = None,
    freshness: dict[str, Any] | None = None,
    degraded: bool = False,
    note: str | None = None,
    **payload: Any,
) -> dict[str, Any]:
    """Portfolio-Envelope: ``source``, ``provenance``, ``retrieved_at``,
    ``source_freshness`` — plus ``degraded`` bei Quellenausfall."""
    envelope: dict[str, Any] = {
        "source": uvg_attribution(edition),
        "provenance": provenance,
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_freshness": freshness or {},
        "degraded": degraded,
    }
    if note:
        envelope["note"] = note
    envelope.update(payload)
    return envelope


def _degraded_envelope(reason: str) -> dict[str, Any]:
    return build_envelope(
        provenance="unavailable",
        degraded=True,
        note=(
            "unfallstatistik.ch war nach drei Versuchen (2s/4s/8s) nicht erreichbar und es "
            f"liegt kein Cache vor. Ursache: {reason}. In einigen Minuten erneut versuchen; "
            "die Publikationen sind unter unfallstatistik.ch auch direkt abrufbar."
        ),
    )


# ---------------------------------------------------------------------------
# NOGA-Code-Abgleich
# ---------------------------------------------------------------------------


def expand_code(code: str | None) -> set[int]:
    """Löse eine Rasterangabe in die enthaltenen NOGA-Nummern auf.

    Die Publikation fasst Abteilungen zusammen: ``"41 – 42"``, ``"77, 79 – 82"``.
    Wer nach ``"42"`` fragt, meint die Zeile ``"41 – 42"`` — ein reiner
    Stringvergleich fände sie nie.
    """
    if not code:
        return set()
    numbers: set[int] = set()
    for part in re.split(r"\s*,\s*", code.strip()):
        bounds = re.split(r"\s*[–—-]\s*", part.strip())
        try:
            if len(bounds) == 2:
                numbers.update(range(int(bounds[0]), int(bounds[1]) + 1))
            elif len(bounds) == 1 and bounds[0]:
                numbers.add(int(bounds[0]))
        except ValueError:
            continue
    return numbers


def code_matches(query: str, code: str | None) -> bool:
    wanted = expand_code(query)
    return bool(wanted and wanted <= expand_code(code))


# ---------------------------------------------------------------------------
# Tool-Implementationen (getrennt von den MCP-Wrappern, damit testbar)
# ---------------------------------------------------------------------------

_NO_MATCH_HINT = (
    "Kein Wirtschaftszweig mit diesem Code im Publikationsraster. Die Quelle fasst "
    "Abteilungen zusammen (z. B. '01 – 03', '77, 79 – 82'), deshalb existiert nicht "
    "jeder zweistellige NOGA-Code als eigene Zeile. Nächster Versuch: `noga` weglassen "
    "— das liefert das vollständige Raster samt Sektorzeilen und der Kategorie "
    "'Unbekannt'; daraus den passenden Code ablesen und erneut abfragen. Erst danach "
    "auf Abwesenheit schliessen, und keine Schätzung an die Stelle des Werts setzen."
)


def _page_data_year(page_text: str, edition_year: int) -> int | None:
    """Jüngstes Datenjahr der Tabellenseite.

    Das Ausgabejahr selbst ist ausgeschlossen: Es steht in der Fusszeile jeder
    Seite («UVG-Statistik 2026») und wäre sonst immer das Maximum — die Ausgabe
    2026 würde 2026 als Datenjahr melden, obwohl sie 2024 ausweist.
    """
    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", page_text)]
    candidates = [y for y in years if y < edition_year]
    return max(candidates) if candidates else None


async def uvg_overview_impl(years: int = 5, include_nbuv: bool = False) -> dict[str, Any]:
    """Gesamtschweizerische Schlüsselzahlen zu Berufsunfällen und Berufskrankheiten."""
    try:
        payload, last_modified, provenance = await _fetch_bytes(UVG_KEY_FIGURES_URL)
    except UvgSourceUnavailableError as exc:
        return _degraded_envelope(str(exc))

    parsed = parse_key_figures(payload.decode("utf-8-sig", errors="replace"))
    if not parsed.get("parsed"):
        return _degraded_envelope(f"Schlüsselzahlen nicht lesbar: {parsed.get('reason')}")

    all_years = parsed["years"]
    keep = set(all_years[-years:]) if years else set(all_years)

    # NBUV = Nichtberufsunfälle (Freizeit). Standardmässig ausgeblendet: Dieser
    # Server deckt den Arbeitsmarkt ab, Freizeitunfälle sind Kontext.
    drop = {"NBUV", "UVAL", "UV IV"}
    rows = []
    for row in parsed["rows"]:
        if not include_nbuv and row["label"].strip() in drop:
            continue
        values = [v for v in row["values"] if v["year"] in keep]
        if values:
            rows.append({**row, "values": values})

    return build_envelope(
        provenance=f"key_figures_html:{provenance}",
        freshness={
            "last_modified": last_modified,
            "years_covered": sorted(keep),
            "latest_year": max(keep) if keep else None,
            "note": (
                "Die jüngste Jahresspalte ist zum Publikationszeitpunkt noch nicht "
                "vollständig befüllt; fehlende Werte werden nicht ausgewiesen."
            ),
        },
        scope="Schweiz gesamt (alle UVG-Versicherer)",
        includes_non_occupational=include_nbuv,
        rows=rows,
    )


async def uvg_by_branch_impl(noga: str | None = None, table: str = "2.4_BUV") -> dict[str, Any]:
    """Unfallrisiko und anerkannte Fälle je Wirtschaftszweig (NOGA 2008)."""
    try:
        yy, payload, last_modified = await resolve_latest_edition()
    except UvgSourceUnavailableError as exc:
        return _degraded_envelope(str(exc))

    pages_layout = _pdf_pages(payload, layout=True)
    pages_text = _pdf_pages(payload)
    parsed = parse_branch_table(pages_layout, pages_text, table)
    if not parsed.get("parsed"):
        return _degraded_envelope(f"Tabelle {table} nicht lesbar: {parsed.get('reason')}")

    meta = _pdf_metadata(payload)
    edition_year = 2000 + yy
    data_year = _page_data_year(pages_text[parsed["page"] - 1], edition_year)

    rows = parsed["rows"]
    if noga:
        rows = [r for r in rows if code_matches(noga, r.get("code"))]

    envelope = build_envelope(
        provenance="annual_pdf",
        edition=edition_label(yy),
        freshness={
            "edition": edition_label(yy),
            "data_year": data_year,
            "published": _pdf_date(meta.get("CreationDate")),
            "last_modified": last_modified,
            "lag_note": (
                f"Die Ausgabe {edition_year} weist {data_year} als jüngstes vollständiges "
                "Branchenjahr aus."
            ),
        },
        table=table,
        source_url=UVG_ANNUAL_PDF_URL.format(yy=yy),
        columns=parsed["columns"],
        classification="NOGA 2008 (BFS)",
        returned=len(rows),
        rows=rows,
        printed_total=parsed["printed_total"],
        totals_check=parsed["totals_check"],
    )
    if noga and not rows:
        envelope["hint"] = _NO_MATCH_HINT
    return envelope


async def uvg_trends_impl(
    noga: str, branch_type: str = "BUV", indicator: str | None = None
) -> dict[str, Any]:
    """Zehnjahres-Zeitreihe der Erfolgskennzahlen je NOGA-Wirtschaftsabteilung."""
    code = re.sub(r"\D", "", noga or "")
    if len(code) != 2:
        return build_envelope(
            provenance="input_rejected",
            returned=0,
            rows=[],
            hint=(
                f"`noga` muss eine zweistellige NOGA-2008-Wirtschaftsabteilung sein, "
                f"erhalten: {noga!r}. Beispiele: '43' (Ausbaugewerbe), '86' (Gesundheitswesen), "
                "'85' (Erziehung und Unterricht). Bereichsangaben wie '41 – 42' gibt es nur in "
                "der Jahrestabelle (`seco_get_uvg_by_branch`), nicht in den Zeitreihen."
            ),
        )

    scheme = "NBUV" if str(branch_type).upper() == "NBUV" else "BUV"
    url = UVG_BRANCH_PDF_URL.format(scheme=scheme, noga=code)
    try:
        payload, last_modified, provenance = await _fetch_bytes(url, allow_404=True)
    except FileNotFoundError:
        return build_envelope(
            provenance="branch_pdf",
            returned=0,
            rows=[],
            source_url=url,
            hint=(
                f"Für die Abteilung {code} führt die Quelle keine eigene Zeitreihe. Nicht jede "
                "NOGA-Nummer ist besetzt (z. B. fehlen 04, 05, 07, 09). Nächster Versuch: "
                "`seco_get_uvg_by_branch` ohne `noga` aufrufen und die tatsächlich belegten "
                "Codes ablesen. Erst danach auf Abwesenheit schliessen."
            ),
        )
    except UvgSourceUnavailableError as exc:
        return _degraded_envelope(str(exc))

    parsed = parse_branch_series(_pdf_pages(payload))
    if not parsed.get("parsed"):
        return _degraded_envelope(f"Zeitreihe {code}/{scheme} nicht lesbar: {parsed.get('reason')}")

    indicators = parsed["indicators"]
    if indicator:
        needle = indicator.casefold()
        indicators = [i for i in indicators if needle in i["indicator"].casefold()]

    envelope = build_envelope(
        provenance=f"branch_pdf:{provenance}",
        freshness={
            "version": parsed["version"],
            "published": parsed["published"],
            "last_modified": last_modified,
            "years_covered": parsed["years"],
            "note": (
                "Stand aus dem Versionsstring des PDF. Die Indexseite branchen_d.htm nennt "
                "ein abweichendes, älteres Datum; massgebend ist die Datei."
            ),
        },
        noga=code,
        branch_label=parsed["branch_label"],
        insurance_branch=scheme,
        classification="NOGA 2008 (BFS)",
        source_url=url,
        significance_note=(
            "`significant` markiert eine statistisch signifikante Veränderung gegenüber "
            "dem Vorjahr (Definition: Beschrieb_Branchen_d.pdf der Quelle)."
        ),
        returned=len(indicators),
        indicators=indicators,
        # Verworfene Zeilen werden ausgewiesen, nicht verschwiegen: Ein Parser,
        # der still weniger liefert, sieht aus wie eine Quelle mit weniger Daten.
        skipped_rows=parsed.get("skipped_rows", []),
    )
    if indicator and not indicators:
        available = ", ".join(i["indicator"] for i in parsed["indicators"])
        envelope["hint"] = (
            f"Keine Kennzahl enthält {indicator!r}. Der Abgleich ist eine "
            f"Teilstring-Suche ohne Wildcards. Verfügbar sind: {available}. "
            "`indicator` weglassen liefert alle."
        )
    return envelope
