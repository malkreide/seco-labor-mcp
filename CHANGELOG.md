# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Behoben

- **Zug las den zweiten Datensatz ungeprüft — und hätte die
  Jugendarbeitslosigkeit still verloren.** Die Anzahlen stehen in
  `arbeitsmarktstatistik`, die Quoten in `arbeitslosenquote`. Für die erste
  Datei prüfte `parse_zg` die Pflichtspalten, für die zweite nicht: sie wurde
  mit `.get("quote")` gelesen. Eine umbenannte Spalte liefert damit für jede
  Zeile `None` — keine Ausnahme, keine leere Antwort, sondern eine Antwort
  ohne beide Quoten, weil die Anzahlen aus der ersten Datei ja noch dastehen.
  Verloren wäre genau die **Jugendarbeitslosenquote**, die der `hinweis` des
  Kantons als einzigen Weg zu dieser Zahl ausweist. Nachgestellt an der
  Aufzeichnung vom 2026-08-15: `Arbeitslosenquote` und
  `Jugendarbeitslosenquote` verschwinden, alles andere bleibt grün.

  `KantonsReihe` führt jetzt `felder_zweite`, und der zweite Datensatz läuft
  durch dieselbe Prüfung wie der erste. Der neue Live-Test hält die im
  Register deklarierten Kennzahlen gegen die jüngste Periode, statt nur
  «irgendwelche Datenpunkte» zu zählen.

- **Die kantonale CSV wurde nach Position gewählt, nicht nach Inhalt.**
  Derselbe Griff wie bei der französischen BFS-Mappe, eine Ebene tiefer:
  `_erste_csv_url` nahm die erste CSV-Ressource des Pakets. Zugs
  `arbeitsmarktstatistik` führt aber **zwei** — die Reihe
  (`jahr,monat,kennzahl,anzahl`) und eine nach Altersgruppen
  (`jahr,monat,altersgruppe,anzahl`), geprüft am 2026-08-29. Sie unterscheiden
  sich in genau einer Spalte; nennt CKAN die falsche zuerst, fällt der Adapter
  mit `Spalten fehlen: ['kennzahl']`. Laut immerhin — aber rot ohne Ursache im
  Diff, und das ist die Nacht, die niemand einordnen kann.

  Anders als beim BFS hilft hier keine Sprachwahl: beide Ressourcen führen
  `language: []`. Gewählt wird deshalb an den Spalten, die der Adapter ohnehin
  braucht — `_csv_mit_den_erwarteten_spalten` prüft die Kandidaten in der
  Reihenfolge, in der CKAN sie nennt, und hört beim ersten Treffer auf. Steht
  die richtige vorn, kostet das genau einen Abruf wie zuvor; ein Test hält das
  fest. Gepinnt ist dafür nichts Zusätzliches: kein Titel, keine
  Ressourcen-Nummer, nur `felder`, das es schon gab.

  Beobachtet ist der Positionswechsel bei Zug **nicht** — belegt ist er für
  die BFS-Tabelle im selben Portal. Die Annahme fällt trotzdem, weil sie
  nirgends zugesichert ist und der Fehlerfall dieselbe Nacht kostet.

  `scripts/record_fixtures.py` trug denselben Griff und hätte an einem solchen
  Tag eine andere Datei aufgezeichnet, als der Server liest. Eine Fixture, die
  etwas anderes belegt als den Produktivpfad, belegt nichts — der Recorder
  wählt jetzt gleich.

### Behoben

