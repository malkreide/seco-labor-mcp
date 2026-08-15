"""
SECO Labor Market MCP Server
=============================
Schweizer Arbeitsmarktdaten. Die registrierten Arbeitslosen und
Stellensuchenden sind SECO-Zahlen aus dem RAV-System; veroeffentlicht werden
sie vom BFS, weil SECO auf opendata.swiss kein Herausgeber (mehr) ist und
amstat.ch keine Schnittstelle hat. Begruendung, Messung und die gepinnten
Kennungen stehen in `sources.py`.

Datenquellen (ohne Authentisierung):
  - opendata.swiss CKAN API (Katalog und die gepinnte BFS-Tabelle T3.3.0.1)
  - unfallstatistik.ch (UVG: HTML-Kennzahlen und PDF-Jahresberichte)
  - Monatsbericht-PDFs von arbeit.swiss (URL-Muster)

Primary use cases:
  - Berufswahlberatung (vocational guidance)
  - Lehrstellen-Monitoring (apprenticeship market monitoring)
  - Bildungsplanung (education planning)
  - Arbeitsmarktanalyse (labor market analysis)
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import socket
import time
from contextlib import asynccontextmanager
from datetime import datetime
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

import httpx
from fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from . import __version__, retry_policy, sources
from .uvg import uvg_by_branch_impl, uvg_overview_impl, uvg_trends_impl

# ---------------------------------------------------------------------------
# HTTP client lifecycle (SDK-001: pooled client via FastMCP lifespan)
# ---------------------------------------------------------------------------

HTTP_TIMEOUT = 30.0

# Portfolio-Standard fuer transiente Fehler. Dieselbe Staffelung nutzt
# uvg.UVG_BACKOFF_SECONDS; die beiden bleiben getrennt, weil uvg.py server.py
# nicht auf Modulebene importieren kann (server.py importiert uvg.py).
HTTP_BACKOFF_SECONDS = (2.0, 4.0, 8.0)

# Eigener Alias, damit Tests die Wartezeit nullen koennen, ohne `asyncio.sleep`
# prozessweit zu entschaerfen. `monkeypatch.setattr(<modul>.asyncio, "sleep", ...)`
# sieht lokal aus, ersetzt `sleep` aber auf dem geteilten Modulobjekt -- fuer
# httpx, respx, pytest-asyncio und jeden anderen Importeur im Prozess.
#
# Gilt vorerst nur fuer die Schleife in `_fetch_bytes_with_retry`; `uvg.py`
# ruft weiterhin `asyncio.sleep` direkt und gehoert in denselben Zug wie die
# uebrigen Server des Portfolios.
_sleep = asyncio.sleep

_HTTP_KWARGS: dict[str, Any] = {
    "timeout": HTTP_TIMEOUT,
    # SEC-004: do not auto-follow redirects so we cannot be tricked into
    # fetching a private/loopback target after URL validation already passed
    # (DNS-rebinding / redirect TOCTOU).
    "follow_redirects": False,
    "headers": {
        "User-Agent": f"seco-labor-mcp/{__version__} (Swiss Public Data MCP Portfolio; github.com/malkreide)",
        "Accept": "application/json, text/csv, */*",
    },
}

# Module-level shared client, populated by the FastMCP lifespan.
# Falls back to per-call clients when running outside a lifespan (e.g. unit tests).
_HTTP_CLIENT: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(_server: FastMCP):
    """Initialise a single pooled httpx.AsyncClient for the server lifetime."""
    global _HTTP_CLIENT
    _HTTP_CLIENT = httpx.AsyncClient(**_HTTP_KWARGS)
    try:
        yield
    finally:
        await _HTTP_CLIENT.aclose()
        _HTTP_CLIENT = None


# ---------------------------------------------------------------------------
# Server initialisation
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "seco_labor_mcp",
    instructions=(
        "Swiss labor market data server. Liefert die nationale Jahresreihe der "
        "registrierten Arbeitslosen und Stellensuchenden (SECO-Zahlen, publiziert "
        "vom BFS) sowie die UVG-Unfallstatistik. Monats- und Kantonswerte gibt es "
        "zurzeit in keiner maschinenlesbaren Quelle; die betroffenen Werkzeuge "
        "sagen das, statt eine nationale Zahl kantonal zu beschriften. "
        "All data is public and requires no API key. "
        "Particularly useful for educational planning, vocational guidance (Berufswahlberatung), "
        "and apprenticeship market monitoring (Lehrstellen-Monitoring)."
    ),
    lifespan=lifespan,
    mask_error_details=True,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CKAN_BASE = "https://opendata.swiss/api/3/action"
AMSTAT_BASE = "https://www.amstat.ch"
ARBEIT_SWISS_BASE = "https://www.arbeit.swiss"

# `SECO_ORG` ist am 2026-08-14 entfallen. Die Organisation existiert auf
# opendata.swiss nicht mehr, und der Filter darauf machte aus jeder Suche eine
# leere Antwort. Was an ihre Stelle tritt und warum kein anderer Herausgeber
# einfach eingesetzt wurde, steht in `sources.py`.

# Swiss canton codes mapping
CANTON_CODES = {
    "ZH": "Zürich",
    "BE": "Bern",
    "LU": "Luzern",
    "UR": "Uri",
    "SZ": "Schwyz",
    "OW": "Obwalden",
    "NW": "Nidwalden",
    "GL": "Glarus",
    "ZG": "Zug",
    "FR": "Freiburg",
    "SO": "Solothurn",
    "BS": "Basel-Stadt",
    "BL": "Basel-Landschaft",
    "SH": "Schaffhausen",
    "AR": "Appenzell Ausserrhoden",
    "AI": "Appenzell Innerrhoden",
    "SG": "St. Gallen",
    "GR": "Graubünden",
    "AG": "Aargau",
    "TG": "Thurgau",
    "TI": "Ticino",
    "VD": "Vaud",
    "VS": "Valais",
    "NE": "Neuchâtel",
    "GE": "Genève",
    "JU": "Jura",
}

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class ResponseFormat(StrEnum):
    """Output format for tool responses."""

    MARKDOWN = "markdown"
    JSON = "json"


class DatasetSearchInput(BaseModel):
    """Input for SECO dataset search on opendata.swiss."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    query: str = Field(
        ...,
        description=(
            "Search query in German or English. "
            "Examples: 'arbeitslose kantone', 'Jugendarbeitslosigkeit', "
            "'offene Stellen', 'Kurzarbeit', 'unemployment youth'"
        ),
        min_length=2,
        max_length=200,
    )
    limit: int = Field(
        default=10,
        description="Maximum number of datasets to return (1-20).",
        ge=1,
        le=20,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable, 'json' for structured data.",
    )


class UnemploymentInput(BaseModel):
    """Input for unemployment statistics queries."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    canton: str | None = Field(
        default=None,
        description=(
            "Filter by canton code (2-letter). "
            "Examples: 'ZH' (Zürich), 'BE' (Bern), 'GE' (Genève), 'TI' (Ticino). "
            "Leave empty for national totals."
        ),
        max_length=2,
    )
    year: int | None = Field(
        default=None,
        description="Filter by year (e.g. 2024, 2025). Leave empty for latest available data.",
        ge=2000,
        le=2030,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'.",
    )


class YouthUnemploymentInput(BaseModel):
    """Input for youth unemployment queries (15–24 year olds)."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    canton: str | None = Field(
        default=None,
        description=("Filter by canton code (2-letter, e.g. 'ZH'). Leave empty for national data."),
        max_length=2,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'.",
    )


class JobSeekersInput(BaseModel):
    """Input for job seeker (Stellensuchende) queries."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    canton: str | None = Field(
        default=None,
        description="Filter by canton code (e.g. 'ZH'). Leave empty for national totals.",
        max_length=2,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'.",
    )


class OpenPositionsInput(BaseModel):
    """Input for open positions (Offene Stellen) queries."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'.",
    )


class OccupationInput(BaseModel):
    """Input for unemployment-by-occupation (Berufshauptgruppe) queries."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'.",
    )


class MonthlyReportInput(BaseModel):
    """Input for monthly press report URL lookup."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    year: int = Field(
        default_factory=lambda: datetime.now().year,
        description="Year of the report (e.g. 2025, 2026).",
        ge=2020,
        le=2030,
    )
    month: int = Field(
        default_factory=lambda: datetime.now().month,
        description="Month of the report (1–12).",
        ge=1,
        le=12,
    )
    language: str = Field(
        default="de",
        description="Language of the report: 'de' (German), 'fr' (French), 'it' (Italian).",
        pattern=r"^(de|fr|it)$",
    )


