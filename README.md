# seco-labor-mcp

> **Swiss Public Data MCP Portfolio** · [malkreide](https://github.com/malkreide)

[![CI](https://github.com/malkreide/seco-labor-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/malkreide/seco-labor-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/seco-labor-mcp)](https://pypi.org/project/seco-labor-mcp/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An MCP (Model Context Protocol) server for Swiss labor market data from **SECO** (Staatssekretariat für Wirtschaft) and **AMSTAT** via opendata.swiss.

[🇩🇪 Deutsche Version](README.de.md)

---

## Overview

This server connects AI models to Swiss labor market statistics — unemployment rates, job seekers, open positions, youth unemployment, and occupational breakdowns — all without requiring an API key.

**Primary audiences:**
- 🏫 **Schulamt / Education planning** — youth unemployment, vocational guidance data
- 📊 **Research & analysis** — labor market trends, cantonal comparisons
- 🤖 **AI agents** — automated labor market monitoring and reporting

**Anchor query:**  
*"Welche Berufsgruppen haben im Kanton Zürich die höchste Jugendarbeitslosigkeit, und welche Lehrberufe unterliegen der Stellenmeldepflicht?"*

---

## Data Sources (Phase 1 — No Auth Required)

| Source | Description | Status |
|--------|-------------|--------|
| [opendata.swiss](https://opendata.swiss/de/dataset?q=seco) | CKAN metadata catalog with SECO dataset CSVs | ✅ Live |
| [arbeit.swiss](https://www.arbeit.swiss) | Monthly press reports (PDF, structured URL pattern) | ✅ Live |
| [amstat.ch](https://www.amstat.ch) | AMSTAT reference portal | ⚠️ JavaScript SPA, no public REST API |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  seco-labor-mcp                     │
│                                                     │
│  ┌─────────────┐    ┌──────────────────────────┐   │
│  │  FastMCP    │    │      9 MCP Tools         │   │
│  │  Server     │◄──►│  seco_search_datasets    │   │
│  │  (stdio /   │    │  seco_get_dataset        │   │
│  │   SSE)      │    │  seco_get_unemployment_* │   │
│  └─────────────┘    │  seco_get_youth_*        │   │
│         │           │  seco_get_job_seekers    │   │
│         ▼           │  seco_get_open_positions │   │
│  ┌─────────────┐    │  seco_get_monthly_url    │   │
│  │  httpx      │    │  seco_list_cantons       │   │
│  │  async      │    └──────────────────────────┘   │
│  └──────┬──────┘                                   │
└─────────┼───────────────────────────────────────────┘
          │
          ▼
  ┌───────────────────────────────────┐
  │  opendata.swiss CKAN API          │
  │  https://opendata.swiss/api/3/    │
  │  action/package_search            │
  │  action/package_show              │
  └───────────┬───────────────────────┘
              │
              ▼
  ┌───────────────────────────────────┐
  │  SECO Data Resources              │
  │  CSV / XLSX / PDF Downloads       │
  │  (monthly labor market data)      │
  └───────────────────────────────────┘
```

---

## Tools

| Tool | Description | Key Use Case |
|------|-------------|--------------|
| `seco_search_datasets` | Search SECO datasets on opendata.swiss | Discovery |
| `seco_get_dataset` | Full metadata + download links for a dataset | Data access |
| `seco_get_unemployment_overview` | National/cantonal unemployment figures | Labor market overview |
| `seco_get_youth_unemployment` | Youth unemployment (15–24 year olds) | 🎓 Berufswahlberatung |
| `seco_get_job_seekers` | Stellensuchende (broader than unemployed) | Training demand |
| `seco_get_open_positions` | Open positions — leading indicator | Sector analysis |
| `seco_get_unemployment_by_occupation` | Breakdown by Berufshauptgruppe | 🎓 Vocational guidance |
| `seco_get_monthly_report_url` | Generate/verify PDF report URL | Source access |
| `seco_list_cantons` | All 26 canton codes and names | Utility |

---

## Installation

### Claude Desktop (stdio)

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "seco-labor": {
      "command": "uvx",
      "args": ["seco-labor-mcp"]
    }
  }
}
```

### Cloud / SSE

```bash
pip install seco-labor-mcp
MCP_TRANSPORT=sse PORT=8000 seco-labor-mcp
```

### Development

```bash
git clone https://github.com/malkreide/seco-labor-mcp.git
cd seco-labor-mcp
pip install -e ".[dev]"
pytest tests/ -m "not live" -v
```

---

## Usage Examples

### Search for youth unemployment data
```
Tool: seco_search_datasets
Input: { "query": "Jugendarbeitslosigkeit Alter", "limit": 5 }
```

### Get cantonal unemployment for Zürich
```
Tool: seco_get_unemployment_overview
Input: { "canton": "ZH", "response_format": "markdown" }
```

### Get monthly report URL
```
Tool: seco_get_monthly_report_url
Input: { "year": 2026, "month": 2, "language": "de" }
```

---

## Key Concepts

### Arbeitslose vs. Stellensuchende

> **Eselsbrücke**: Arbeitslose ⊂ Stellensuchende — Arbeitslose sind eine Teilmenge.

| Term | Definition | Dec 2025 |
|------|-----------|----------|
| Arbeitslose | RAV-registered, immediately available | ~149'000 (3.2%) |
| Stellensuchende | All RAV-registered (incl. training programs) | ~233'900 |

### Youth Unemployment Seasonality

- **July/August**: Sharp increase (school leavers without placements)
- **September/October**: Decline (apprenticeship starts)
- The residual that remains after the autumn decline signals structural need for bridge programs (Brückenangebote)

### Stellenmeldepflicht (since 2020)

Occupations with ≥5% unemployment rate must be reported to the RAV before posting publicly. The list changes annually. This is directly relevant for vocational counseling — these professions have highest availability for Swiss job seekers.

---

## Portfolio Synergies

| Server | Synergy |
|--------|---------|
| `swiss-statistics-mcp` | BFS population/employment data for deeper context |
| `zurich-opendata-mcp` | City of Zurich-level education and social data |
| `swiss-snb-mcp` | Economic context (GDP, wages) for labor market interpretation |
| `fedlex-mcp` | ALV (Arbeitslosenversicherung) legislative framework |

---

## Known Limitations

- `amstat.arbeit.swiss` has no public REST API (JavaScript SPA) → workaround via CKAN
- Occupational/sectoral detail requires CSV download from SECO resources
- Monthly press report URL patterns may vary for older reports
- Cantonal sub-municipal data not available at this level

**Phase 2 roadmap:**
- Automatic CSV caching with 24h TTL
- Direct XLSX parsing for cantonal breakdowns
- Integration with `zh-education-mcp` for Schulamt-specific correlations

---

## Data License

SECO data published on opendata.swiss is under **Creative Commons CCZero** (public domain).  
Source: Staatssekretariat für Wirtschaft (SECO) — [seco.admin.ch](https://www.seco.admin.ch)

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.