- **Die Live-Suite las an manchen Tagen die französische Arbeitsmappe.** Der
  gepinnte BFS-Datensatz führt dieselbe Tabelle zweimal — `je-d-03.03.00.01`
  und `je-f-03.03.00.01`. Beide tragen Format `XLS`, beide das Blatt
  `T3.3.0.1`; übersetzt sind nur die Zeilenbeschriftungen, nach denen
  `sources.REIHEN` wörtlich sucht. `_bfs_jahresreihe` nahm die *erste*
  XLS-Ressource, und über deren Reihenfolge sagt CKAN nichts zu.

  Ergebnis war ein Münzwurf: die nächtlichen Läufe vom 25. und 26.8.2026 fielen
  mit «Reihen nicht gefunden» und französischen Beschriftungen in der Meldung,
  der Lauf davor und die beiden danach waren grün — bei unverändertem Code und
  unveränderter Quelle. Als Ausfall der Quelle gelesen wäre das ein Fehlalarm
  gewesen, als Formänderung eine falsche Diagnose.

  `_deutsche_xls_ressource` wählt jetzt nach Sprache statt nach Position, aus
  dem DCAT-Feld `language` und ersatzweise den nicht leeren Schlüsseln des
  mehrsprachigen `title`. Bekennt sich keine Ressource zu einer Sprache, bleibt
  es beim bisherigen Griff — dann gibt es nichts zu entscheiden. Bekennen sie
  sich und Deutsch ist nicht dabei, ist das eine benannte Ausnahme und keine
  übersetzte Mappe, die als deutsche durchgeht.

  Die Aufzeichnung vom 2026-08-15 trägt beide Mappen bereits, und die
  Reihenfolge-Gegenprobe in `test_recorded_fixtures.py` dreht sie um: mit der
  alten Auswahl fällt sie, mit der neuen nicht. Der Fehlschlag ist damit
  offline reproduzierbar und hängt nicht daran, in welcher Reihenfolge CKAN
  gerade antwortet.

### Hinzugefügt

- **Ein Gate für die MCP-Protokollrevision.** Bisher stand dazu nirgends etwas —
  keine Konstante, kein Satz in einer README, kein Test. Ein SDK-Bump, der die
  Revision ändert, wäre lautlos durchgelaufen: alles grün, andere Revision am
  Draht. `tests/test_protocol_version.py` hält jetzt drei Dinge gegeneinander:
  die dokumentierte Revision `2025-11-25`, `LATEST_PROTOCOL_VERSION` aus dem
  SDK, und die Revision, die ein echter `initialize` gegen das Server-Objekt
  zurückgibt.

  Beide READMEs bekommen den Abschnitt «MCP-Protokollversion», und der Test
  prüft beide einzeln — nur die englische anzusehen wäre genau die Lücke, an der
  die zwei anderswo im Portfolio schon auseinandergelaufen sind.

  Anders als die Schwester-Server pinnt dieser **eine** Revision, kein Paar:
  fastmcp 3.x zieht `mcp` 1.x herein, wo es `mcp.types.version` nicht gibt und
  die Zwei-Ären-Frage sich nicht stellt. `test_das_sdk_kennt_hier_nur_eine_aera`
  ist an das SDK gebunden statt an einen Kommentar und fällt, sobald ein Upgrade
  die beiden Konstanten hereinzieht.

## [0.4.0] - 2026-08-15

### Added

- **Die Pruefsummen im Fixture-Nachweis waren Zierde.** `PROVENANCE.md` fuehrt
  je Datei einen SHA-256 — um genau einen Fall zu fangen: eine Aufzeichnung,
  die nach dem Lauf von Hand nachgebessert wurde. Eine korrigierte Antwort ist
  wieder eine erfundene, und von aussen ist ihr das nicht anzusehen.
  Nachgerechnet hat sie kein Test. `test_die_pruefsumme_im_nachweis_stimmt`
  tut es jetzt, ueber die Bytes auf der Platte statt ueber den Loader — genau
  die hat der Recorder gehasht.