class DatasetDetailsInput(BaseModel):
    """Input for fetching a specific SECO dataset."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    dataset_id: str = Field(
        ...,
        description=(
            "Dataset ID or slug from opendata.swiss. Obtain from seco_search_datasets first."
        ),
        min_length=3,
        max_length=200,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'.",
    )


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


class UrlNotAllowedError(ValueError):
    """Raised by _validate_external_url for unsafe schemes or IP targets."""


async def _validate_external_url(url: str) -> None:
    """SEC-004: Reject URLs that are not HTTPS or that resolve to a
    private/loopback/link-local/multicast IP. Resolution happens here
    (and not inside httpx), so combined with follow_redirects=False
    this also prevents DNS-rebinding TOCTOU attacks.

    Async so DNS resolution runs on the event loop's executor and does
    not block other concurrent tool calls under SSE deployment."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise UrlNotAllowedError(f"only https:// is allowed, got: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UrlNotAllowedError(f"missing hostname in URL: {url!r}")
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UrlNotAllowedError(f"DNS resolution failed for {host!r}: {exc}") from exc
    for _family, _type, _proto, _canon, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise UrlNotAllowedError(f"refusing to fetch URL pointing at non-public address: {ip}")


@asynccontextmanager
async def _client_scope():
    """Yield the shared pooled client when running under lifespan;
    otherwise yield a per-call client (e.g. unit tests with respx)."""
    if _HTTP_CLIENT is not None and not _HTTP_CLIENT.is_closed:
        yield _HTTP_CLIENT
    else:
        async with httpx.AsyncClient(**_HTTP_KWARGS) as client:
            yield client


def _to_execution_error(e: Exception) -> str:
    """OBS-001: For EXECUTION errors (4xx, refused URLs, malformed input),
    return a user-facing string so the LLM can react and try something else.
    For PROTOCOL errors (5xx, timeout, connect failure, unknown), re-raise
    so FastMCP turns it into a proper JSON-RPC error with isError=true."""
    if isinstance(e, UrlNotAllowedError):
        return f"Error: URL rejected by SSRF policy ({e})."
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code == 404:
            return (
                "Error: Resource not found (HTTP 404). "
                "Use seco_search_datasets to find valid dataset IDs."
            )
        if code == 429:
            return "Error: Rate limit exceeded. Please wait a moment before retrying."
        if 500 <= code < 600:
            # Upstream is broken — protocol-level concern, not something the
            # LLM can fix by changing arguments. Surface it as a real error.
            raise e
        if 300 <= code < 400:
            # follow_redirects=False yields these. Treat as execution error.
            return f"Error: Unexpected redirect (HTTP {code}); refusing to follow."
        return f"Error: HTTP {code}."
    # Connectivity issues: protocol-level. Re-raise.
    raise e


def _fmt_number(n: Any) -> str:
    """Format integer with Swiss thousand separator (apostrophe)."""
    try:
        return f"{int(n):,}".replace(",", "'")
    except (ValueError, TypeError):
        return str(n)


def _pct(v: Any) -> str:
    """Format percentage value."""
    try:
        return f"{float(v):.1f}%"
    except (ValueError, TypeError):
        return str(v)


# ---------------------------------------------------------------------------
# CKAN helpers
# ---------------------------------------------------------------------------


class UpstreamSchemaError(RuntimeError):
    """Die Antwort kam an, sieht aber anders aus, als der Code sie liest.

    Bewusst **kein** Ausfuehrungsfehler im Sinne von ``_to_execution_error``:
    Ein anderer Suchbegriff hilft hier nicht, und eine Zeichenkette an das
    Modell zurueckzugeben hiesse, ihm eine Handlung anzubieten, die es nicht
    gibt. Der Typ ist ``_to_execution_error`` unbekannt und wird deshalb
    weitergereicht — FastMCP macht daraus ``isError: true`` (OBS-001).
    """


class UpstreamUnreachableError(RuntimeError):
    """Alle Versuche verbraucht oder das Budget abgelaufen.

    Wie ``UpstreamSchemaError`` bewusst kein Ausfuehrungsfehler: ein anderer
    Suchbegriff hilft gegen einen Netzausfall nicht. Der Typ ist
    ``_to_execution_error`` unbekannt und wird weitergereicht (OBS-001).
    """


def _ckan_result(payload: object, action: str) -> dict:
    """Den ``result``-Block einer CKAN-Antwort holen, oder laut scheitern.

    Ein Default auf dem Wurzelpfad schreibt jede Strukturaenderung in ein
    gueltiges leeres Ergebnis um, und fuer das Modell ist das nicht von «die
    Quelle kennt das nicht» zu unterscheiden (FID-006).
    """
    if not isinstance(payload, dict):
        raise UpstreamSchemaError(
            f"CKAN `{action}`: Antwort ist {type(payload).__name__} und kein Objekt."
        )
    if "result" not in payload:
        raise UpstreamSchemaError(
            f"CKAN `{action}`: Antwort ohne `result`. Vorhandene Schluessel: "
            f"{sorted(payload)}. Das ist keine Leermenge — die Struktur der "
            "Quelle hat sich geaendert."
        )
    result = payload["result"]
    if not isinstance(result, dict):
        raise UpstreamSchemaError(
            f"CKAN `{action}`: `result` ist {type(result).__name__} und kein Objekt."
        )
    return result


def _ckan_results(payload: object) -> list:
    """Die Trefferliste einer ``package_search``-Antwort, oder laut scheitern.

    Sechs Werkzeuge lasen die Liste mit zwei Defaults hintereinander. Fiel
    ``result`` weg, antworteten sie «Keine SECO-Datensaetze gefunden» samt
    Vorschlaegen fuer andere Suchbegriffe — fuer das Modell nicht davon zu
    unterscheiden, dass es zu dieser Anfrage wirklich nichts gibt.

    Bestaetigt wird die **Anwesenheit** von ``results``, nicht sein Inhalt:
    ``results: []`` ist eine Aussage der Quelle und bleibt eine leere Suche.
    CKAN liefert den Schluessel auch bei null Treffern.
    """
    result = _ckan_result(payload, "package_search")
    if "results" not in result:
        raise UpstreamSchemaError(
            "CKAN `package_search`: `result` ohne `results`. Vorhandene "
            f"Schluessel: {sorted(result)}. CKAN liefert `results` auch bei null "
            "Treffern — dies ist keine leere Suche."
        )
    return result["results"]


