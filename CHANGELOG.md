# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **The retry had six defects, all inherited from the shared template.** Both HTTP paths in this package copied their retry from `reference/retry_backoff.py` in
  [mcp-data-source-probe-skill](https://github.com/malkreide/mcp-data-source-probe-skill),
  and the template shipped these until 2026-08-07. A sweep across eleven
  servers found that none read `Retry-After` and none jittered — one template,
  eleven copies, not eleven independent omissions.
  1. **No jitter.** The ladder was deterministic, so every client that hit the
     same outage retried in lockstep and the load returned as a wave exactly
     when the source recovered — the retry storm extending the outage it was
     meant to bridge. Now spread into `[0.5x, 1.5x]`.
  2. **`Retry-After` was never read.** A 429 or 503 answers the very question
     the backoff curve guesses at. Both RFC 9110 §10.2.3 forms are now read
     (delta-seconds and HTTP-date); an unparseable header yields `None` and
     falls back to the curve — it must never crash on the error path. The
     jitter on top is one-sided `[1.0x, 1.25x]`: the source said *when*, so
     later is polite and earlier ignores the value just read.
  3. **No cap on a single wait**, and the cap now binds *after* the jitter.
     `min(cap, base) * jitter` and `min(cap, base * jitter)` both contain a cap
     and a jitter; only the second is bounded — 20s times 1.5 is 30s.
  4. **The budget counted attempts, not seconds.** Four attempts against an
     upstream that takes 30s to time out is two minutes inside one tool call,
     and an attempt count never says so. Now 25s for the whole call, anchored
     on the MCP SDK's `MCP_DEFAULT_TIMEOUT = 30.0`.
  5. **Nothing held that budget.** It is now an `asyncio.timeout` wall-clock
     deadline rather than an httpx timeout: httpx bounds each *operation*, and
     its read timeout restarts with every chunk, so a slowly trickling response
     outlived the budget without any single read expiring.
  6. **`uvg.py` interpolated the empty message.** `UvgSourceUnavailableError`
     stays — it is a typed error and the degraded cache path depends on it —
     but the message read `f"{url} nach 3 Retries: {last_error}"`, and
     `httpx.ConnectTimeout`, `ReadTimeout` and `ConnectError` all carry an
     **empty** `str()`. Those are the only errors a real outage produces, so
     the sentence stopped at the colon and named neither the failure mode nor
     the host. It now names the exception type, the host and which of the two
     limits ran out. `server.py::_fetch_text_cached` returns `None` on failure
     and never had this problem.

  **Both call sites now share one policy module.** `server.py` and `uvg.py`
  each carried their own copy of the same `(2.0, 4.0, 8.0)` ladder. That is the
  portfolio's mistake one scale down — the defect these functions inherited came
  from a template copied into eleven servers, and inside this package the same
  code was copied twice. Two copies drift, and a drifted retry is invisible:
  nothing fails, one path is just less patient than the other. The new
  `retry_policy.py` holds the shared half; what is retried stays with each call
  site, because their non-retryable statuses genuinely differ (`uvg.py` treats a
  404 on `Ts27.pdf` as an answer, not an outage).

  New `tests/test_retry_policy.py`: `Retry-After` in both forms plus the
  refusal cases, the jitter spread, that the cap binds after jittering, and the
  one-sided `Retry-After` jitter.

### Added

- **Unfallstatistik UVG (SSUV): drei Tools für Berufsunfälle und
  Berufskrankheiten** — `seco_get_uvg_overview` (Schlüsselzahlen Gesamtschweiz),
  `seco_get_uvg_by_branch` (Ergebnisse nach NOGA-2008-Wirtschaftszweig) und
  `seco_get_uvg_trends` (Zehnjahres-Zeitreihe je Branche). Damit deckt der
  Server die Risikoseite desselben Arbeitsmarkts ab, den die Arbeitslosen-Tools
  beschreiben. Tool-Bestand: 12 von maximal 15.

  Herausgeber ist die Koordinationsgruppe KSUV mit der Sammelstelle SSUV c/o
  Suva — **nicht das SECO**. Das Präfix `seco_` adressiert den Server, nicht die
  Quelle; das Feld `source` jeder Response nennt den Herausgeber ausdrücklich.

  Architektur C (dump-first), empirisch begründet in `PROBE_REPORT_UVG.md`: Die
  Quelle hat keine API, ein Link-Scan über alle Datenseiten ergab 165 PDFs und
  null maschinenlesbare Datendateien.

  **Nutzungsrechte:** Die UVG-Daten sind nicht offen lizenziert («Abdruck ausser
  für kommerzielle Nutzung mit Quellenangabe gestattet»). Die MIT-Lizenz dieses
  Repos deckt den Code, nicht die Zahlen. Die Einschränkung steht deshalb in
  jedem Envelope und nicht bloss im README — ein README wird dem Modell nicht
  weitergereicht.

### Known findings

Vier Eigenheiten der Quelle, die jede für sich zu einem stillen Datenfehler
geführt hätten. Sie stehen hier, damit derselbe Griff beim nächsten
PDF-basierten Portfolio-Server nicht neu erarbeitet werden muss.

- **Zwei unvereinbare Zahlenformate in derselben Quelle.** Die Jahresausgabe
  trennt Tausender mit einem gewöhnlichen Leerzeichen und Dezimalstellen mit
  Komma (`1 097 154`, `137,5`), die Branchen-PDF mit Apostroph und Punkt
  (`1'057`, `4.25`).

  Der Leerzeichen-Trenner ist der gefährliche Fall, weil er dasselbe Zeichen ist,
  das auch Spalten trennt: `166 534 234` ist als `166534234` genauso lesbar wie
  als `166 534 | 234`. Ein `split()` liefert dann plausible Integers und kein
  Fehlersignal — ein Parser, der nicht abstürzt, sondern lügt. Aus dem Textlayer
  allein ist das nicht auflösbar; die Zahlen kommen deshalb aus dem
  Layout-Extraktionsmodus, wo die Spaltenabstände des Satzes erhalten bleiben.
  Die Trennschwelle ist gemessen, nicht geraten: Lücken innerhalb von Zahlen
  reichen bis 10 Leerzeichen, die kleinste Lücke zwischen zwei Spalten misst 113.

  *Schweizer Statistik-PDFs trennen Tausender mit demselben Zeichen wie Spalten —
  wer beides gleich behandelt, bekommt aus 1 097 154 Vollbeschäftigten drei
  Zahlen und keine Warnung.*

- **Der Stern ist Information.** Werte erscheinen als `162*` oder `*145`. Laut
  `Beschrieb_Branchen_d.pdf` markiert er eine statistisch signifikante
  Veränderung zum Vorjahr. Ihn wegzuwerfen hiesse, jede Bewegung gleich
  bedeutsam aussehen zu lassen; er bleibt als Feld `significant` je Datenpunkt
  erhalten.

- **Die Indexseiten der Quelle sind unzuverlässiger als ihre Dateien.**
  `branchen_d.htm` nennt «Letzte Aktualisierung: 07.11.2023», während die
  verlinkten PDFs `Version: 2.01.00 / 09.01.2026` tragen. `jahr_d.htm` verlinkt
  noch `Ts25.pdf`, obwohl `Ts26.pdf` seit Juni 2026 online ist. Folglich wird
  `source_freshness` aus der Datei abgeleitet und die aktuelle Ausgabe durch
  direktes Proben von `Ts{YY}.pdf` ermittelt, nicht durch Scrapen des Index.

- **Die Quelle rundet gegen sich selbst.** In der Ausgabe 2025 ergeben die
  gedruckten Sektorzeilen der Tabelle 1.2 zusammen 4 469 213 bei einem
  gedruckten Total von 4 469 212 — im Rohtext bestätigt, also eine Differenz der
  Publikation, nicht der Extraktion. Die Summenprobe prüft deshalb auf Toleranz
  statt auf exakte Gleichheit: Rundung ist 1, ein gebrochenes Layout sind
  Grössenordnungen.


- **Versions-Badge in beiden READMEs** (`0.3.4`). Bis jetzt war die Version im
  README nur über den dynamischen PyPI-Badge sichtbar, und `C8` meldete auf
  INFO-Ebene, dass es keinen Anker zum Abgleichen gibt — «nichts gefunden» soll
  nicht wie «alles in Ordnung» aussehen.

  Ein hartkodierter Badge ist nur dann eine Verbesserung, wenn ihn etwas bewacht
  — sonst führt er genau die Drift ein, gegen die der Check existiert. Hier
  bewacht ihn `scripts/check_version_sync.py`, das bereits in der CI läuft: es
  nimmt den Badge jetzt in beiden Sprachfassungen mit auf. Gegengeprüft, dass
  die Bewachung auch greift — mit einem auf `0.9.9` verstellten Badge meldet der
  Check `DRIFT` und beendet sich mit Exit 1.

### Fixed

- **Laufzeit-Abhängigkeiten mit Obergrenzen versehen** (`fastmcp<4`, `httpx<1`,
  `pydantic<3`). Alle drei standen nach oben offen, und für alle drei liegt der
  nächste Major-Sprung bereits auf PyPI: `fastmcp 4.0.0b1`, `httpx 1.0.dev*`.
  Eine Beta wird von pip zwar nicht ohne `--pre` gezogen — der erste stabile
  Release desselben Majors aber sehr wohl, und dann ohne eine einzige
  Codeänderung hier.

  Relevant für die laufende Fleet-Migration auf MCP-Spec 2026-07-28: `fastmcp`
  3.x zieht `mcp<2.0` (aufgelöst: `mcp 1.29.0`), während `mcp 2.0.0` bereits
  stabil ist. Der Schritt auf `mcp 2.x` soll ein bewusstes fastmcp-Upgrade sein,
  nicht die Nebenwirkung eines offenen Ranges. Die Schranken frieren den
  verifizierten Stand ein, ohne ihn zu verschieben: vor und nach der Änderung
  lösen dieselben Versionen auf (`fastmcp 3.4.5`, `httpx 0.28.1`,
  `pydantic 2.13.4`), 69 Offline-Tests bleiben grün.

- **`ruff` mit Obergrenze gepinnt (`>=0.5.0,<0.17`).** ruff ist pre-1.0; seine
  Minors sind die Stelle, an der Regelverhalten und neue Checks innerhalb der
  gewählten Familien landen. Ohne Cap installiert die CI die jeweils neuste
  Version und wird ohne Codeänderung rot.

  Der Cap liegt bewusst über dem tatsächlich verwendeten Stand (`0.16.x`). Ein
  `<0.16` hätte die Schranke zwar gesetzt, dabei aber still auf `0.15`
  zurückgedreht — eine Obergrenze soll den Stand einfrieren, nicht nebenbei ein
  Downgrade auslösen.

- **Emoji aus vier Überschriften entfernt** — `# 💼 SECO Labor Market MCP Server`
  in beiden Sprachfassungen sowie `## 🛡️ Safety & Limits` /
  `## 🛡️ Sicherheit & Grenzen`. Vorher nach Regel E4 geprüft: beide Dateien
  enthalten null `](#…)`-Anker, es bricht also kein Link. Emoji im Fliesstext
  bleiben unangetastet.

- **Zehn blinde `pytest.raises(Exception)` in `tests/test_unit.py` ersetzt.**
  Alle zehn prüfen Pydantic-Schranken, und alle zehn bestanden auch dann, wenn
  gar nicht mehr die Schranke griff: ein vertippter Feldname scheitert ebenfalls,
  nur als `extra_forbidden`.

  Der Feldname allein hätte nicht gereicht. Fünf der Tests prüfen **beide Enden
  derselben Schranke** (`limit=25`/`limit=0`, `year=1999`/`year=2031`,
  `month=13`/`month=0`) — eine auf den Feldnamen gestützte Assertion wäre für
  beide Hälften identisch und hätte ein vertauschtes `ge`/`le` nicht bemerkt.
  Umgekehrt trägt `MonthlyReportInput` Bounds auf `year` *und* `month`, sodass
  der Fehlertyp allein eine Feldverwechslung durchgelassen hätte.

  Der neue Helper `assert_rejects(build, error_type, field)` prüft deshalb beides
  gegen die strukturierte Fehlerliste — `type` und `loc` statt `match=` auf dem
  Meldungstext, der bei Pydantic-Upgrades beweglich ist.

  Per Mutationstest gegengeprüft; unter jeder Mutation bestand die alte
  Assertion und fällt die neue durch:

  | Mutation | alt | neu |
  |---|---|---|
  | obere Schranke prüft unteren Wert | bestanden | fällt durch |
  | `month`-Bounds-Test trifft `year` | bestanden | fällt durch |
  | Feldname `response_formt` vertippt | bestanden | fällt durch |
  | Feldname `quer` vertippt | bestanden | fällt durch |

## [0.3.4] - 2026-07-30

### Fixed

- **The User-Agent reports the actual package version again.** The published
  `0.3.3` sent `seco-labor-mcp/0.3.0` to every upstream — the version string was
  hardcoded and had been left behind by earlier bumps. The version now comes
  from the package metadata, so it can no longer drift from the package.

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