- **Drei Wächter statt einem, weil zwei den Fall nicht gefangen hätten.**
  `test_beide_pfade_gehen_ueber_ihren_modul_alias` prüft die Module,
  `test_kein_test_patcht_die_wartezeit_am_fremden_modul` die Tests — beide
  hätten hier **nichts gemeldet**: es gab keinen Patch am fremden Modul und
  keinen direkten `asyncio.sleep` im aufgerufenen Pfad, sondern eine Fixture,
  die eine harmlose Konstante traf. Deshalb misst
  `test_die_fixture_nullt_die_wartezeit_wirklich` die Wartezeit selbst. Der
  Abstand trägt: mit wirksamer Fixture Millisekunden, ohne sie elf Sekunden,
  Schranke bei einer.
- `test_der_uvg_retry_fragt_die_leiter_ab` lässt den Alias mitschreiben und
  prüft die Werte gegen 2/4/8 samt Jitter-Bandbreite.
- **Die kantonale Schicht: vier Kantone publizieren ihre RAV-Zahlen selbst.**
  `seco_get_unemployment_overview(canton=…)` liefert für **TG, FR, ZG und ZH**
  echte Werte statt einer Absage — monatlich für die ersten drei, jährlich nach
  Gemeinde für Zürich. Gepinnt sind wieder die CKAN-Kennungen, nie die
  Portal-URLs der Kantone; ein Live-Test prüft jede gegen die Quelle.
- **Jugendarbeitslosigkeit, in den zwei Kantonen, die sie führen.** TG liefert
  eine **Anzahl** (Altersklasse 15–24, monatlich seit 2016), ZG eine **Quote**
  (seit 1993). Beide stehen so in der Antwort, wie der Kanton sie publiziert —
  eine Umrechnung bräuchte die Bezugsgrösse, die keiner der beiden mitliefert.
  Zürich publiziert Arbeitslose, aber nicht nach Alter; das ist ein dritter
  Fall und wird auch als solcher beantwortet.
- **Vier Kantone, vier Adapter.** Jedes Statistikamt publiziert mit eigenen
  Spaltennamen, eigener Zeitachse und eigenem Begriffsumfang. Ein gemeinsamer
  Parser müsste raten; stattdessen liest jeder Adapter genau ein Schema und
  scheitert bei jeder Abweichung laut. Das hat sich beim ersten Lauf sofort
  gelohnt — siehe unten.


- **`sources.py`: das gepinnte Register und der Parser der BFS-Jahrestabelle.**
  Die Reihenbeschriftungen stehen wörtlich darin, statt über Zeilenpositionen
  geraten zu werden: schiebt das BFS eine Zeile ein, ist eine falsche Zahl das
  Ergebnis einer Positionsannahme, aber eine benannte Ausnahme das einer
  Beschriftungssuche. Fehlt eine Reihe, fliegt `TabelleNichtLesbarError` mit
  den tatsächlich gefundenen Beschriftungen in der Meldung.
- **Die ILO-Falle ist ausdrücklich abgesichert.** Dieselbe Tabelle führt
  registrierte Arbeitslose (SECO) und Erwerbslose gemäss ILO (BFS)
  untereinander; im Jahr 2000 ist die ILO-Zahl das **1.76-fache**. Der Server
  gibt beide getrennt und beschriftet aus, und je ein Offline- und ein
  Live-Test hält den Abstand fest.
- **`_fetch_bytes_with_retry`** mit der Portfolio-Leiter 2s/4s/8s, `Retry-After`
  und dem 25-Sekunden-Budget. Ohne sie stand der neue Abruf nackt da: ein
  einziger `client.get` gegen einen Asset-Host, der die TLS-Verhandlung
  sporadisch abbricht — beim Aufzeichnen der Fixtures zweimal in Folge.
  Gepatcht wird über den Modul-Alias `_sleep`, nicht über `asyncio.sleep`.
- **Zwei Aufzeichnungen für den neuen Weg**: `package_show` auf die gepinnte
  Kennung und die XLS-Ressource, die dort steht. Die Asset-URL wird bewusst
  nicht zweitgepinnt — sie ändert sich bei jeder Neupublikation.
