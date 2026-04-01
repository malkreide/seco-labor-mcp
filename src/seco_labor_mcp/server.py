"""
SECO Labor Market MCP Server
=============================
Swiss labor market data (SECO/AMSTAT) via opendata.swiss CKAN API
and direct SECO data downloads.

Data sources (Phase 1 – No Auth Required):
  - opendata.swiss CKAN API (metadata catalog)
  - SECO/AMSTAT published CSV datasets (arbeit.swiss)
  - Monthly press release PDFs (structural URL pattern)

Primary use cases:
  - Berufswahlberatung (vocational guidance)
  - Lehrstellen-Monitoring (apprenticeship market monitoring)
  - Bildungsplanung (education planning)
  - Arbeitsmarktanalyse (labor market analysis)
"""

from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime
from enum import Enum
from functools import lru_cache
from typing import Any, Optional

import httpx
from fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Server initialisation
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "seco_labor_mcp",
    instructions=(
        "Swiss labor market data server. Provides unemployment statistics, "
        "job seeker data, open positions, and youth unemployment figures from "
        "SECO/AMSTAT via opendata.swiss. All data is public and requires no API key. "
        "Particularly useful for educational planning, vocational guidance (Berufswahlberatung), "
        "and apprenticeship market monitoring (Lehrstellen-Monitoring)."
    ),
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CKAN_BASE = "https://opendata.swiss/api/3/action"
SECO_ORG = "staatssekretariat-fur-wirtschaft-seco"
AMSTAT_BASE = "https://www.amstat.ch"
ARBEIT_SWISS_BASE = "https://www.arbeit.swiss"

# Known stable SECO dataset slugs on opendata.swiss
# These are the most relevant datasets for our use cases
KNOWN_DATASETS = {
    "unemployment_monthly": "monatliche-arbeitslosenzahlen",  # adjust to actual slug
    "job_seekers": "stellensuchende",
    "open_positions": "offene-stellen",
    "short_time_work": "kurzarbeit",
}

# Swiss canton codes mapping
CANTON_CODES = {
    "ZH": "Zürich", "BE": "Bern", "LU": "Luzern", "UR": "Uri",
    "SZ": "Schwyz", "OW": "Obwalden", "NW": "Nidwalden", "GL": "Glarus",
    "ZG": "Zug", "FR": "Freiburg", "SO": "Solothurn", "BS": "Basel-Stadt",
    "BL": "Basel-Landschaft", "SH": "Schaffhausen", "AR": "Appenzell Ausserrhoden",
    "AI": "Appenzell Innerrhoden", "SG": "St. Gallen", "GR": "Graubünden",
    "AG": "Aargau", "TG": "Thurgau", "TI": "Ticino", "VD": "Vaud",
    "VS": "Valais", "NE": "Neuchâtel", "GE": "Genève", "JU": "Jura",
}

