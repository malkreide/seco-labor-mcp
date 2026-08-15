> 🇨🇭 **Part of the [Swiss Public Data MCP Portfolio](https://github.com/malkreide)**

# SECO Labor Market MCP Server

![Version](https://img.shields.io/badge/version-0.3.4-blue)
[![CI](https://github.com/malkreide/seco-labor-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/malkreide/seco-labor-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/seco-labor-mcp)](https://pypi.org/project/seco-labor-mcp/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-purple)](https://modelcontextprotocol.io/)
[![No Auth Required](https://img.shields.io/badge/auth-none%20required-brightgreen)](https://github.com/malkreide/seco-labor-mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

🌐 **English** | **[Deutsch](README.de.md)**

An MCP (Model Context Protocol) server for Swiss labor market data from **SECO** (Staatssekretariat für Wirtschaft) and **AMSTAT** via opendata.swiss.

<p align="center">
  <img src="assets/demo.png" alt="Demo: Claude queries youth unemployment via seco-labor-mcp tool call" width="720">
</p>

---

## Overview

This server connects AI models to Swiss labor market statistics — unemployment rates, job seekers, open positions, youth unemployment, and occupational breakdowns — all without requiring an API key.

**Primary audiences:**
- 🏫 **Schulamt / Education planning** — youth unemployment, vocational guidance data
- 📊 **Research & analysis** — labor market trends, cantonal comparisons
- 🤖 **AI agents** — automated labor market monitoring and reporting

**Anchor query:**  
*"Welche Berufsgruppen haben im Kanton Zürich die höchste Jugendarbeitslosigkeit, und welche Lehrberufe unterliegen der Stellenmeldepflicht?"*
[→ More use cases by audience →](EXAMPLES.md)

---

## Data Sources (Phase 1 — No Auth Required)

| Source | Description | Status |
|--------|-------------|--------|
| [opendata.swiss](https://opendata.swiss/de/dataset) | CKAN catalogue; the pinned BFS table `T3.3.0.1` carries the SECO annual series | ✅ Live |
| [arbeit.swiss](https://www.arbeit.swiss) | Monthly press reports (PDF, structured URL pattern) | ✅ Live |
| [amstat.ch](https://www.amstat.ch) | AMSTAT reference portal | ⚠️ JavaScript SPA, no public REST API |
| [unfallstatistik.ch](https://www.unfallstatistik.ch) | Unfallstatistik UVG (SSUV/KSUV c/o Suva) — occupational accidents and diseases | ⚠️ PDF only, no API (see below) |

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

## Where the figures come from — and what is missing

**SECO is no longer a publisher on opendata.swiss.** Verified 2026-08-14:
`organization_show` returns 404, and none of the 176 entries in
`organization_list` is SECO. Until then the server filtered every search on
that organisation and therefore returned **nothing** — a name lookup that
misses looks exactly like an empty search.

The registered unemployed and job seekers are still SECO's figures: the **BFS
publishes them** in table `T3.3.0.1` and names SECO in the footer. The server
reads that table through a **pinned dataset id** (`sources.py`), checked
against the live source by a live test.

| Series | 2000 | 2025 |
|---|---|---|
| Registered job seekers (SECO) | 124.6 | 214.1 |
| Registered unemployed (SECO) | 72.0 | 133.7 |
| ILO unemployed (BFS) | 126.5 | 248.5 |

*thousands, annual average*

The three series do **not** measure the same thing: in 2000 the ILO figure is
1.76× the registered one. The server reports them separately and labelled, and
never converts one into the other.

**Not available at present:** monthly values, cantonal breakdowns, youth
unemployment (zero datasets portal-wide) and unemployment by occupational
group. The affected tools say so and return **no** substitute figure. These
values exist interactively on [amstat.ch](https://www.amstat.ch/v2/amstat_de.html),
which offers no interface a server could call.

---

## Tools

| Tool | Description | Key Use Case |
|------|-------------|--------------|
| `seco_search_datasets` | Search labour-market datasets on opendata.swiss (publisher shown per hit) | Discovery |
| `seco_get_dataset` | Full metadata + download links for a dataset | Data access |
| `seco_get_unemployment_overview` | Registered unemployed, national, annual series from 2000 | Labor market overview |
| `seco_get_youth_unemployment` | Youth unemployment (15–24) — **no data source at present**, see below | 🎓 Berufswahlberatung |
| `seco_get_job_seekers` | Registered job seekers, national, annual series from 2000 | Training demand |
| `seco_get_open_positions` | Open positions — **no national series available** | Sector analysis |
| `seco_get_unemployment_by_occupation` | Breakdown by Berufshauptgruppe — **no machine-readable source** | 🎓 Vocational guidance |
| `seco_get_monthly_report_url` | Generate/verify PDF report URL | Source access |
| `seco_list_cantons` | All 26 canton codes and names | Utility |
| `seco_get_uvg_overview` | UVG key figures on occupational accidents and diseases | Risk overview |
| `seco_get_uvg_by_branch` | Results per NOGA 2008 economic branch | 🎓 Vocational guidance |
| `seco_get_uvg_trends` | Ten-year accident time series per branch | Trend analysis |

12 of a maximum of 15 tools.

---

## Unfallstatistik UVG (SSUV)

The three `seco_get_uvg_*` tools cover the risk side of the same labour market
the unemployment tools describe: how many occupational accidents and diseases
occur per branch, and how that develops over ten years.

**The publisher is not SECO.** The Unfallstatistik UVG is issued by the
Koordinationsgruppe KSUV and the Sammelstelle SSUV c/o Suva, Lucerne. The
`seco_` prefix addresses this server, not the source; every response names the
actual publisher in its `source` field.

### Architecture decision: C (dump-first)

Verified live on 2026-08-05, full write-up in
[`PROBE_REPORT_UVG.md`](PROBE_REPORT_UVG.md).

The source has **no API**. A link scan across every data page returned 165 PDFs
and zero files with `.csv`, `.xlsx` or `.json`. opendata.swiss does not list the
source at all (`count=0` for six of seven search terms), and the BFS dam-api
silently ignores its filter parameters. What remains is machine-readable in
practice but not by design:

| Access | Format | Refresh |
|---|---|---|
| `schluesselzahlen_d.htm` | HTML table, 5 years, Switzerland-wide | annually |
| `Ts{YY}.pdf` | annual edition, tables 1.2 and 2.4 by NOGA | annually, June |
| `WirtKl_{BUV\|NBUV}_{NN}.pdf` | ten-year series per NOGA division | annually, January |

PDFs are cached for 24 h and fetched with 2s/4s/8s backoff.

### What every response tells you

- `source_freshness.data_year` — the **data** year, not the edition year. The
  2026 edition reports 2024; that two-year lag is stated, not buried.
- `totals_check` — parsed rows are summed and compared against the total
  printed in the same publication. A broken layout shows up here instead of
  becoming a plausible wrong number.
- `significant` — the source marks statistically significant year-on-year
  changes with an asterisk. That flag is preserved per data point, so a change
  is only reported as significant where the source says so.

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

The SSE server binds to **`127.0.0.1` (loopback) by default** to prevent
NeighborJack on shared networks. For container deployments where you actually
need to accept traffic from outside the container, set `HOST=0.0.0.0`
explicitly — ideally in your Dockerfile / orchestrator config, and only behind
an upstream proxy or firewall:

```bash
HOST=0.0.0.0 MCP_TRANSPORT=sse PORT=8000 seco-labor-mcp   # container only
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
- UVG figures come from PDF parsing — the layout was stable across the 2025 and
  2026 editions, but a redesign can break it. The `totals_check` in every
  response is what makes such a break visible rather than silent.
- UVG data lags roughly two years (the 2026 edition reports 2024)
- UVG branch detail follows NOGA 2008 and groups some divisions (`41 – 42`,
  `77, 79 – 82`); there is no cantonal breakdown at this level
- Detailed UVG data beyond the publications sits behind the SSUV closed user
  group and is out of scope for this no-auth server

**Phase 2 roadmap:**
- Automatic CSV caching with 24h TTL
- Direct XLSX parsing for cantonal breakdowns
- Integration with `zh-education-mcp` for Schulamt-specific correlations

---

## Data License

Two different licences apply — the code of this server is MIT either way, but the
data is not covered by it.

**SECO / AMSTAT data** published on opendata.swiss is under **Creative Commons
CCZero** (public domain).
Source: Staatssekretariat für Wirtschaft (SECO) — [seco.admin.ch](https://www.seco.admin.ch)

**Unfallstatistik UVG data** is **not** openly licensed. The publication states:

> «Abdruck – ausser für kommerzielle Nutzung – mit Quellenangabe gestattet.»
> (Reproduction permitted, except for commercial use, with attribution.)

That is a non-commercial restriction with an attribution requirement. It belongs
to KSUV/SSUV and cannot be lifted by this repository's MIT licence: the MIT terms
cover the code, not the figures the code retrieves. **If you use this server
commercially, the UVG tools are not covered** — clarify directly with the
Sammelstelle (`unfallstatistik@suva.ch`). Every UVG response repeats this
restriction in its `source` field, because a README is not passed to the model.

---

## Safety & Limits

| Aspect | Details |
|--------|---------|
| **Access** | Read-only (`readOnlyHint: true`) — the server cannot modify or delete any data |
| **Personal data** | No personal data — all sources are aggregated, anonymous public statistics |
| **Rate limits** | No enforced external limits; server caps queries at 20 results by default; 30 s HTTP timeout |
| **Authentication** | No API keys required — opendata.swiss and arbeit.swiss are publicly accessible |
| **Licenses** | SECO data under [Creative Commons CCZero](https://creativecommons.org/publicdomain/zero/1.0/) (public domain) |
| **Terms of Service** | Subject to ToS of: [opendata.swiss](https://opendata.swiss/de/terms-of-use), [SECO](https://www.seco.admin.ch), [arbeit.swiss](https://www.arbeit.swiss) |
| **GDPR / DSG** | Fully compliant — no personal data transmitted or stored; all data is official public statistics |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

---

## Security

See [SECURITY.md](SECURITY.md) for the security posture and how to report a
vulnerability.

---

## License

Released under the [MIT License](LICENSE) — Copyright © 2026 Hayal Oezkan.

---

## Author

**Hayal Oezkan** · [github.com/malkreide](https://github.com/malkreide)

<!-- mcp-name: io.github.malkreide/seco-labor-mcp -->

<!-- BEGIN GENERATED: install -->
## Installation

Run via [`uv`](https://docs.astral.sh/uv/)'s `uvx` — no clone or manual install needed. Add to your MCP client config (`mcpServers` for Claude Desktop, Cursor and Windsurf; use a top-level `servers` key for VS Code in `.vscode/mcp.json`):

```json
{
  "mcpServers": {
    "seco-labor-mcp": {
      "command": "uvx",
      "args": [
        "seco-labor-mcp"
      ]
    }
  }
}
```
<!-- END GENERATED: install -->