- **`openpyxl`** als Abhängigkeit. Die Reihe gibt es nur als XLSX; weder CSV
  noch SDMX, geprüft am 2026-08-14.
- **Eine aufgezeichnete Antwort je externem Endpunkt**, in `tests/fixtures/`,
  mit Herkunft, Aufnahmedatum, Auswahlregel und SHA-256 je Datei in
  `tests/fixtures/PROVENANCE.md`. Neu aufzeichnen mit
  `python scripts/record_fixtures.py`, geladen wird über `tests/fixture_data.py`.
  Aufgezeichnet sind beide CKAN-Aktionen, eine CSV-Ressource, die beiden
  HTML-Seiten von unfallstatistik.ch und zwei PDFs. Gekürzt ist immer die Zahl
  der Einträge — Zeilen einer CSV, Seiten eines PDF —, nie ihr Inhalt.
  Die übrige Suite arbeitet auf *nachgebildeten* Fixturen; `test_uvg.py` sagt
  das selbst: «Was diese Tests nicht können: eine falsche Grundannahme fangen.»
  Genau diese Lücke schliessen die Aufzeichnungen — sie haben in diesem Zug
  zwei Defekte und einen Quellenbefund aufgedeckt.
- **Befund vom 2026-08-14 in `PROVENANCE.md`: der gepinnte Organisationsfilter
  trifft niemanden mehr.** `SECO_ORG` gibt es auf opendata.swiss nicht (mehr) —
  `organization_show` antwortet 404, und in den 176 Einträgen von
  `organization_list` kommt kein SECO vor. Dieselbe Suche liefert mit `fq`
  **0** und ohne `fq` mehrere tausend Treffer; beide Antworten sind
  aufgezeichnet. Wirkung: alle sechs CKAN-gestützten Werkzeuge liefern nichts.
  Bewusst nicht in diesem Zug behoben — den Filter zu streichen wäre keine
  Reparatur, sondern eine andere Zusage: die Antworten hiessen weiter
  «SECO-Datensätze», wären aber Daten des BFS und der Kantone.


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

### Changed

- **Befund aus #28 korrigiert: es gibt doch eine maschinenlesbare monatliche
  Schweizer Reihe.** Sie steht nicht in einem Datensatz *über* die Schweiz,
  sondern als Vergleichszeile `Suisse / Schweiz` in der **Freiburger** Reihe —
  monatlich seit 2004. Die Aussage «keine monatliche Quelle» galt für die
  Suche nach nationalen Datensätzen und war insofern zu weit gefasst. Sie ist
  in README, Werkzeugtexten und Nachweis nachgezogen.
- **Der Server liest die SECO-Zahlen jetzt über eine gepinnte Kennung statt über
  einen Organisationsfilter.** Der Filter auf
  `organization:staatssekretariat-fur-wirtschaft-seco` war ein Namensabgleich,
  und als die Organisation von opendata.swiss verschwand, lief er still ins
  Leere: jede Suche null Treffer, jedes Werkzeug «Keine SECO-Datensätze
  gefunden». An seine Stelle tritt ein Literal-Register in `sources.py` —
  dasselbe Muster wie `CANTON_INSTITUTION_IDS` in `swiss-procurement-mcp`.
  Das verschiebt den Fehler von *still* nach *laut*: `test_live.py` prüft jede
  Kennung gegen die Quelle, und eine verschwundene Kennung ist ein roter Test
  statt einer leeren Antwort.
- **Herausgeber und Datenquelle werden getrennt benannt.** Die registrierten
  Arbeitslosen und Stellensuchenden sind SECO-Zahlen aus dem RAV-System;
  veröffentlicht werden sie vom BFS in Tabelle `T3.3.0.1`, das SECO in seiner
  Fusszeile als Quelle nennt. Jede Antwort führt beide Häuser. Der Server
  behauptet nicht mehr, SECOs eigenes Portal zu lesen — amstat.ch ist eine
  MicroStrategy-Anwendung ohne Schnittstelle.