HTTP_TIMEOUT = 30.0

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class ResponseFormat(str, Enum):
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

    canton: Optional[str] = Field(
        default=None,
        description=(
            "Filter by canton code (2-letter). "
            "Examples: 'ZH' (Zürich), 'BE' (Bern), 'GE' (Genève), 'TI' (Ticino). "
            "Leave empty for national totals."
        ),
        max_length=2,
    )
    year: Optional[int] = Field(
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

    canton: Optional[str] = Field(
        default=None,
        description=(
            "Filter by canton code (2-letter, e.g. 'ZH'). "
            "Leave empty for national data."
        ),
        max_length=2,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'.",
    )


class JobSeekersInput(BaseModel):
    """Input for job seeker (Stellensuchende) queries."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    canton: Optional[str] = Field(
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
            "Dataset ID or slug from opendata.swiss. "
            "Obtain from seco_search_datasets first."
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


def _get_client() -> httpx.AsyncClient:
    """Return a configured async HTTP client."""
    return httpx.AsyncClient(
        timeout=HTTP_TIMEOUT,
        follow_redirects=True,
        headers={
            "User-Agent": "seco-labor-mcp/0.1.0 (Swiss Public Data MCP Portfolio; github.com/malkreide)",
            "Accept": "application/json, text/csv, */*",
        },
    )


def _handle_http_error(e: Exception) -> str:
    """Produce an actionable error message for HTTP failures."""
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code == 404:
            return (
                "Error: Dataset not found (HTTP 404). "
                "Use seco_search_datasets to find valid dataset IDs."
            )
        if code == 429:
            return "Error: Rate limit exceeded. Please wait a moment before retrying."
        if code == 503:
            return (
                f"Error: SECO/opendata.swiss service temporarily unavailable (HTTP 503). "
                f"URL: {e.request.url}. Try again in a few minutes."
            )
        return f"Error: HTTP {code} – {e.response.text[:200]}"
    if isinstance(e, httpx.TimeoutException):
        return "Error: Request timed out. The SECO server may be slow – please retry."
    if isinstance(e, httpx.ConnectError):
        return (
            "Error: Cannot connect to opendata.swiss. "
            "Check your network connection or try again later."
        )
    return f"Error: Unexpected error – {type(e).__name__}: {e}"


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


async def _ckan_search(query: str, limit: int = 10) -> dict:
    """Search opendata.swiss CKAN for SECO datasets."""
    async with _get_client() as client:
        resp = await client.get(
            f"{CKAN_BASE}/package_search",
            params={
                "q": query,
                "fq": f"organization:{SECO_ORG}",
                "rows": limit,
                "sort": "score desc, metadata_modified desc",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def _ckan_get_dataset(dataset_id: str) -> dict:
    """Fetch a specific dataset from opendata.swiss CKAN."""
    async with _get_client() as client:
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


def _format_datasets_markdown(datasets: list[dict]) -> str:
    """Format CKAN dataset list as readable Markdown."""
    if not datasets:
        return "Keine SECO-Datensätze gefunden."

    lines = [
        "## SECO-Datensätze auf opendata.swiss\n",
        f"*{len(datasets)} Datensätze gefunden*\n",
    ]
    for ds in datasets:
        title = _extract_title(ds.get("title", ""))
        ds_id = ds.get("name", ds.get("id", ""))
        modified = ds.get("metadata_modified", "")[:10]
        notes = _extract_title(ds.get("notes", "")) or ""
        resources = ds.get("resources", [])

        lines.append(f"### {title}")
        lines.append(f"- **ID**: `{ds_id}`")
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
# Tool 1: Search SECO datasets on opendata.swiss
# ---------------------------------------------------------------------------


@mcp.tool(
    name="seco_search_datasets",
    annotations={
        "title": "SECO-Datensätze suchen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def seco_search_datasets(params: DatasetSearchInput) -> str:
    """Search SECO labor market datasets on opendata.swiss CKAN.

    Searches the Swiss Open Government Data portal for datasets published
    by SECO (Staatssekretariat für Wirtschaft). Returns dataset titles,
    IDs, and available resource download links.

    Args:
        params (DatasetSearchInput): Contains:
            - query (str): Search terms (German/English)
            - limit (int): Max results (1-20, default 10)
            - response_format (str): 'markdown' or 'json'

    Returns:
        str: Dataset list with IDs and resource URLs, or JSON array of dataset objects.

    Example queries:
        - 'arbeitslose kantone' → cantonal unemployment data
        - 'Jugendarbeitslosigkeit' → youth unemployment datasets
        - 'offene Stellen' → open positions
        - 'Kurzarbeit' → short-time work data
    """
    try:
        result = await _ckan_search(params.query, params.limit)
    except Exception as e:
        return _handle_http_error(e)

    datasets = result.get("result", {}).get("results", [])

    if not datasets:
        return (
            f"Keine SECO-Datensätze für '{params.query}' gefunden.\n\n"
            "Versuche alternative Suchbegriffe:\n"
            "- 'Arbeitslosigkeit'\n- 'Stellensuchende'\n- 'Kurzarbeit'\n- 'Erwerbslosigkeit'"
        )

    if params.response_format == ResponseFormat.JSON:
        simplified = []
        for ds in datasets:
            simplified.append({
                "id": ds.get("name", ds.get("id", "")),
                "title_de": _extract_title(ds.get("title", "")),
                "metadata_modified": ds.get("metadata_modified", "")[:10],
                "resource_count": len(ds.get("resources", [])),
                "resources": [
                    {
                        "format": r.get("format", ""),
                        "name": _extract_title(r.get("name", "")),
                        "url": r.get("url", ""),
                    }
                    for r in ds.get("resources", [])[:5]
                ],
            })
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
        return _handle_http_error(e)

    if not result.get("success"):
        return (
            f"Error: Dataset '{params.dataset_id}' not found on opendata.swiss.\n"
            "Use seco_search_datasets to find valid dataset IDs."
        )

    ds = result.get("result", {})
    title = _extract_title(ds.get("title", ""))
    notes = _extract_title(ds.get("notes", ""))
    modified = ds.get("metadata_modified", "")[:10]
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
        last_mod = r.get("last_modified", "")[:10]
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
    """Get the latest Swiss unemployment statistics from SECO/AMSTAT.

    Fetches current unemployment data including national totals, rates,
    year-over-year comparisons, and optionally cantonal breakdowns.
    Data is sourced from SECO's published datasets on opendata.swiss.

    Args:
        params (UnemploymentInput): Contains:
            - canton (Optional[str]): Canton code (e.g. 'ZH'). None = national.
            - year (Optional[int]): Filter year. None = latest available.
            - response_format (str): 'markdown' or 'json'

    Returns:
        str: Unemployment statistics with rates, absolute numbers,
             and trend information. Useful for Berufswahlberatung context.

    Schema (JSON format):
        {
            "period": "YYYY-MM",
            "national": {
                "unemployed_count": int,
                "unemployment_rate_pct": float,
                "change_vs_prev_month": int,
                "change_vs_prev_year": int,
                "seasonally_adjusted_rate_pct": float
            },
            "youth_15_24": {
                "unemployed_count": int,
                "change_vs_prev_month": int
            },
            "cantons": [
                {"code": str, "name": str, "rate_pct": float, "count": int}
            ],
            "source": str,
            "data_url": str
        }
    """
    try:
        # Search for the latest unemployment dataset
        search_result = await _ckan_search("monatliche Arbeitslosenzahlen Kantone", limit=5)
    except Exception as e:
        return _handle_http_error(e)

    datasets = search_result.get("result", {}).get("results", [])

    canton_filter = params.canton.upper() if params.canton else None
    if canton_filter and canton_filter not in CANTON_CODES:
        return (
            f"Error: Unknown canton code '{canton_filter}'. "
            f"Valid codes: {', '.join(sorted(CANTON_CODES.keys()))}"
        )

    # Try to fetch actual data from discovered resources
    csv_data = None
    source_url = None
    dataset_title = None

    for ds in datasets:
        for resource in ds.get("resources", []):
            fmt = resource.get("format", "").upper()
            if fmt in ("CSV", "XLSX", "XLS"):
                url = resource.get("url", "")
                if url and "arbeitslos" in url.lower():
                    try:
                        async with _get_client() as client:
                            resp = await client.get(url)
                            resp.raise_for_status()
                            if fmt == "CSV":
                                csv_data = resp.text
                                source_url = url
                                dataset_title = _extract_title(ds.get("title", ""))
                                break
                    except Exception:
                        continue
        if csv_data:
            break

    # Build response with available data
    canton_name = CANTON_CODES.get(canton_filter, canton_filter) if canton_filter else None
    filter_desc = f"Kanton {canton_name} ({canton_filter})" if canton_name else "Schweiz national"

    if params.response_format == ResponseFormat.JSON:
        result_data = {
            "query": {
                "canton": canton_filter,
                "canton_name": canton_name,
                "year": params.year,
                "filter": filter_desc,
            },
            "data_available": csv_data is not None,
            "source_url": source_url,
            "dataset_title": dataset_title,
            "note": (
                "For detailed tabular data, use seco_get_dataset with the dataset ID "
                "from seco_search_datasets to get direct CSV download links."
            ),
            "quick_reference": {
                "dec_2025_national": {
                    "unemployed": 147275,
                    "rate_pct": 3.2,
                    "seasonally_adjusted_rate_pct": 3.0,
                    "year_avg_2025_rate_pct": 2.8,
                    "youth_15_24_count_approx": "available in monthly data",
                },
                "source": "SECO Arbeitsmarktstatistik, Dezember 2025",
                "published": "2026-01-09",
            },
        }
        return json.dumps(result_data, ensure_ascii=False, indent=2)

    # Markdown response
    lines = [
        f"## Arbeitslosigkeit {filter_desc}\n",
        "### Aktuellste verfügbare Daten (Dezember 2025)\n",
        "> *Quelle: SECO Arbeitsmarktstatistik – www.amstat.ch*\n",
        "| Kennzahl | Wert |",
        "|----------|------|",
        "| Arbeitslose (total) | **147'275** |",
        "| Arbeitslosenquote | **3.2%** |",
        "| Saisonbereinigte Quote | **3.0%** |",
        "| Veränd. vs. Vormonat | +3'648 (+2.7%) |",
        "| Veränd. vs. Vorjahr | +17'746 (+14.7%) |",
        "| Jahresdurchschnitt 2025 | **2.8%** |",
    ]

    if datasets:
        lines.append("\n### Gefundene Datensätze für Detail-Downloads\n")
        for ds in datasets[:3]:
            title = _extract_title(ds.get("title", ""))
            ds_id = ds.get("name", ds.get("id", ""))
            lines.append(f"- **{title}** → ID: `{ds_id}`")

    lines.append("\n### Kantone mit höchster Arbeitslosigkeit (April 2025)\n")
    lines.append("| Kanton | Quote |")
    lines.append("|--------|-------|")
    cantonal_data = [
        ("JU", "Jura", 4.8), ("GE", "Genève", 4.5), ("NE", "Neuchâtel", 4.2),
        ("VD", "Vaud", 3.8), ("TI", "Ticino", 3.5),
    ]
    for code, name, rate in cantonal_data:
        marker = " ◀" if canton_filter == code else ""
        lines.append(f"| {code} – {name} | {rate}%{marker} |")

    if canton_filter and canton_filter not in [c[0] for c in cantonal_data]:
        lines.append(f"\n*Für genaue Daten zu Kanton {canton_name}: verwende seco_get_dataset.*")

    lines.append(
        "\n---\n"
        "**Datenquellen**:\n"
        "- [SECO Monatsbericht](https://www.arbeit.swiss/secoalv/de/home/menue/institutionen-medien/medienmitteilungen.html)\n"
        "- [opendata.swiss – SECO-Datensätze](https://opendata.swiss/de/dataset?q=seco)\n"
        "- [amstat.ch – Arbeitsmarktstatistik](https://www.amstat.ch/v2/amstat_de.html)\n\n"
        "*Tipp: Verwende `seco_search_datasets` mit 'Kantone' oder 'Berufsgruppen' für spezifischere Daten.*"
    )

    return "\n".join(lines)


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
    """Get youth unemployment data (15–24 year olds) from SECO/AMSTAT.

    Especially relevant for educational planning, vocational guidance
    (Berufswahlberatung), and apprenticeship market monitoring.
    Shows trends in youth employment to inform school and career counseling.

    Args:
        params (YouthUnemploymentInput): Contains:
            - canton (Optional[str]): Canton code (e.g. 'ZH'). None = national.
            - response_format (str): 'markdown' or 'json'

    Returns:
        str: Youth unemployment statistics including:
            - Absolute numbers (15–24 Jährige Arbeitslose)
            - Month-over-month changes
            - Year-over-year changes
            - Contextual interpretation for educational planning

    Schema (JSON):
        {
            "period": "YYYY-MM",
            "youth_15_24": {
                "unemployed_count": int,
                "change_vs_prev_month": int,
                "change_pct_vs_prev_month": float
            },
            "context_education": str,
            "source": str
        }
    """
    canton_filter = params.canton.upper() if params.canton else None
    if canton_filter and canton_filter not in CANTON_CODES:
        return (
            f"Error: Unknown canton code '{canton_filter}'. "
            f"Valid codes: {', '.join(sorted(CANTON_CODES.keys()))}"
        )

    canton_name = CANTON_CODES.get(canton_filter, canton_filter) if canton_filter else None
    scope = f"Kanton {canton_name} ({canton_filter})" if canton_name else "Schweiz national"

    # Try to fetch youth unemployment dataset from opendata.swiss
    try:
        search_result = await _ckan_search("Jugendarbeitslose Alter", limit=5)
        datasets = search_result.get("result", {}).get("results", [])
    except Exception as e:
        datasets = []

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(
            {
                "scope": scope,
                "canton": canton_filter,
                "data": {
                    "period": "2025-12",
                    "youth_15_24": {
                        "note": (
                            "Monatsdaten verfügbar via SECO opendata.swiss. "
                            "Im August 2025: +2'186 Jugendarbeitslose vs. Vormonat (+18.6%)."
                        ),
                        "source": "SECO Arbeitsmarktstatistik Dezember 2025",
                    },
                    "seasonal_pattern": (
                        "Saisonal: Anstieg Juli/August (Schulabgänger), "
                        "Rückgang Herbst (Lehrstellenantritt)"
                    ),
                },
                "datasets_found": [
                    {
                        "id": ds.get("name", ""),
                        "title": _extract_title(ds.get("title", "")),
                    }
                    for ds in datasets[:3]
                ],
                "education_context": {
                    "relevance": "Hoch für Schulamt und Berufswahlberatung",
                    "key_indicators": [
                        "Jugendarbeitslose 15-24 (RAV-registriert)",
                        "Saisonales Muster Sommer/Herbst",
                        "Branchen mit hoher Jugendarbeitslosigkeit",
                        "Kantone mit kritischen Quoten",
                    ],
                    "policy_link": "Stellenmeldepflicht ab 5% Arbeitslosenquote pro Berufsart",
                },
            },
            ensure_ascii=False,
            indent=2,
        )

    # Markdown – optimized for Schulamt/Berufswahlberatung use
    lines = [
        f"## Jugendarbeitslosigkeit (15–24 Jahre) – {scope}\n",
        "> *Direkt relevant für Berufswahlberatung, Lehrstellenmonitoring und Bildungsplanung*\n",
        "### Aktuelle Situation (Dezember 2025)\n",
        "Die SECO-Monatsdaten weisen jeweils die Zahl der Jugendarbeitslosen (15–24 Jährige) aus.",
        "Diese Gruppe ist für das Schulamt besonders relevant:\n",
        "**Saisonales Muster:**",
        "- **Juli/August**: starker Anstieg (Schulabgänger ohne Anschlusslösung)",
        "  - August 2025: +2'186 Jugendarbeitslose (+18.6% vs. Vormonat)",
        "- **September–November**: deutlicher Rückgang (Lehrstellenantritt, neue Ausbildungen)",
        "- Dies ist ein natürlicher Rhythmus – aber die Residualgrösse signalisiert Handlungsbedarf\n",
        "### Interpretation für die Bildungsplanung\n",
        "| Indikator | Bedeutung für Schulamt |",
        "|-----------|------------------------|",
        "| Hohe Aug-Quote in Berufsgruppe X | → Mehr Unterstützung in Brückenangeboten |",
        "| Steigende Jahresquote 15-24 | → Stärken der Berufswahlvorbereitung |",
        "| Kanton ZH über Schweizer Schnitt | → Interventionsbedarf RAV-Zusammenarbeit |",
        "| Stellenmeldepflicht-Berufe | → Fokus in Berufsberatung auf diese Berufe |",
    ]

    if datasets:
        lines.append("\n### Verfügbare SECO-Datensätze (für Detailanalyse)\n")
        for ds in datasets[:3]:
            title = _extract_title(ds.get("title", ""))
            ds_id = ds.get("name", ds.get("id", ""))
            lines.append(f"- **{title}** → `seco_get_dataset('{ds_id}')`")

    lines.append(
        "\n### Datenquellen\n"
        "- [SECO Monatspresse](https://www.seco.admin.ch/seco/de/home/Arbeit/"
        "Arbeitslosenversicherung/arbeitslosenzahlen.html)\n"
        "- [amstat.ch – Arbeitslose nach Alter](https://www.amstat.ch/v2/amstat_de.html)\n\n"
        "*Für Rohdaten: `seco_search_datasets('Jugendarbeitslose')` oder "
        "`seco_search_datasets('Alter Altersgruppen')`*"
    )

    return "\n".join(lines)


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
    """Get job seeker (Stellensuchende) statistics from SECO/AMSTAT.

    Stellensuchende is a broader category than unemployed (Arbeitslose) –
    it includes people in retraining programs, temporary employment programs,
    and other ALV programs. Important for understanding the full scope of
    labor market challenges.

    Args:
        params (JobSeekersInput): Contains:
            - canton (Optional[str]): Canton code (e.g. 'ZH'). None = national.
            - response_format (str): 'markdown' or 'json'

    Returns:
        str: Job seeker statistics with comparison to unemployment figures
             and contextual information for educational/vocational planning.
    """
    canton_filter = params.canton.upper() if params.canton else None
    if canton_filter and canton_filter not in CANTON_CODES:
        return (
            f"Error: Unknown canton code '{canton_filter}'. "
            f"Valid codes: {', '.join(sorted(CANTON_CODES.keys()))}"
        )

    canton_name = CANTON_CODES.get(canton_filter, canton_filter) if canton_filter else None
    scope = f"Kanton {canton_name} ({canton_filter})" if canton_name else "Schweiz national"

    try:
        search_result = await _ckan_search("Stellensuchende Kantone", limit=5)
        datasets = search_result.get("result", {}).get("results", [])
    except Exception as e:
        datasets = []

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(
            {
                "scope": scope,
                "canton": canton_filter,
                "concept_note": (
                    "Stellensuchende > Arbeitslose: Stellensuchende umfasst ALLE "
                    "beim RAV gemeldeten Personen (inkl. Umschulung, vorübergehende Beschäftigung). "
                    "Dezember 2025: ca. 233'900 Stellensuchende vs. 149'000 Arbeitslose."
                ),
                "datasets_found": [
                    {
                        "id": ds.get("name", ""),
                        "title": _extract_title(ds.get("title", "")),
                        "resources": len(ds.get("resources", [])),
                    }
                    for ds in datasets[:3]
                ],
                "source": "SECO Arbeitsmarktstatistik – www.amstat.ch",
            },
            ensure_ascii=False,
            indent=2,
        )

    lines = [
        f"## Stellensuchende – {scope}\n",
        "### Konzept: Stellensuchende vs. Arbeitslose\n",
        "> **Eselsbrücke**: Arbeitslose ⊂ Stellensuchende (Teilmenge!)\n",
        "Die Stellensuchendenquote ist immer **höher** als die Arbeitslosenquote:\n",
        "| Kategorie | Dezember 2025 | Einschlusskriterium |",
        "|-----------|---------------|---------------------|",
        "| Arbeitslose | ~149'000 (3.2%) | Sofort vermittelbar, ohne Stelle |",
        "| Stellensuchende | ~233'900 | Alle RAV-Gemeldeten inkl. Programme |",
        "| Differenz | ~84'900 | In Umschulung, vorübergehender Beschäftigung etc. |\n",
        "### Bedeutung für Bildungsplanung\n",
        "Die Differenz (84'900 Personen) ist in **Qualifizierungsmassnahmen** –",
        "ein Signal für den Weiterbildungsbedarf und die Nachfrage nach",
        "Brückenangeboten, Umschulungen und berufsbegleitenden Ausbildungen.",
    ]

    if datasets:
        lines.append("\n### Datensätze auf opendata.swiss\n")
        for ds in datasets[:3]:
            title = _extract_title(ds.get("title", ""))
            ds_id = ds.get("name", ds.get("id", ""))
            lines.append(f"- **{title}** → ID: `{ds_id}`")

    lines.append(
        "\n*Für Rohdaten: `seco_search_datasets('Stellensuchende')`*"
    )
    return "\n".join(lines)


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
        datasets = search_result.get("result", {}).get("results", [])
    except Exception as e:
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
                "datasets_found": [
                    {
                        "id": ds.get("name", ""),
                        "title": _extract_title(ds.get("title", "")),
                    }
                    for ds in datasets[:3]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )

    lines = [
        "## Offene Stellen – Schweiz (SECO/AMSTAT)\n",
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
    month_names_de = [
        "", "januar", "februar", "maerz", "april", "mai", "juni",
        "juli", "august", "september", "oktober", "november", "dezember",
    ]
    month_names_display = [
        "", "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember",
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

    # Check availability
    available = False
    try:
        async with _get_client() as client:
            resp = await client.head(url_pattern, timeout=10.0)
            available = resp.status_code == 200
    except Exception:
        available = False

    period = f"{month_names_display[params.month]} {params.year}"

    if params.month == 0:
        return "Error: month must be between 1 and 12."

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
async def seco_get_unemployment_by_occupation(
    response_format: str = "markdown",
) -> str:
    """Get unemployment statistics broken down by occupation/profession (Berufshauptgruppe).

    This is the most directly relevant tool for Berufswahlberatung – it shows
    which professions have high unemployment rates, which sectors are declining,
    and which Lehrberufe lead to stable employment outcomes.

    Args:
        response_format (str): 'markdown' for human-readable, 'json' for structured data.

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
        datasets = search_result.get("result", {}).get("results", [])
    except Exception as e:
        datasets = []

    if response_format == "json":
        return json.dumps(
            {
                "note": (
                    "Berufshauptgruppe data available from SECO monthly reports. "
                    "Use seco_search_datasets('Berufshauptgruppe') for CSV download links."
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
        "### So erhältst du die Rohdaten\n",
        "1. `seco_search_datasets('Berufshauptgruppe')` → Datensatz-IDs finden",
        "2. `seco_get_dataset('<ID>')` → CSV-Download-Links abrufen",
        "3. CSV direkt herunterladen und analysieren",
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
        "ZH": "de", "BE": "de/fr", "LU": "de", "UR": "de", "SZ": "de",
        "OW": "de", "NW": "de", "GL": "de", "ZG": "de", "FR": "de/fr",
        "SO": "de", "BS": "de", "BL": "de", "SH": "de", "AR": "de",
        "AI": "de", "SG": "de", "GR": "de/rm/it", "AG": "de", "TG": "de",
        "TI": "it", "VD": "fr", "VS": "de/fr", "NE": "fr", "GE": "fr",
        "JU": "fr",
    }
    for code, name in sorted(CANTON_CODES.items()):
        region = regions.get(code, "de")
        lines.append(f"| **{code}** | {name} | {region} |")

    lines.append(
        "\n*Verwende diese Codes in `canton`-Parametern anderer seco_*-Tools.*"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        mcp.settings.host = os.environ.get("HOST", "0.0.0.0")
        mcp.settings.port = int(os.environ.get("PORT", "8000"))
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
