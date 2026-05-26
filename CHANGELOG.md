# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-05-26

Version 0.2.0 was reserved for an earlier GitHub-only release pointing at
commit `89fc337` (pre-audit lint cleanup). Because PyPI version numbers are
immutable, this audit-completion snapshot ships as 0.3.0 to avoid a confusing
collision between the GitHub tag and what users would install from PyPI.

This release closes all findings from a `mcp-audit-skill` audit cycle
(2 HIGH, 4 MEDIUM, 3 LOW + 4 follow-up LOW from a re-audit).

### Added
- FastMCP `lifespan` with a pooled `httpx.AsyncClient` reused across all tool
  calls. Eliminates per-call TCP/TLS setup (SDK-001).
- Live CSV parsing for `seco_get_unemployment_overview`,
  `seco_get_youth_unemployment`, and `seco_get_job_seekers`. Each tool now
  fetches and parses the first matching CSV resource from CKAN with defensive
  delimiter and encoding detection, returns headers + last N rows (optionally
  filtered by canton), and detects the `YYYY-MM` reference period.
- 24 h TTL CSV cache (bounded to 50 entries, FIFO eviction).
- SSRF prevention: HTTPS-only enforcement + IP validation against
  private/loopback/link-local/multicast ranges via async `getaddrinfo`,
  `follow_redirects=False` to close DNS-rebinding TOCTOU windows (SEC-004).
- `OccupationInput` Pydantic model for `seco_get_unemployment_by_occupation`,
  matching every other tool's input shape (ARCH consistency).
- Snapshot disclaimers (`data_source: "static_reference"` + `verify_live_at`
  URL) for the rare fallback path when live CSV fetch/parse fails.
- 35 new unit tests (34 → 69) covering live CSV parsing, SSRF rejection,
  cache eviction, protocol vs. execution errors, and tool input validation.

### Changed
- SSE transport binds to `127.0.0.1` by default. Containers must opt into
  `HOST=0.0.0.0` explicitly (SEC-016).
- `FastMCP(..., mask_error_details=True)` so internal exception messages
  cannot leak into LLM context (OBS-002).
- Protocol-level errors (5xx, `ConnectError`, `TimeoutException`) now re-raise
  so FastMCP surfaces them as JSON-RPC `isError=true`. Execution-level errors
  (4xx, SSRF rejection) still return a recoverable string the LLM can act on
  (OBS-001).
- `_validate_external_url` is now async and uses `loop.getaddrinfo` so DNS
  resolution does not block the event loop under concurrent SSE traffic.
- Tests split into `tests/test_unit.py` (mocked, runs in CI) and
  `tests/test_live.py` (real internet, opt-in via `--run-live`) per OPS-001.

### Removed
- Unused `KNOWN_DATASETS` constant (was never referenced).
- Dead `if params.month == 0` branch in `seco_get_monthly_report_url`
  (Pydantic already enforces `1 ≤ month ≤ 12`).

## [0.1.0] - 2026-04-01

### Added
- Initial release of `seco-labor-mcp`
- `seco_search_datasets` — search SECO datasets on opendata.swiss CKAN
- `seco_get_dataset` — full metadata and download links for a dataset
- `seco_get_unemployment_overview` — national and cantonal unemployment figures
- `seco_get_youth_unemployment` — youth unemployment data (15–24 year olds)
- `seco_get_job_seekers` — Stellensuchende statistics
- `seco_get_open_positions` — open positions as a leading indicator
- `seco_get_unemployment_by_occupation` — breakdown by Berufshauptgruppe
- `seco_get_monthly_report_url` — generate and verify monthly PDF report URLs
- `seco_list_cantons` — all 26 Swiss canton codes and names
- Bilingual documentation (README.md in English, README.de.md in German)
- 34 unit tests with respx mocking, live-test markers
- GitHub Actions CI and PyPI OIDC publish workflows
- No API key required (Phase 1 – No-Auth-First)