- **`seco_search_datasets` sucht ohne Herausgeberfilter und zeigt bei jedem
  Treffer, von wem er stammt.** Datensätze zum Arbeitsmarkt gibt es; sie
  stammen vom BFS, von Kantonen und vom liechtensteinischen Amt für Statistik.
  Sie unter der Überschrift «SECO-Datensätze» zu zeigen wäre genau die
  Verwechslung, die dieser Umbau behebt.

### Removed

- **Die statischen Referenz-Snapshots.** `seco_get_unemployment_overview` gab
  bei jedem Aufruf 147'275 Arbeitslose und 3.2 % aus (Dezember 2025) samt einer
  fest eingetragenen Kantons-Rangliste vom **April 2025**;
  `seco_get_youth_unemployment` nannte «+2'186 Jugendarbeitslose (+18.6 %)» als
  Beispielwert. Weil der CKAN-Filter nie traf, war das nicht der Ausnahme-,
  sondern der **einzige** Pfad: ein Werkzeug namens «Aktuelle Arbeitslosigkeit
  Schweiz», das seit Monaten April-Zahlen lieferte. Die Warnhinweise daneben
  ändern daran wenig — gelesen und zitiert wird die Zahl, nicht der Hinweis.
  Eine Absage kann man nicht falsch zitieren.
- **Der CSV-Zweig** (`_try_live_csv`, `_fetch_text_cached`, `_parse_csv`,
  `_select_rows_for_canton`, `_detect_latest_period` und der Cache dazu). Nach
  der Umstellung auf die gepinnte Tabelle rief ihn kein Werkzeug mehr auf.
  Ungenutzter Code, den Tests grün halten, sieht aus wie eine Fähigkeit —
  dieses Repo hat die Lektion schon einmal aufgeschrieben, damals über einen
  Cache, der nie einen Treffer liefern konnte. Die Retry-Zusicherungen dieses
  Pfades sind nicht verloren, sondern auf `_fetch_bytes_with_retry` portiert.
  Kommt eine kantonale Schicht (Thurgau publiziert monatlich nach Alter), holt
  die Git-Historie ihn zurück.
- **`seco_get_youth_unemployment`, `seco_get_open_positions` und
  `seco_get_unemployment_by_occupation` geben keine Zahlen mehr aus.** Für alle
  drei gibt es keine maschinenlesbare Quelle — «Jugendarbeitslosigkeit» liefert
  portalweit **null** Datensätze. Sie sagen das jetzt, nennen die Stelle, wo
  die Werte interaktiv stehen, und behalten die fachliche Einordnung, die als
  solche gekennzeichnet ist. Ein Werkzeug, das für «Jugendarbeitslosigkeit im
  Kanton Bern» eine national aggregierte Zahl zurückgibt, ist schlechter als
  eines, das nichts zurückgibt.

### Fixed

- **Die UVG-Testfixture nullte die Wartezeit nicht — sie sah nur so aus.** Sie
  setzte `UVG_BACKOFF_SECONDS` auf `(0.0, 0.0, 0.0)`, mit dem Docstring
  «Backoff im Test auf null setzen». Seit dem Wechsel auf `retry_policy` kommt
  die Wartezeit aber aus `RETRY_BASE_DELAY`; die Liste bestimmte nur noch die
  **Anzahl** der Versuche — und drei Nullen sind genauso lang wie drei Zahlen.
  `test_uvg.py` wartete deshalb die echte Leiter 2/4/8 ab: **96 statt 2.9
  Sekunden** bei identischen 58 Tests. Gefallen ist dabei kein einziger Test.
  Das Modul legt die Naht jetzt als `_sleep = asyncio.sleep` offen, und die
  Konstante heisst `UVG_VERSUCHE`, weil sie nur noch das ist.


