# Security Policy & Posture

🌐 **English** | **[Deutsch](SECURITY.de.md)**

`seco-labor-mcp` was hardened against the internal MCP best-practice audit
catalogue. This document summarises the security posture and records the
**accepted-risk** decisions for controls that are deliberately handled at the
portfolio/gateway layer rather than inside this single server.

## Reporting a vulnerability

Please open a private security advisory on the GitHub repository, or contact the
maintainer listed in `README.md`. Do not file public issues for exploitable
vulnerabilities.

## Posture summary

This is a **read-only**, **no-PII**, **public-open-data** MCP server. All 9 tools
only issue HTTP GET requests against a fixed set of Swiss federal open-data
endpoints (opendata.swiss CKAN, arbeit.swiss — see `README.md`) and parse the
returned CSV/metadata. Hardening already in place:

| Area | Control |
|---|---|
| Egress | HTTPS-only to opendata.swiss / arbeit.swiss; outbound URLs are validated and `follow_redirects=False` closes DNS-rebinding TOCTOU windows (SEC-004) |
| SSRF | IP validation against private/loopback/link-local/multicast ranges via async `getaddrinfo` before every external fetch (SEC-004) |
| TLS | Certificate verification on by default (httpx default); never disabled (SEC-005) |
| Binding | stdio transport by default; the optional SSE transport binds to `127.0.0.1` and requires an explicit `HOST=0.0.0.0` opt-in for containers (SEC-016) |
| Input | Pydantic v2 strict validation (`extra="forbid"`) on every tool input model (SEC-008/018) |
| Tools | Every tool sets `readOnlyHint: True`; no write, mutate, or delete paths exist (ARCH) |
| Secrets | None required — the server uses no API key or credentials; nothing secret is stored or logged (ARCH-005/SEC-013) |
| Errors | `FastMCP(..., mask_error_details=True)` keeps internal exception messages out of LLM context; protocol vs. execution errors are surfaced correctly (OBS-001/002) |
| Stdout | Reserved for the JSON-RPC stream; all logging pinned to stderr (OBS-004) |
| Resilience | A 30 s per-request timeout bounds every upstream call; a bounded 24 h TTL CSV cache (50 entries, FIFO eviction) limits resource growth (SCALE-002/003) |

The audit cycle (2 HIGH, 4 MEDIUM, 3 LOW + 4 follow-up LOW from a re-audit) is
**fully closed** as of `0.3.0`. See `CHANGELOG.md` for the hardening history.

## Accepted risks (portfolio-level controls)

The following audit checks are **not** implemented inside this server by design.
They are portfolio-wide concerns best enforced at an MCP gateway / host layer,
and the residual risk here is low because the server is read-only and only
reaches a small set of trusted public-data providers.

### SEC-014 — Tool allow-listing via an MCP gateway

**Status:** accepted risk (portfolio-level).
A per-tool allow-list belongs to the MCP host/gateway that aggregates multiple
servers, not to an individual server that exposes a fixed, read-only tool set.
If/when a central gateway is introduced for the portfolio, tool allow-listing
should be configured there. Until then, the risk is bounded: every tool is
read-only and constrained to the fixed endpoints above.

### SEC-015 — Pre-flight tool-poisoning detection

**Status:** accepted risk (portfolio-level) — with a local guard in place.
Tool-poisoning (malicious tool descriptions / rug-pulls) is a supply-chain and
host-side concern. This server's tool definitions are version-controlled,
authored in-repo, and reviewed via PR; there is no dynamic or remote tool
registration. Cross-server poisoning detection remains a gateway/host
responsibility tracked at the portfolio level.

## Re-evaluation triggers

These acceptances should be revisited if the server ever:

- gains **write** capability or starts processing **PII**, or
- adds an **authentication** model (then implement bound, TTL'd,
  server-side-invalidated session IDs and re-audit before merge), or
- registers tools **dynamically** / from remote sources, or
- is aggregated behind a shared MCP gateway (then enable the gateway's tool
  allow-listing and tool-poisoning detection).