async def _ckan_search(query: str, limit: int = 10) -> dict:
    """Durchsucht opendata.swiss nach Arbeitsmarkt-Datensätzen.

    Ohne Organisationsfilter, und das ist eine Aussage über die Quelle: SECO
    ist auf opendata.swiss kein Herausgeber (mehr). Der frühere Filter auf
    ``organization:staatssekretariat-fur-wirtschaft-seco`` traf deshalb nie
    etwas und machte aus jeder Suche eine leere — Begründung und Messung
    stehen in ``sources.py``.

    Was der Ersatz *nicht* tut: so tun, als wären die Treffer SECO-Datensätze.
    Jeder Treffer trägt seinen Herausgeber, und die Werkzeuge zeigen ihn an.
    """
    async with _client_scope() as client:
        resp = await client.get(
            f"{CKAN_BASE}/package_search",
            params={
                "q": query,
                "rows": limit,
                "sort": "score desc, metadata_modified desc",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def _fetch_bytes_with_retry(url: str) -> bytes:
    """Holt eine Datei mit der Portfolio-Leiter 2s/4s/8s und dem Budget.

    Ohne diese Schleife stand der Abruf der BFS-Tabelle nackt da: ein einziger
    `client.get`. Der Asset-Host bricht die TLS-Verhandlung sporadisch ab —
    beim Aufzeichnen der Fixtures zweimal in Folge —, und ein Werkzeug, das
    daran scheitert, meldet «Quelle nicht erreichbar» für einen Aussetzer von
    Sekunden.

    Wiederholt werden 429, 5xx und Netzfehler. Ein 404 oder ein Umleitungscode
    ist eine Antwort und kein Ausfall; ihn zu wiederholen kostet nur Zeit.
    Anders als der frühere CSV-Pfad liefert diese Funktion keinen `None`-Wert
    zurück, sondern reicht den letzten Fehler durch: der Aufrufer baut daraus
    eine benannte Antwort, statt eine leere Reihe auszugeben.
    """
    await _validate_external_url(url)
    deadline = time.monotonic() + retry_policy.RETRY_TOTAL_BUDGET
    last_error: Exception | None = None

    for attempt in range(len(HTTP_BACKOFF_SECONDS) + 1):
        if attempt:
            delay = retry_policy.compute_delay(attempt, last_error)
            # Eine Wartezeit, die das Budget überdauert, wartet für niemanden.
            if delay >= deadline - time.monotonic():
                break
            await _sleep(delay)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            async with _client_scope() as client, asyncio.timeout(remaining):
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.content
        except TimeoutError as exc:  # Budget aufgebraucht, nicht nur dieser Versuch
            last_error = exc
            break
        except httpx.HTTPStatusError as exc:
            last_error = exc
            code = exc.response.status_code
            if not (code == 429 or 500 <= code < 600):
                raise
        except httpx.RequestError as exc:
            last_error = exc

    raise UpstreamUnreachableError(
        f"{url} nach {attempt + 1} Versuch(en) nicht erreichbar: "
        # `str(last_error) or ...`, nicht `last_error or ...`: eine Ausnahme mit
        # leerem `str()` ist trotzdem wahr, und `httpx.ConnectError`,
        # `ConnectTimeout` und `ReadTimeout` haben genau das — also die Menge,
        # die ein echter Ausfall erzeugt. Derselbe Fehler steckte bis 2026-08-07
        # in `uvg.py` und liess den Satz nach dem Doppelpunkt enden.
        f"{type(last_error).__name__}: {str(last_error) or 'kein weiterer Hinweis'}"
    ) from last_error


async def _bfs_jahresreihe() -> dict[str, Any]:
    """Holt die gepinnte BFS-Tabelle und liest die drei SECO-Reihen daraus.

    Zweistufig mit Absicht: erst ``package_show`` auf die gepinnte UUID, dann
    die XLS-Ressource, die *dort* steht. Die Asset-URL des BFS wird damit
    bewusst nicht zweitgepinnt — sie hängt an einer Asset-Nummer, die sich bei
    jeder Neupublikation ändert. Gepinnt ist nur die Kennung, die stabil sein
    soll; alles andere wird bei jedem Abruf frisch gelesen.
    """
    paket = await _ckan_get_dataset(sources.JAHRESREIHE.ckan_id)
    ds = _ckan_result(paket, "package_show")
    xls = next(
        (r for r in ds.get("resources", []) if (r.get("format") or "").upper() in {"XLS", "XLSX"}),
        None,
    )
    if xls is None or not xls.get("url"):
        raise UpstreamSchemaError(
            f"Datensatz {sources.JAHRESREIHE.slug!r} führt keine XLS-Ressource mehr. "
            f"Vorhandene Formate: "
            f"{sorted({r.get('format') for r in ds.get('resources', [])})}"
        )
    payload = await _fetch_bytes_with_retry(xls["url"])
    daten = sources.parse_jahresreihe(payload)
    daten["resource_url"] = xls["url"]
    daten["dataset_modified"] = (ds.get("metadata_modified") or "")[:10]
    return daten


async def _ckan_get_dataset(dataset_id: str) -> dict:
    """Fetch a specific dataset from opendata.swiss CKAN."""
    async with _client_scope() as client:
        resp = await client.get(
            f"{CKAN_BASE}/package_show",
            params={"id": dataset_id},
        )
        resp.raise_for_status()
        return resp.json()


def _extract_title(title_field: Any) -> str:
    """Extract title from multilingual CKAN title field."""
    if isinstance(title_field, dict):
        return (
            title_field.get("de")
            or title_field.get("fr")
            or title_field.get("en")
            or title_field.get("it")
            or str(title_field)
        )
    return str(title_field) if title_field else ""


def _herausgeber(ds: dict) -> str:
    """Der Herausgeber eines Treffers, so wie CKAN ihn führt.

    Wird bei jedem Treffer angezeigt, weil die Suche seit dem 2026-08-14 ohne
    Organisationsfilter läuft: die Treffer stammen vom BFS, von Kantonen und
    vom liechtensteinischen Amt für Statistik. Sie als «SECO-Datensätze» zu
    zeigen wäre genau die Verwechslung, die dieser Umbau beheben soll.
    """
    org = ds.get("organization") or {}
    titel = org.get("title")
    if isinstance(titel, dict):
        titel = titel.get("de") or titel.get("fr") or titel.get("en")
    return str(titel or org.get("name") or "unbekannt")


def _format_datasets_markdown(datasets: list[dict]) -> str:
    """Format CKAN dataset list as readable Markdown."""
    if not datasets:
        return "Keine Datensätze gefunden."

    lines = [
        "## Arbeitsmarkt-Datensätze auf opendata.swiss\n",
        f"*{len(datasets)} Datensätze gefunden*\n",
        "> Die Suche läuft ohne Herausgeberfilter. SECO ist auf opendata.swiss kein\n"
        "> Herausgeber; die Treffer stammen vom BFS, von Kantonen und weiteren Stellen.\n"
        "> Der Herausgeber steht bei jedem Treffer — er entscheidet, was die Zahlen messen.\n",
    ]
    for ds in datasets:
        title = _extract_title(ds.get("title", ""))
        ds_id = ds.get("name", ds.get("id", ""))
        modified = (ds.get("metadata_modified") or "")[:10]
        notes = _extract_title(ds.get("notes", "")) or ""
        resources = ds.get("resources", [])

        lines.append(f"### {title}")
        lines.append(f"- **ID**: `{ds_id}`")
        lines.append(f"- **Herausgeber**: {_herausgeber(ds)}")
        if modified:
            lines.append(f"- **Aktualisiert**: {modified}")
        if notes:
            lines.append(f"- **Beschreibung**: {notes[:200]}{'…' if len(notes) > 200 else ''}")
        if resources:
            lines.append(f"- **Ressourcen**: {len(resources)} Datei(en)")
            for res in resources[:3]:
                fmt = res.get("format", "?")
                rname = _extract_title(res.get("name", ""))
                url = res.get("url", "")
                lines.append(f"  - [{fmt}] {rname}: {url}")
        lines.append("")

    lines.append(
        "\n*Tipp: Verwende `seco_get_dataset` mit der Dataset-ID für Details und Download-Links.*"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 1: Arbeitsmarkt-Datensaetze auf opendata.swiss suchen
# ---------------------------------------------------------------------------


@mcp.tool(
    name="seco_search_datasets",
    annotations={
        "title": "Arbeitsmarkt-Datensätze suchen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def seco_search_datasets(params: DatasetSearchInput) -> str:
    """Sucht Arbeitsmarkt-Datensätze auf opendata.swiss.

    **Nicht auf SECO gefiltert, und das ist eine Aussage über die Quelle.** Bis
    zum 2026-08-14 filterte diese Suche auf `organization:staatssekretariat-
    fur-wirtschaft-seco`. Diese Organisation existiert auf opendata.swiss nicht
    (mehr): `organization_show` antwortet 404, und in den 176 Einträgen von
    `organization_list` kommt kein SECO vor. Jede Suche lieferte deshalb null
    Treffer — und ein Namensabgleich, der ins Leere läuft, sieht genau aus wie
    eine leere Suche.

    Die Suche läuft jetzt über den ganzen Bestand, und **jeder Treffer trägt
    seinen Herausgeber**. Das ist die ehrlichere Antwort: Datensätze zum
    Arbeitsmarkt gibt es, sie stammen nur vom BFS, von Kantonen und vom
    liechtensteinischen Amt für Statistik. Wer sie verwendet, muss wissen, von
    wem — die Erhebungsweise unterscheidet sich, und registrierte Arbeitslose
    (SECO) sind nicht dasselbe wie Erwerbslose gemäss ILO (BFS).

    Args:
        params (DatasetSearchInput): Contains:
            - query (str): Search terms (German/English)
            - limit (int): Max results (1-20, default 10)
            - response_format (str): 'markdown' or 'json'

    Returns:
        str: Dataset list with IDs and resource URLs, or JSON array of dataset objects.

    Example queries:
        - 'arbeitslose kantone' → kantonale Arbeitslosenzahlen (kantonale Portale)
        - 'Kurzarbeit' → Kurzarbeitsentschädigung
        - 'Erwerbslose ILO' → die BFS-Reihe

    Hinweis: 'Jugendarbeitslosigkeit' liefert am 2026-08-14 portalweit null
    Treffer. Das ist der Bestand und kein Fehler der Suche.
    """
    try:
        result = await _ckan_search(params.query, params.limit)
    except Exception as e:
        return _to_execution_error(e)

    datasets = _ckan_results(result)

    if not datasets:
        return (
            f"Keine Datensätze für '{params.query}' auf opendata.swiss gefunden.\n\n"
            "Die Suche läuft über den ganzen Bestand, nicht über einen Herausgeber — "
            "eine leere Antwort heisst hier wirklich, dass es dazu nichts gibt.\n\n"
            "Andere Begriffe, die etwas liefern:\n"
            "- 'Arbeitslosigkeit'\n- 'Stellensuchende'\n- 'Kurzarbeit'\n- 'Erwerbslose ILO'"
        )

    if params.response_format == ResponseFormat.JSON:
        simplified = []
        for ds in datasets:
            simplified.append(
                {
                    "id": ds.get("name", ds.get("id", "")),
                    "title_de": _extract_title(ds.get("title", "")),
                    "publisher": _herausgeber(ds),
                    "metadata_modified": (ds.get("metadata_modified") or "")[:10],
                    "resource_count": len(ds.get("resources", [])),
                    "resources": [
                        {
                            "format": r.get("format", ""),
                            "name": _extract_title(r.get("name", "")),
                            "url": r.get("url", ""),
                        }
                        for r in ds.get("resources", [])[:5]
                    ],
                }
            )
        return json.dumps(simplified, ensure_ascii=False, indent=2)

    return _format_datasets_markdown(datasets)


# ---------------------------------------------------------------------------
# Tool 2: Get specific SECO dataset details
# ---------------------------------------------------------------------------


@mcp.tool(
    name="seco_get_dataset",
    annotations={
        "title": "SECO-Datensatz-Details abrufen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def seco_get_dataset(params: DatasetDetailsInput) -> str:
    """Fetch full details and download links for a specific SECO dataset.

    Use this after seco_search_datasets to get complete metadata and
    all resource download URLs for a dataset.

    Args:
        params (DatasetDetailsInput): Contains:
            - dataset_id (str): Dataset ID/slug from opendata.swiss
            - response_format (str): 'markdown' or 'json'

    Returns:
        str: Full dataset metadata including all resource download URLs.
    """
    try:
        result = await _ckan_get_dataset(params.dataset_id)
    except Exception as e:
        return _to_execution_error(e)

    if not result.get("success"):
        return (
            f"Error: Dataset '{params.dataset_id}' not found on opendata.swiss.\n"
            "Use seco_search_datasets to find valid dataset IDs."
        )

    ds = _ckan_result(result, "package_show")
    title = _extract_title(ds.get("title", ""))
    notes = _extract_title(ds.get("notes", ""))
    modified = (ds.get("metadata_modified") or "")[:10]
    resources = ds.get("resources", [])
    license_title = ds.get("license_title", "")
    tags = [_extract_title(t.get("name", "")) for t in ds.get("tags", [])]

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(
            {
                "id": ds.get("name", ds.get("id", "")),
                "title": title,
                "description": notes,
                "license": license_title,
                "metadata_modified": modified,
                "tags": tags,
                "resources": [
                    {
                        "id": r.get("id", ""),
                        "name": _extract_title(r.get("name", "")),
                        "format": r.get("format", ""),
                        "url": r.get("url", ""),
                        "size": r.get("size"),
                        "last_modified": r.get("last_modified", ""),
                    }
                    for r in resources
                ],
            },
            ensure_ascii=False,
            indent=2,
        )

    # Markdown format
    lines = [
        f"## {title}\n",
        f"**Aktualisiert**: {modified}",
        f"**Lizenz**: {license_title}",
    ]
    if tags:
        lines.append(f"**Schlagwörter**: {', '.join(tags)}")
    if notes:
        lines.append(f"\n**Beschreibung**:\n{notes[:500]}{'…' if len(notes) > 500 else ''}\n")

    lines.append(f"\n### Ressourcen ({len(resources)} Dateien)\n")
    for r in resources:
        fmt = r.get("format", "?")
        rname = _extract_title(r.get("name", ""))
        url = r.get("url", "")
        size = r.get("size")
        # `or ""` statt eines Vorgabewerts: CKAN schickt den Schluessel mit,
        # aber mit `null` — gemessen am 2026-08-14 in 165 von 165 Ressourcen
        # aus 38 Datensaetzen. `.get(k, "")` greift dann nicht, und das
        # anschliessende Schneiden lief auf `None`. Dieses Tool ist daran fuer
        # jeden Datensatz mit Ressourcen abgestuerzt. Dieselbe Form drei Zeilen
        # weiter oben und in zwei anderen Funktionen: gleicher Ausdruck,
        # gleicher Absturz, sobald die Quelle dort ebenfalls `null` schickt.
        last_mod = (r.get("last_modified") or "")[:10]
        size_str = f" ({_fmt_number(size)} Bytes)" if size else ""
        lines.append(f"**[{fmt}]** {rname}{size_str}")
        if last_mod:
            lines.append(f"  Aktualisiert: {last_mod}")
        lines.append(f"  Download: {url}\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 3: Get latest unemployment overview (monthly press data)
# ---------------------------------------------------------------------------


@mcp.tool(
    name="seco_get_unemployment_overview",
    annotations={
        "title": "Aktuelle Arbeitslosigkeit Schweiz",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def seco_get_unemployment_overview(params: UnemploymentInput) -> str:
    """Registrierte Arbeitslose der Schweiz — SECO-Zahlen, publiziert vom BFS.

    Liefert die Jahresreihe der registrierten Arbeitslosen (Jahresdurchschnitt,
    2000 bis heute) aus der BFS-Tabelle `T3.3.0.1`. Die Zahlen stammen aus
    SECOs RAV-System; das BFS veröffentlicht sie und nennt SECO als Quelle.

    **Was dieses Werkzeug nicht liefert:** monatliche Werte und kantonale
    Aufschlüsselungen. Beide gibt es auf opendata.swiss nicht in
    maschinenlesbarer Form — geprüft am 2026-08-14 über den ganzen Bestand.
    Wer sie braucht, findet sie interaktiv auf amstat.ch. Eine Abfrage mit
    `canton` bekommt deshalb eine Absage und keine national aggregierte Zahl,
    die so aussieht, als wäre sie kantonal.

    **Nicht mit der ILO-Erwerbslosigkeit verwechseln.** Dieselbe Tabelle führt
    beide Reihen; die ILO-Zahl lag im Jahr 2000 um 76 Prozent höher. Das
    Werkzeug gibt beide aus und beschriftet sie, statt sie zu vermischen.

    Args:
        params (UnemploymentInput): Contains:
            - canton (Optional[str]): wird abgelehnt, siehe oben.
            - year (Optional[int]): Jahr der Reihe. None = jüngstes verfügbares.
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Jahreswerte mit Herkunftsangabe, oder eine benannte Absage.
    """
    canton_filter = params.canton.upper() if params.canton else None
    if canton_filter and canton_filter not in CANTON_CODES:
        return (
            f"Error: Unknown canton code '{canton_filter}'. "
            f"Valid codes: {', '.join(sorted(CANTON_CODES.keys()))}"
        )
    if canton_filter:
        return _keine_kantonale_reihe(canton_filter, params.response_format)

    try:
        daten = await _bfs_jahresreihe()
    except Exception as e:
        return _to_execution_error(e)

    jahre = daten["years"]
    jahr = params.year or jahre[-1]
    if jahr not in jahre:
        hinweis = (
            f"Jahr {jahr} ist nicht in der Reihe. Verfügbar: {jahre[0]}–{jahre[-1]} "
            "(Jahresdurchschnitte)."
        )
        return (
            json.dumps({"error": hinweis}, ensure_ascii=False, indent=2)
            if params.response_format == ResponseFormat.JSON
            else f"**Kein Wert für {jahr}.** {hinweis}"
        )

    reihen = daten["series"]
    arbeitslose = reihen["registrierte_arbeitslose"].get(jahr)
    stellensuchende = reihen["registrierte_stellensuchende"].get(jahr)
    ilo = reihen["erwerbslose_ilo"].get(jahr)

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(
            {
                "year": jahr,
                "unit": sources.JAHRESREIHE.einheit,
                "registrierte_arbeitslose_seco": arbeitslose,
                "registrierte_stellensuchende_seco": stellensuchende,
                "erwerbslose_ilo_bfs": ilo,
                "series_labels": daten["labels"],
                "years_available": [jahre[0], jahre[-1]],
                "granularity": "annual_national",
                "not_available": {
                    "monthly": "keine maschinenlesbare Quelle (Stand 2026-08-14)",
                    "cantonal": "keine maschinenlesbare Quelle (Stand 2026-08-14)",
                    "where": "https://www.amstat.ch/v2/amstat_de.html",
                },
                "source": sources.herkunftszeile(),
                "data_url": daten["resource_url"],
                "dataset_modified": daten["dataset_modified"],
                "warning": (
                    "Registrierte Arbeitslose (SECO) und Erwerbslose gemäss ILO (BFS) "
                    "sind verschiedene Statistiken und nicht austauschbar."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )

    def _fmt(wert: float | None) -> str:
        return f"{wert * 1000:,.0f}".replace(",", "'") if wert is not None else "–"

    lines = [
        f"## Registrierte Arbeitslose Schweiz — {jahr}\n",
        f"*{sources.JAHRESREIHE.einheit}, national*\n",
        "| Reihe | Wert |",
        "|---|---|",
        f"| Registrierte Arbeitslose (SECO) | {_fmt(arbeitslose)} |",
        f"| Registrierte Stellensuchende (SECO) | {_fmt(stellensuchende)} |",
        f"| Erwerbslose gemäss ILO (BFS) | {_fmt(ilo)} |",
        "",
        "> Die drei Reihen messen **nicht dasselbe**. Registrierte Arbeitslose sind",
        "> beim RAV gemeldet; die ILO-Erwerbslosigkeit stammt aus einer Befragung und",
        "> liegt regelmässig deutlich höher. Nicht ineinander umrechnen.",
        "",
        f"Reihe verfügbar: {jahre[0]}–{jahre[-1]} (Jahresdurchschnitte).",
        "",
        "### Was hier fehlt",
        "",
        "Monatswerte und kantonale Aufschlüsselungen gibt es auf opendata.swiss",
        "nicht maschinenlesbar (geprüft 2026-08-14). Interaktiv stehen sie auf",
        "[amstat.ch](https://www.amstat.ch/v2/amstat_de.html); der Monatsbericht",
        "liegt als PDF auf [arbeit.swiss](https://www.arbeit.swiss/de/informationszentrum/arbeitsmarktstatistik-schweiz).",
        "",
        "---",
        f"{sources.herkunftszeile()}",
        f"Datensatz zuletzt geändert: {daten['dataset_modified']}",
    ]
    return "\n".join(lines)


def _keine_kantonale_reihe(kanton: str, format_: ResponseFormat) -> str:
    """Eine benannte Absage statt einer national aggregierten Zahl.

    Die frühere Fassung zeigte hier eine fest eingetragene Rangliste vom April
    2025 — fünf Kantone, feste Quoten, mit Warnhinweis. Ein Warnhinweis neben
    einer Zahl verliert gegen die Zahl: gelesen wird die Quote, nicht der
    Hinweis. Eine Absage kann man nicht falsch zitieren.
    """
    name = CANTON_CODES.get(kanton, kanton)
    quellen = (
        "https://www.amstat.ch/v2/amstat_de.html",
        "https://www.arbeit.swiss/de/informationszentrum/arbeitsmarktstatistik-schweiz",
    )
    if format_ == ResponseFormat.JSON:
        return json.dumps(
            {
                "canton": kanton,
                "canton_name": name,
                "data_available": False,
                "reason": (
                    "Für kantonale Arbeitslosenzahlen gibt es auf opendata.swiss keine "
                    "maschinenlesbare Quelle (geprüft 2026-08-14). Die nationale "
                    "Jahresreihe steht ohne `canton` zur Verfügung."
                ),
                "where": list(quellen),
            },
            ensure_ascii=False,
            indent=2,
        )
    return "\n".join(
        [
            f"## Kanton {name} ({kanton}) — keine Daten\n",
            "Für **kantonale** Arbeitslosenzahlen gibt es auf opendata.swiss keine",
            "maschinenlesbare Quelle (geprüft 2026-08-14). Dieses Werkzeug gibt",
            "deshalb keine Zahl aus — eine national aggregierte Zahl an dieser Stelle",
            "wäre als kantonale zu lesen und damit falsch.",
            "",
            "Die nationale Jahresreihe liefert dieses Werkzeug ohne `canton`.",
            "",
            "Kantonale Werte gibt es interaktiv auf",
            f"[amstat.ch]({quellen[0]}) und im Monatsbericht auf",
            f"[arbeit.swiss]({quellen[1]}).",
            "",
            "Einzelne Kantone publizieren eigene Reihen auf ihren Portalen; mit",
            "`seco_search_datasets` nach dem Kantonsnamen suchen. Herausgeber und",
            "Erhebungsweise unterscheiden sich dort je Kanton.",
        ]
    )


# ---------------------------------------------------------------------------
# Tool 4: Youth unemployment (Jugendarbeitslosigkeit) – key for Schulamt
# ---------------------------------------------------------------------------


@mcp.tool(
    name="seco_get_youth_unemployment",
    annotations={
        "title": "Jugendarbeitslosigkeit Schweiz",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def seco_get_youth_unemployment(params: YouthUnemploymentInput) -> str:
    """Jugendarbeitslosigkeit (15–24) — zurzeit ohne maschinenlesbare Quelle.

    **Dieses Werkzeug liefert keine Zahlen.** Eine Suche über den ganzen
    Bestand von opendata.swiss nach «Jugendarbeitslosigkeit» ergab am
    2026-08-14 **null** Datensätze; auch die Umschreibungen nach Alter und
    Altersgruppen führen zu keiner Reihe, die 15–24-Jährige als registrierte
    Arbeitslose ausweist. SECO erhebt die Zahl und zeigt sie auf amstat.ch,
    veröffentlicht sie aber nirgends maschinenlesbar.

    Was es stattdessen gibt: die Einordnung, die eine Zahl brauchbar macht —
    das saisonale Muster und was daraus für die Bildungsplanung folgt. Das ist
    Fachwissen und keine Messung, und es steht hier als solches.

    Die frühere Fassung nannte an dieser Stelle «+2'186 Jugendarbeitslose
    (+18.6%)» als Beispielwert aus einem Snapshot. Eine als Beispiel
    eingeführte Zahl wird als Zahl zitiert; der Zusatz «Snapshot» überlebt das
    Zitieren nicht.

    Args:
        params (YouthUnemploymentInput): Contains:
            - canton (Optional[str]): Kantonscode; ändert am Ergebnis nichts.
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Eine benannte Absage samt Bezugsquellen und fachlicher Einordnung.
    """
    canton_filter = params.canton.upper() if params.canton else None
    if canton_filter and canton_filter not in CANTON_CODES:
        return (
            f"Error: Unknown canton code '{canton_filter}'. "
            f"Valid codes: {', '.join(sorted(CANTON_CODES.keys()))}"
        )
    canton_name = CANTON_CODES.get(canton_filter, canton_filter) if canton_filter else None
    scope = f"Kanton {canton_name} ({canton_filter})" if canton_name else "Schweiz national"

    quellen = {
        "amstat": "https://www.amstat.ch/v2/amstat_de.html",
        "monatsbericht": (
            "https://www.arbeit.swiss/de/informationszentrum/arbeitsmarktstatistik-schweiz"
        ),
    }
    saison = [
        "Juli/August: Anstieg — Schulabgängerinnen und Schulabgänger ohne Anschlusslösung",
        "September–November: Rückgang — Lehrstellenantritt und neue Ausbildungen",
        "Die Restgrösse nach November ist das Signal, nicht der Ausschlag im August",
    ]

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(
            {
                "scope": scope,
                "data_available": False,
                "reason": (
                    "Keine maschinenlesbare Quelle für registrierte Jugendarbeitslose "
                    "(15–24) auf opendata.swiss — Suche über den Gesamtbestand am "
                    "2026-08-14: 0 Datensätze. SECO erhebt die Zahl und zeigt sie "
                    "interaktiv auf amstat.ch."
                ),
                "where": quellen,
                "seasonal_pattern_qualitative": saison,
                "note": (
                    "Das saisonale Muster ist fachliche Einordnung, keine Messung. "
                    "Dieses Werkzeug gibt bewusst keine Beispielzahlen aus."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )

    return "\n".join(
        [
            f"## Jugendarbeitslosigkeit (15–24) — {scope}\n",
            "**Keine Zahlen verfügbar.** Für registrierte Jugendarbeitslose gibt es",
            "auf opendata.swiss keine maschinenlesbare Quelle: die Suche über den",
            "Gesamtbestand ergab am 2026-08-14 null Datensätze. SECO erhebt die Zahl",
            "und zeigt sie interaktiv auf amstat.ch, publiziert sie aber nicht als",
            "Datei.",
            "",
            "Dieses Werkzeug gibt deshalb keine Beispiel- oder Referenzwerte aus. Eine",
            "als Beispiel eingeführte Zahl wird als Zahl zitiert.",
            "",
            "### Wo die Zahlen stehen",
            "",
            f"- [amstat.ch – Arbeitslose nach Alter]({quellen['amstat']}) (interaktiv)",
            f"- [Monatsbericht «Die Lage auf dem Arbeitsmarkt»]({quellen['monatsbericht']}) (PDF)",
            "",
            "### Saisonales Muster (fachliche Einordnung, keine Messung)",
            "",
            *[f"- {s}" for s in saison],
            "",
            "### Was daraus für die Bildungsplanung folgt",
            "",
            "| Beobachtung | Bedeutung für das Schulamt |",
            "|---|---|",
            "| Hohe August-Quote in einer Berufsgruppe | Brückenangebote in dieser Richtung stärken |",
            "| Steigende Jahresquote 15–24 | Berufswahlvorbereitung früher ansetzen |",
            "| Kanton über dem Schweizer Schnitt | Zusammenarbeit mit dem RAV prüfen |",
            "| Beruf mit Stellenmeldepflicht | in der Beratung eigens ansprechen |",
            "",
            "Diese Zeilen sind Lesehilfen für eigene Zahlen — sie ersetzen sie nicht.",
        ]
    )


# ---------------------------------------------------------------------------
# Tool 5: Job seekers (Stellensuchende)
# ---------------------------------------------------------------------------


@mcp.tool(
    name="seco_get_job_seekers",
    annotations={
        "title": "Stellensuchende Schweiz",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def seco_get_job_seekers(params: JobSeekersInput) -> str:
    """Registrierte Stellensuchende — SECO-Zahlen, publiziert vom BFS.

    Stellensuchende ist die weitere Kategorie: sie schliesst Personen in
    Umschulung, Beschäftigungsprogrammen und anderen ALV-Massnahmen ein, die
    nicht als arbeitslos gezählt werden. Der Abstand zwischen beiden Reihen ist
    die eigentliche Aussage — er sagt, wie viele Menschen das System gerade
    begleitet, ohne dass sie in der Arbeitslosenquote auftauchen.

    Dieselbe Tabelle wie `seco_get_unemployment_overview` (BFS `T3.3.0.1`),
    Jahresdurchschnitte ab 2000, national. Kantonale und monatliche Werte gibt
    es dort nicht; `canton` bekommt deshalb eine Absage statt einer nationalen
    Zahl im kantonalen Gewand.

    Args:
        params (JobSeekersInput): Contains:
            - canton (Optional[str]): wird abgelehnt, siehe oben.
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Jahreswerte beider Reihen samt Abstand, mit Herkunftsangabe.
    """
    canton_filter = params.canton.upper() if params.canton else None
    if canton_filter and canton_filter not in CANTON_CODES:
        return (
            f"Error: Unknown canton code '{canton_filter}'. "
            f"Valid codes: {', '.join(sorted(CANTON_CODES.keys()))}"
        )
    if canton_filter:
        return _keine_kantonale_reihe(canton_filter, params.response_format)

    try:
        daten = await _bfs_jahresreihe()
    except Exception as e:
        return _to_execution_error(e)

    jahre = daten["years"]
    jahr = jahre[-1]
    stellensuchende = daten["series"]["registrierte_stellensuchende"].get(jahr)
    arbeitslose = daten["series"]["registrierte_arbeitslose"].get(jahr)
    differenz = (
        stellensuchende - arbeitslose
        if stellensuchende is not None and arbeitslose is not None
        else None
    )

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(
            {
                "year": jahr,
                "unit": sources.JAHRESREIHE.einheit,
                "registrierte_stellensuchende_seco": stellensuchende,
                "registrierte_arbeitslose_seco": arbeitslose,
                "differenz_in_massnahmen": differenz,
                "series_labels": daten["labels"],
                "years_available": [jahre[0], jahre[-1]],
                "granularity": "annual_national",
                "not_available": {
                    "monthly": "keine maschinenlesbare Quelle (Stand 2026-08-14)",
                    "cantonal": "keine maschinenlesbare Quelle (Stand 2026-08-14)",
                    "where": "https://www.amstat.ch/v2/amstat_de.html",
                },
                "source": sources.herkunftszeile(),
                "data_url": daten["resource_url"],
            },
            ensure_ascii=False,
            indent=2,
        )

    def _fmt(wert: float | None) -> str:
        return f"{wert * 1000:,.0f}".replace(",", "'") if wert is not None else "–"

    anteil = (
        f"{differenz / stellensuchende * 100:.0f}%"
        if differenz is not None and stellensuchende
        else "–"
    )
    return "\n".join(
        [
            f"## Registrierte Stellensuchende Schweiz — {jahr}\n",
            f"*{sources.JAHRESREIHE.einheit}, national*\n",
            "| Reihe | Wert |",
            "|---|---|",
            f"| Registrierte Stellensuchende (SECO) | {_fmt(stellensuchende)} |",
            f"| davon registrierte Arbeitslose (SECO) | {_fmt(arbeitslose)} |",
            f"| Differenz: in Massnahmen oder Zwischenverdienst | {_fmt(differenz)} ({anteil}) |",
            "",
            "> Die Differenz ist die eigentliche Aussage dieser Reihe: Menschen, die das",
            "> System begleitet, ohne dass sie in der Arbeitslosenquote erscheinen.",
            "",
            f"Reihe verfügbar: {jahre[0]}–{jahre[-1]} (Jahresdurchschnitte).",
            "Monats- und Kantonswerte sind nicht maschinenlesbar verfügbar",
            "(geprüft 2026-08-14) — interaktiv auf",
            "[amstat.ch](https://www.amstat.ch/v2/amstat_de.html).",
            "",
            "---",
            f"{sources.herkunftszeile()}",
        ]
    )


# ---------------------------------------------------------------------------
# Tool 6: Open positions (Offene Stellen)
# ---------------------------------------------------------------------------


@mcp.tool(
    name="seco_get_open_positions",
    annotations={
        "title": "Offene Stellen Schweiz (SECO)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def seco_get_open_positions(params: OpenPositionsInput) -> str:
    """Get open job positions (Offene Stellen) statistics from SECO/AMSTAT.

    Open positions data is a leading indicator for labor market demand –
    relevant for identifying which professions/sectors to emphasize in
    vocational guidance and which Lehrberufe are in high demand.

    Args:
        params (OpenPositionsInput): Contains:
            - response_format (str): 'markdown' or 'json'

    Returns:
        str: Open positions trends and interpretation for educational planning.
             Includes which sectors are hiring and notes on Stellenmeldepflicht.
    """
    try:
        search_result = await _ckan_search("offene Stellen Vakanzen", limit=5)
        datasets = _ckan_results(search_result)
    except Exception:
        datasets = []

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(
            {
                "indicator_type": "leading_indicator",
                "note": (
                    "Offene Stellen sind ein Frühindikator – steigende Vakanzen "
                    "signalisieren Nachfrage, sinkende Vakanzen warnen vor Stellenabbau."
                ),
                "stellenmeldepflicht": {
                    "description": (
                        "Seit 2020: Berufe mit ≥5% Arbeitslosenquote meldepflichtig. "
                        "Liste ändert sich jährlich."
                    ),
                    "source": "SECO – Stellenmeldepflicht",
                },
                "data_available": False,
                "reason": (
                    "Keine maschinenlesbare nationale Reihe für gemeldete offene "
                    "Stellen auf opendata.swiss (geprüft 2026-08-14). Einzelne "
                    "Kantone publizieren eigene Reihen; siehe datasets_found."
                ),
                "datasets_found": [
                    {
                        "id": ds.get("name", ""),
                        "title": _extract_title(ds.get("title", "")),
                        "publisher": _herausgeber(ds),
                    }
                    for ds in datasets[:3]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )

    lines = [
        "## Offene Stellen – Schweiz\n",
        "> **Keine nationale Reihe verfügbar.** Für gemeldete offene Stellen gibt es",
        "> auf opendata.swiss keine maschinenlesbare nationale Quelle (geprüft",
        "> 2026-08-14). Einzelne Kantone publizieren eigene Reihen — siehe die",
        "> Trefferliste unten, mit Herausgeber. Was hier steht, ist die Einordnung",
        "> des Indikators, keine Messung.\n",
        "> **Eselsbrücke**: Offene Stellen = Thermometer des Arbeitsmarkts.",
        "> Steigt die Temperatur → mehr Nachfrage; sinkt sie → Abkühlung.\n",
        "### Strategische Bedeutung für Berufsberatung\n",
        "Offene Stellen sind ein **Frühindikator** für Berufswahlempfehlungen:\n",
        "| Signal | Interpretation | Empfehlung Schulamt |",
        "|--------|----------------|---------------------|",
        "| Hohe Vakanzen Gesundheitsberufe | Anhaltender Fachkräftemangel | Stärker bewerben |",
        "| Sinkende Vakanzen Industrie | Strukturwandel/Automatisierung | Weiterbildung betonen |",
        "| Stellenmeldepflicht-Berufe | ≥5% Quote → Vorrang CH-Arbeitnehmende | Beratungsfokus |",
        "| Wachstum ICT/Digitalisierung | Dauerhaft hohe Nachfrage | Informatik-Lehrberufe |",
        "\n### Stellenmeldepflicht (ab 2020)\n",
        "Berufe mit Arbeitslosenquote ≥ 5% sind **meldepflichtig**:",
        "- Offene Stellen müssen 5 Arbeitstage dem RAV gemeldet werden",
        "- RAV vermittelt zuerst Stellensuchende (Inländervorrang)",
        "- Liste der Berufe ändert sich **jährlich** (SECO Publikation)",
        "- Aktuelle Liste: [arbeit.swiss Stellenmeldepflicht](https://www.arbeit.swiss)",
    ]

    if datasets:
        lines.append("\n### Datensätze auf opendata.swiss\n")
        for ds in datasets[:3]:
            title = _extract_title(ds.get("title", ""))
            ds_id = ds.get("name", ds.get("id", ""))
            lines.append(f"- **{title}** → `seco_get_dataset('{ds_id}')`")

    lines.append(
        "\n*Detaildaten: `seco_search_datasets('offene Stellen')` oder "
        "`seco_search_datasets('Vakanzen Berufsgruppen')`*"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 7: Monthly press report URL generator
# ---------------------------------------------------------------------------


@mcp.tool(
    name="seco_get_monthly_report_url",
    annotations={
        "title": "SECO Monatsbericht-URL generieren",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def seco_get_monthly_report_url(params: MonthlyReportInput) -> str:
    """Generate and validate URL for SECO monthly labor market press report.

    SECO publishes monthly press documentation 'Die Lage auf dem Arbeitsmarkt'
    as PDF. This tool constructs the URL for a specific month/year and
    verifies availability.

    Args:
        params (MonthlyReportInput): Contains:
            - year (int): Report year (e.g. 2025, 2026)
            - month (int): Report month (1-12)
            - language (str): 'de', 'fr', or 'it'

    Returns:
        str: PDF URL and availability status for the requested monthly report.

    Note:
        Reports are published on the first Thursday of the following month.
        Example: January 2026 data → published February 6, 2026.
    """
    month_names_display = [
        "",
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ]

    # URL patterns vary; try the known arbeit.swiss DAM pattern
    month_str = f"{params.month:02d}"
    year_str = str(params.year)

    # Pattern for recent reports (2025+)
    url_pattern = (
        f"https://www.arbeit.swiss/dam/secoalv/de/dokumente/publikationen/amstat/"
        f"{year_str}/{year_str}-{month_str}_die_lage_auf_dem_arbeitsmarkt.pdf"
        f".download.pdf/{year_str}-{month_str}_Die_Lage_auf_dem_Arbeitsmarkt_DE.pdf"
    )

    # Check availability (SEC-004: validate URL even though we constructed it
    # — defense-in-depth against future code changes that introduce variable hosts).
    available = False
    try:
        await _validate_external_url(url_pattern)
        async with _client_scope() as client:
            resp = await client.head(url_pattern, timeout=10.0)
            available = resp.status_code == 200
    except Exception:
        available = False

    period = f"{month_names_display[params.month]} {params.year}"

    lines = [
        f"## SECO Monatsbericht – {period}\n",
        f"**PDF-URL**: {url_pattern}\n",
        f"**Verfügbar**: {'✅ Ja' if available else '⚠️ Nicht direkt verfügbar (URL-Muster kann abweichen)'}\n",
        "### Hinweise\n",
        f"- Berichtszeitraum: {period}",
        "- Veröffentlichung: jeweils 1. Donnerstag des Folgemonats",
        "- Sprachen: DE / FR / IT",
        "- Enthält: Arbeitslose, Stellensuchende, Kurzarbeit, Offene Stellen\n",
        "### Alternative Quellen\n",
        "- [SECO Medienmitteilungen](https://www.seco.admin.ch/seco/de/home/Arbeit/"
        "Arbeitslosenversicherung/arbeitslosenzahlen.html)",
        "- [arbeit.swiss Medienmitteilungen](https://www.arbeit.swiss/secoalv/de/home/"
        "menue/institutionen-medien/medienmitteilungen.html)",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 8: Unemployment by occupation/profession (Berufsgruppen)
# ---------------------------------------------------------------------------


@mcp.tool(
    name="seco_get_unemployment_by_occupation",
    annotations={
        "title": "Arbeitslosigkeit nach Berufsgruppe",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def seco_get_unemployment_by_occupation(params: OccupationInput) -> str:
    """Get unemployment statistics broken down by occupation/profession (Berufshauptgruppe).

    This is the most directly relevant tool for Berufswahlberatung – it shows
    which professions have high unemployment rates, which sectors are declining,
    and which Lehrberufe lead to stable employment outcomes.

    Args:
        params (OccupationInput): Contains:
            - response_format (str): 'markdown' for human-readable, 'json' for structured data.

    Returns:
        str: Unemployment by major occupational group (Berufshauptgruppe).
             Includes Stellenmeldepflicht status and implications for
             apprenticeship market counseling.

    Schema (JSON):
        {
            "occupational_groups": [
                {
                    "group": str,
                    "unemployment_rate_pct": float,
                    "stellenmeldepflicht": bool,
                    "trend": str
                }
            ],
            "source": str,
            "education_implications": [str]
        }
    """
    try:
        search_result = await _ckan_search("Berufshauptgruppe Berufsgruppe arbeitslose", limit=5)
        datasets = _ckan_results(search_result)
    except Exception:
        datasets = []

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(
            {
                "data_available": False,
                "note": (
                    "Keine maschinenlesbare Quelle für Arbeitslose nach "
                    "Berufshauptgruppe (geprüft 2026-08-14). SECO weist die "
                    "Gliederung im Monatsbericht aus und zeigt sie interaktiv auf "
                    "amstat.ch; als Datei publiziert wird sie nicht."
                ),
                "stellenmeldepflicht_threshold": "≥5% Arbeitslosenquote",
                "data_source": "SECO Arbeitsmarktstatistik, NOGA-Gliederung 2008",
                "datasets_found": [
                    {"id": ds.get("name", ""), "title": _extract_title(ds.get("title", ""))}
                    for ds in datasets[:3]
                ],
                "education_implications": [
                    "Berufe mit hoher Quote → stärken Brückenangebote / Beratung",
                    "Berufe mit Stellenmeldepflicht → Chancen für RAV-Vermittlung",
                    "Wachstumsberufe → in Berufswahlinformationen hervorheben",
                    "Rückgangsberufe → Umschulungsberatung vorbereiten",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )

    lines = [
        "## Arbeitslosigkeit nach Berufshauptgruppe\n",
        "> *Das goldene Werkzeug für Berufswahlberatung:*",
        "> Nicht alle Berufe sind gleich – diese Daten zeigen, wo Jobs sind und wo nicht.\n",
        "### Gliederungssystem: NOGA 2008\n",
        "SECO gliedert nach der Allgemeinen Systematik der Wirtschaftszweige (NOGA 2008).\n",
        "### Berufshauptgruppen mit höchster Relevanz für Schulamt ZH\n",
        "| Berufsgruppe | Tendenz | Relevanz Berufswahlberatung |",
        "|--------------|---------|------------------------------|",
        "| Gesundheit & Pflege | 📈 hohe Nachfrage | Fachkräftemangel → aktiv empfehlen |",
        "| ICT / Informatik | 📈 stark wachsend | Lehrberufe sehr gefragt |",
        "| Gastronomie / Hotellerie | ⚠️ hohe Quote | Brückenberatung wichtig |",
        "| Bau & Handwerk | ↔ stabil | Solide Lehrstellen |",
        "| Detailhandel | ↘ Strukturwandel | Digitalisierung beachten |",
        "| Verwaltung / Büro | ↔ mit KI-Risiko | Zukunftsperspektive ansprechen |",
        "\n### Stellenmeldepflicht-Berufe\n",
        "Berufe mit ≥ 5% Arbeitslosenquote → RAV-Meldepflicht für offene Stellen:",
        "- Aktuelle Liste jährlich publiziert von SECO",
        "- [Link zur aktuellen Liste](https://www.arbeit.swiss/secoalv/de/home/menue/arbeitgeber/stellenmeldepflicht.html)",
        "- In der Berufsberatung: Jugendliche auf diese Berufe sensibilisieren\n",
        "### Woher die Zahlen kommen\n",
        "**Nicht von hier.** Für Arbeitslose nach Berufshauptgruppe gibt es auf",
        "opendata.swiss keine maschinenlesbare Quelle (geprüft 2026-08-14: die Suche",
        "nach 'Berufshauptgruppe' liefert vier Datensätze, alle vom BFS und alle zu",
        "anderen Fragen). SECO weist die Gliederung im Monatsbericht aus und zeigt",
        "sie interaktiv auf amstat.ch:",
        "",
        "- [amstat.ch – Arbeitslose nach Beruf](https://www.amstat.ch/v2/amstat_de.html)",
        "- [Monatsbericht «Die Lage auf dem Arbeitsmarkt»]"
        "(https://www.arbeit.swiss/de/informationszentrum/arbeitsmarktstatistik-schweiz)",
    ]

    if datasets:
        lines.append("\n### Gefundene Datensätze\n")
        for ds in datasets[:3]:
            title = _extract_title(ds.get("title", ""))
            ds_id = ds.get("name", ds.get("id", ""))
            lines.append(f"- **{title}** → `{ds_id}`")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 9: Cantons overview
# ---------------------------------------------------------------------------


@mcp.tool(
    name="seco_list_cantons",
    annotations={
        "title": "Schweizer Kantone – Codes und Namen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def seco_list_cantons() -> str:
    """List all Swiss canton codes and their names.

    Utility tool to look up canton codes needed for other seco_* tools.
    Returns all 26 cantons with their 2-letter codes and full names.

    Returns:
        str: Markdown table of canton codes and names.
    """
    lines = [
        "## Schweizer Kantone – Codes und Namen\n",
        "| Code | Kanton | Sprachregion |",
        "|------|--------|--------------|",
    ]
    regions = {
        "ZH": "de",
        "BE": "de/fr",
        "LU": "de",
        "UR": "de",
        "SZ": "de",
        "OW": "de",
        "NW": "de",
        "GL": "de",
        "ZG": "de",
        "FR": "de/fr",
        "SO": "de",
        "BS": "de",
        "BL": "de",
        "SH": "de",
        "AR": "de",
        "AI": "de",
        "SG": "de",
        "GR": "de/rm/it",
        "AG": "de",
        "TG": "de",
        "TI": "it",
        "VD": "fr",
        "VS": "de/fr",
        "NE": "fr",
        "GE": "fr",
        "JU": "fr",
    }
    for code, name in sorted(CANTON_CODES.items()):
        region = regions.get(code, "de")
        lines.append(f"| **{code}** | {name} | {region} |")

    lines.append("\n*Verwende diese Codes in `canton`-Parametern anderer seco_*-Tools.*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tools 10-12: Unfallstatistik UVG (SSUV)
# ---------------------------------------------------------------------------
#
# Datenquelle ist NICHT das SECO, sondern die Koordinationsgruppe KSUV und die
# Sammelstelle SSUV c/o Suva. Das Praefix seco_ adressiert diesen Server, nicht
# den Herausgeber; die Quellenangabe im Envelope nennt ihn ausdruecklich.


def _uvg_value(value: Any) -> str:
    """Zahlformat der Quelle: Apostroph als Tausender-, Komma als Dezimaltrenner.

    Nicht _fmt_number verwenden — das castet auf int und macht aus einer
    Lohnsumme von 359,7 Mrd. stillschweigend 359.
    """
    if value is None:
        return "–"
    if isinstance(value, bool) or not isinstance(value, int | float):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}".replace(",", "'")
    text = f"{value:,.1f}".replace(",", "\x00").replace(".", ",").replace("\x00", "'")
    return text


def _uvg_markdown(envelope: dict[str, Any], title: str, body: list[str]) -> str:
    """Markdown-Ausgabe mit Provenienz-Fuss.

    Die Envelope-Felder gehen auch in die Markdown-Fassung: Sie sind das
    Einzige, was das Modell tatsaechlich zu sehen bekommt — ein README wird
    nicht weitergereicht, und die Nicht-kommerziell-Klausel der Quelle darf
    nicht an der Formatwahl haengen.
    """
    lines = [f"## {title}\n"]
    if envelope.get("degraded"):
        lines.append(f"> **Quelle nicht erreichbar.** {envelope.get('note', '')}\n")
        return "\n".join(lines)
    if envelope.get("hint"):
        lines.append(f"> **Kein Treffer.** {envelope['hint']}\n")
    lines.extend(body)
    freshness = envelope.get("source_freshness") or {}
    lines.append("\n---\n")
    lines.append(f"**Quelle**: {envelope['source']}")
    parts = [f"`{k}`: {v}" for k, v in freshness.items() if v not in (None, [], {})]
    if parts:
        lines.append(f"**Stand**: {' · '.join(parts)}")
    lines.append(
        f"**Provenance**: `{envelope['provenance']}` · **Abruf**: {envelope['retrieved_at']}"
    )
    return "\n".join(lines)


class UvgOverviewInput(BaseModel):
    """Input for UVG key figures (Switzerland-wide)."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    years: int = Field(
        default=5,
        description="Number of most recent years to return (1-5). The source publishes five.",
        ge=1,
        le=5,
    )
    include_non_occupational: bool = Field(
        default=False,
        description=(
            "Also report non-occupational (leisure) accidents NBUV, UVAL and UV IV. "
            "Default False: this server covers the labour market, leisure accidents are context."
        ),
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'.",
    )


class UvgBranchInput(BaseModel):
    """Input for UVG results by economic branch (NOGA 2008)."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    noga: str | None = Field(
        default=None,
        description=(
            "NOGA 2008 code, e.g. '43' (finishing trade), '86' (health), '85' (education). "
            "The publication groups some divisions ('01 - 03', '41 - 42', '77, 79 - 82'); a "
            "query for '42' matches the row '41 - 42'. "
            "OMITTING THIS RETURNS THE COMPLETE GRID — all branch rows, the three sector "
            "totals and the category 'Unbekannt'. It filters nothing out."
        ),
        max_length=20,
    )
    table: str = Field(
        default="2.4_BUV",
        description=(
            "Which published table to read. '2.4_BUV' = accepted occupational-accident and "
            "occupational-disease cases, disability pensions, fatalities, running costs. "
            "'2.4_NBUV' = same for non-occupational accidents. '1.2' = insured full-time "
            "equivalents and accident risk per 1000 FTE."
        ),
        pattern=r"^(2\.4_BUV|2\.4_NBUV|1\.2)$",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'.",
    )


class UvgTrendInput(BaseModel):
    """Input for the ten-year branch time series."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    noga: str = Field(
        ...,
        description=(
            "Two-digit NOGA 2008 division, e.g. '43', '86', '85'. Ranges such as '41 - 42' "
            "exist only in the annual table (seco_get_uvg_by_branch), not in the time series. "
            "Not every number is occupied (04, 05, 07, 09 are absent)."
        ),
        min_length=1,
        max_length=8,
    )
    branch_type: str = Field(
        default="BUV",
        description="'BUV' = occupational accident insurance, 'NBUV' = non-occupational.",
        pattern=r"^(BUV|NBUV|buv|nbuv)$",
    )
    indicator: str | None = Field(
        default=None,
        description=(
            "Case-insensitive substring match against the indicator name, no wildcards. "
            "Examples: 'Fallrisiko', 'Berufskrankheiten', 'Todesfälle'. "
            "Omit to return all twelve indicators."
        ),
        max_length=80,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'.",
    )


@mcp.tool(
    name="seco_get_uvg_overview",
    annotations={
        "title": "Berufsunfälle und Berufskrankheiten – Schlüsselzahlen (UVG/SSUV)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def seco_get_uvg_overview(params: UvgOverviewInput) -> str:
    """Switzerland-wide key figures on occupational accidents and diseases (UVG).

    Covers all 22 Swiss accident insurers: registered and accepted cases,
    accepted occupational diseases, disability pensions, fatalities and costs
    over the five most recent years.

    Published by KSUV/SSUV c/o Suva — not by SECO. Complements the unemployment
    tools of this server: same labour market, risk side instead of demand side.

    Args:
        params (UvgOverviewInput): years, include_non_occupational, response_format

    Returns:
        str: Key figures with source, provenance and publication date.
    """
    envelope = await uvg_overview_impl(
        years=params.years, include_nbuv=params.include_non_occupational
    )
    if params.response_format == ResponseFormat.JSON:
        return json.dumps(envelope, ensure_ascii=False, indent=2)

    body: list[str] = []
    section = None
    for row in envelope.get("rows", []):
        if row["section"] != section:
            section = row["section"]
            years = [v["year"] for v in row["values"]]
            body.append(f"\n### {section}\n")
            body.append("| Kennzahl | Einheit | " + " | ".join(str(y) for y in years) + " |")
            body.append("|---|---|" + "---|" * len(years))
        values = " | ".join(_uvg_value(v["value"]) for v in row["values"])
        body.append(f"| {row['label']} | {row['unit'] or ''} | {values} |")
    return _uvg_markdown(envelope, "Unfallstatistik UVG – Schlüsselzahlen Schweiz", body)


@mcp.tool(
    name="seco_get_uvg_by_branch",
    annotations={
        "title": "Berufsunfälle nach Wirtschaftszweig NOGA (UVG/SSUV)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def seco_get_uvg_by_branch(params: UvgBranchInput) -> str:
    """Occupational accident and disease results per economic branch (NOGA 2008).

    Answers which branches carry which accident risk — the counterpart to
    seco_get_unemployment_by_occupation for vocational guidance: a Lehrberuf
    recommendation can weigh demand against occupational risk.

    Every response carries a totals check: the parsed rows are summed and
    compared against the total printed in the publication.

    Args:
        params (UvgBranchInput): noga, table, response_format

    Returns:
        str: Branch rows including sector totals and the category 'Unbekannt'.
    """
    envelope = await uvg_by_branch_impl(noga=params.noga, table=params.table)
    if params.response_format == ResponseFormat.JSON:
        return json.dumps(envelope, ensure_ascii=False, indent=2)

    columns = envelope.get("columns", [])
    body: list[str] = []
    rows = envelope.get("rows", [])
    if rows:
        body.append("| Code | Wirtschaftszweig | " + " | ".join(columns) + " |")
        body.append("|---|---|" + "---|" * len(columns))
        for row in rows:
            marker = "**" if row.get("row_type") == "sector" else ""
            code = row.get("code") or ""
            values = " | ".join(_uvg_value(row.get(c)) for c in columns)
            body.append(f"| {code} | {marker}{row['label']}{marker} | {values} |")
    check = envelope.get("totals_check") or {}
    if check.get("available"):
        verdict = "stimmt exakt" if check["match"] else f"Abweichung {check['delta']:+d}"
        body.append(
            f"\n*Summenprobe ({check['field']}): Zeilen {_uvg_value(check['sum_rows'])} vs. "
            f"gedrucktes Total {_uvg_value(check['printed_total'])} — {verdict}.*"
        )
    return _uvg_markdown(envelope, "Unfallstatistik UVG – nach Wirtschaftszweig", body)


@mcp.tool(
    name="seco_get_uvg_trends",
    annotations={
        "title": "Unfallgeschehen Zeitreihe nach Branche (UVG/SSUV)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def seco_get_uvg_trends(params: UvgTrendInput) -> str:
    """Ten-year time series of accident indicators for one NOGA branch.

    Twelve indicators per branch, among them case risk per 1000 full-time
    equivalents, occupational diseases per 100'000, severe accidents,
    disability pensions and fatalities.

    Each data point carries a `significant` flag: the source marks statistically
    significant year-on-year changes with an asterisk. Report a change as
    significant only where that flag is set.

    Args:
        params (UvgTrendInput): noga, branch_type, indicator, response_format

    Returns:
        str: Time series per indicator with mean and trend.
    """
    envelope = await uvg_trends_impl(
        noga=params.noga, branch_type=params.branch_type, indicator=params.indicator
    )
    if params.response_format == ResponseFormat.JSON:
        return json.dumps(envelope, ensure_ascii=False, indent=2)

    indicators = envelope.get("indicators", [])
    body: list[str] = []
    if indicators:
        label = envelope.get("branch_label") or ""
        body.append(
            f"**NOGA {envelope.get('noga')} – {label}** ({envelope.get('insurance_branch')})\n"
        )
        years = [p["year"] for p in indicators[0]["series"]]
        body.append("| Kennzahl | " + " | ".join(str(y) for y in years) + " | Mittel | Trend |")
        body.append("|---|" + "---|" * (len(years) + 2))
        for ind in indicators:
            cells = []
            for point in ind["series"]:
                mark = "*" if point["significant"] else ""
                cells.append(f"{point['value']}{mark}")
            body.append(
                f"| {ind['indicator']} | "
                + " | ".join(cells)
                + f" | {ind['mean']} | {ind['trend_pct']}% |"
            )
        body.append("\n*\\* = statistisch signifikante Veränderung gegenüber dem Vorjahr.*")
    return _uvg_markdown(envelope, "Unfallstatistik UVG – Zeitreihe nach Branche", body)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        # SEC-016: bind to loopback by default. Container deployments
        # must explicitly set HOST=0.0.0.0 (see Dockerfile/README).
        mcp.settings.host = os.environ.get("HOST", "127.0.0.1")
        mcp.settings.port = int(os.environ.get("PORT", "8000"))
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
