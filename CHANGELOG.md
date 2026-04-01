# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