- **Zürich mischte Kanton, Bezirke und Gemeinden in einer Liste.** «Zürich -
  ganzer Kanton», «Bezirk Horgen» und «Region Glattal» stehen in der Quelle in
  derselben Spalte `GEBIET_NAME` wie die Gemeinden. Eine nach Grösse sortierte
  Liste zeigte damit den Kantonswert als grösste «Gemeinde» — 18'887 vor
  Zürich mit 6'224. Unterschieden werden sie an `BFS_NR`: Aggregate tragen 0.
  Der Adapter trennt beides und weist den Kantonswert eigens aus.
- **Freiburg wurde über die falschen Spaltennamen gelesen.** Die über CKAN
  verlinkte Ressource trägt **beschriftete** Spalten (`Total chômeurs`), nicht
  die technischen Namen des Portals (`chomeurs_en_tout`). Beide Formen
  existieren; gelesen wird jetzt die, auf die die gepinnte Kennung zeigt. Der
  Schema-Check hat den Unterschied beim ersten Lauf gemeldet, statt eine leere
  Reihe zu liefern — genau wofür er da ist.


- **`seco_get_dataset` stürzte für jeden Datensatz mit Ressourcen ab.** CKAN
  schickt `last_modified` mit — aber als `null`. Gemessen **165 von 165**
  Ressourcen aus 38 Datensätzen. `r.get("last_modified", "")` greift bei einem
  vorhandenen Schlüssel nicht zum Vorgabewert, und das anschliessende `[:10]`
  lief auf `None`: `TypeError`. Der handgeschriebene Stub setzte dort einen
  String, deshalb blieb die Suite grün. Jetzt `(… or "")[:10]`, an allen vier
  Stellen mit demselben Ausdruck — gleicher Absturz, sobald die Quelle auch
  dort `null` schickt.
- **Eine Strukturänderung von opendata.swiss wurde zu «keine SECO-Datensätze».**
  Sechs Werkzeuge lasen die Trefferliste mit zwei Defaults hintereinander:
  `search_result.get("result", {}).get("results", [])`.

  Fällt `result` weg, war `datasets` leer, und die Werkzeuge antworteten «Keine
  SECO-Datensätze für '<Suche>' gefunden» samt Vorschlägen für andere
  Suchbegriffe. Für das Modell ist das nicht davon zu unterscheiden, dass es zu
  dieser Anfrage wirklich nichts gibt — und der Hinweis, es mit
  «Arbeitslosigkeit» statt «Kurzarbeit» zu versuchen, macht den Ausfall noch
  überzeugender. **Fünf der sechs Stellen** sahen das `success`-Envelope dabei
  gar nicht erst an.

  Alle sechs laufen jetzt über `_ckan_results()`, das `result` **und**
  `results` bestätigt; `seco_get_dataset_details` nutzt `_ckan_result()` für
  denselben Wurzelpfad. Bei Abweichung fliegt `UpstreamSchemaError` mit den
  tatsächlich vorhandenen Schlüsseln in der Meldung.

  **Die Einordnung ist die eigentliche Entscheidung.** Der Typ ist
  `_to_execution_error` bewusst *unbekannt* und wird deshalb weitergereicht:
  Ein Ausführungsfehler gibt eine Zeichenkette an das Modell zurück, damit es
  etwas anderes versuchen kann — bei einer Formänderung gibt es nichts anderes
  zu versuchen. FastMCP macht daraus `isError: true` (OBS-001).

  `results: []` bleibt eine leere Suche mit der freundlichen Vorschlagsliste:
  Bestätigt wird die **Anwesenheit** des Schlüssels, nicht sein Inhalt.

  Gefunden im Portfolio-Durchlauf zu
  [`FID-006`](https://github.com/malkreide/mcp-audit-skill/blob/main/checks/FID-006.md)
  am 2026-08-07: Acht Server im Portfolio sprechen mit CKAN, sieben defaulteten
  `result`.


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
