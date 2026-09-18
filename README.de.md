> 🇨🇭 **Teil des [Swiss Public Data MCP Portfolios](https://github.com/malkreide)**

# SECO Labor Market MCP Server

![Version](https://img.shields.io/badge/version-0.4.0-blue)
[![CI](https://github.com/malkreide/seco-labor-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/malkreide/seco-labor-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/seco-labor-mcp)](https://pypi.org/project/seco-labor-mcp/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-purple)](https://modelcontextprotocol.io/)
[![No Auth Required](https://img.shields.io/badge/auth-none%20required-brightgreen)](https://github.com/malkreide/seco-labor-mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

🌐 **[English](README.md)** | **Deutsch**

Ein MCP-Server (Model Context Protocol) für Schweizer Arbeitsmarktdaten des **SECO** (Staatssekretariat für Wirtschaft) und **AMSTAT** via opendata.swiss.

<p align="center">
  <img src="assets/demo.png" alt="Demo: Claude fragt Jugendarbeitslosigkeit über seco-labor-mcp Tool Call ab" width="720">
</p>

---

## Übersicht

Dieser Server verbindet KI-Modelle mit offiziellen Schweizer Arbeitsmarktstatistiken – ohne API-Schlüssel, ohne Registrierung.

**Primäre Zielgruppen:**
- 🏫 **Schulamt / Bildungsplanung** — Jugendarbeitslosigkeit, Berufswahlberatung
- 📊 **Analyse & Forschung** — Arbeitsmarkttrends, Kantonsvergleiche
- 🤖 **KI-Agenten** — Automatisiertes Monitoring und Reporting

**Anker-Demo-Query:**  
*«Welche Berufsgruppen haben im Kanton Zürich die höchste Jugendarbeitslosigkeit, und welche Lehrberufe unterliegen der Stellenmeldepflicht?»*
[→ Weitere Anwendungsbeispiele nach Zielgruppe →](EXAMPLES.md)

---

## Datenquellen (Phase 1 – kein API-Schlüssel nötig)

| Quelle | Beschreibung | Status |
|--------|-------------|--------|
| [opendata.swiss](https://opendata.swiss/de/dataset) | CKAN-Katalog; die gepinnte BFS-Tabelle `T3.3.0.1` trägt die SECO-Jahresreihen | ✅ Aktiv |
| [arbeit.swiss](https://www.arbeit.swiss) | Monatliche Pressedokumentation (PDF) | ✅ Aktiv |
| [amstat.ch](https://www.amstat.ch) | AMSTAT-Referenzportal | ⚠️ JavaScript SPA |
| [unfallstatistik.ch](https://www.unfallstatistik.ch) | Unfallstatistik UVG (SSUV/KSUV c/o Suva) — Berufsunfälle und Berufskrankheiten | ⚠️ Nur PDF, keine API (siehe unten) |

---

## Woher die Zahlen kommen — und was fehlt

**SECO ist auf opendata.swiss kein Herausgeber (mehr).** Geprüft am 2026-08-14:
`organization_show` antwortet 404, und in den 176 Einträgen von
`organization_list` kommt kein SECO vor. Der Server filterte bis dahin jede
Suche auf diese Organisation und lieferte deshalb **nichts** — ein
Namensabgleich, der ins Leere läuft, sieht genau aus wie eine leere Suche.

Die registrierten Arbeitslosen und Stellensuchenden sind trotzdem SECO-Zahlen:
das **BFS veröffentlicht sie** in Tabelle `T3.3.0.1` und nennt SECO in der
Fusszeile als Quelle. Der Server liest diese Tabelle über eine **gepinnte
Datensatz-Kennung** (`sources.py`), die ein Live-Test gegen die Quelle prüft.

| Reihe | 2000 | 2025 |
|---|---|---|
| Registrierte Stellensuchende (SECO) | 124.6 | 214.1 |
| Registrierte Arbeitslose (SECO) | 72.0 | 133.7 |
| Erwerbslose gemäss ILO (BFS) | 126.5 | 248.5 |

*in Tausend, Jahresdurchschnitt*

Die drei Reihen messen **nicht dasselbe**: im Jahr 2000 ist die ILO-Zahl das
1.76-fache der registrierten. Der Server gibt sie getrennt und beschriftet aus
und rechnet sie nie ineinander um.

### Die kantonale Schicht: vier Kantone, vier Schemata

National gibt es keine Monatswerte — **vier Kantone publizieren ihre
RAV-Zahlen aber selbst**, jeder in seinem eigenen Portal mit eigenen
Spaltennamen. Für sie liefert `seco_get_unemployment_overview(canton=…)`
echte Werte:

| Kanton | Granularität | ab | Ebene | Besonderheit |
|---|---|---|---|---|
| **TG** | monatlich | 2016-01 | Kanton | einzige Reihe **nach Altersklasse** → Jugendarbeitslosigkeit als Anzahl |
| **FR** | monatlich | 2004-01 | Kanton **und Schweiz** | führt die Schweizer Monatszahl als Vergleichszeile mit |
| **ZG** | monatlich | 1993-01 | Kanton | Jugendarbeitslosigkeit nur als **Quote**, nicht als Anzahl |
| **ZH** | **jährlich** | 1991 | **Gemeinde** | keine Monatswerte; Bezirke und Regionen stehen in derselben Spalte wie die Gemeinden und werden getrennt |

**Die übrigen 22 Kantone bekommen eine benannte Absage**, keine Zahl aus
einem anderen Kanton und keine national aggregierte. Eine Teilabdeckung, die
sich wie eine vollständige anfühlt, ist schlimmer als gar keine.

Die vier Reihen sind **untereinander nicht vergleichbar** und ergeben addiert
keine Schweizer Zahl: verschiedene Zeitachsen, verschiedene Gebietsebenen,
und im Fall von ZG eine Quote statt einer Anzahl.

**Was es weiterhin nicht gibt:** Arbeitslose nach Berufshauptgruppe, offene
Stellen als nationale Reihe, und Jugendarbeitslosigkeit für die Schweiz oder
für 24 der 26 Kantone. Die betroffenen Werkzeuge sagen das und geben **keine**
Ersatzzahl aus. Interaktiv stehen diese Werte auf
[amstat.ch](https://www.amstat.ch/v2/amstat_de.html); dort gibt es keine
Schnittstelle, die ein Server ansprechen könnte.

---

## Tools

| Tool | Beschreibung | Hauptanwendung |
|------|-------------|----------------|
| `seco_search_datasets` | Arbeitsmarkt-Datensätze auf opendata.swiss suchen (mit Herausgeber je Treffer) | Datensatz-Discovery |
| `seco_get_dataset` | Vollständige Metadaten und Download-Links | Datenzugang |
| `seco_get_unemployment_overview` | Registrierte Arbeitslose: national jährlich, für TG/FR/ZG/ZH kantonal | Überblick |
| `seco_get_youth_unemployment` | Jugendarbeitslosigkeit (15–24 J.) — nur **TG** (Anzahl) und **ZG** (Quote) | 🎓 Berufswahlberatung |
| `seco_get_job_seekers` | Registrierte Stellensuchende, national, Jahresreihe ab 2000 | Weiterbildungsbedarf |
| `seco_get_open_positions` | Offene Stellen als Frühindikator — **keine nationale Reihe verfügbar** | Branchenanalyse |
| `seco_get_unemployment_by_occupation` | Aufschlüsselung nach Berufshauptgruppe — **keine maschinenlesbare Quelle** | 🎓 Berufswahl |
| `seco_get_monthly_report_url` | PDF-URL für SECO-Monatsberichte | Quellenverifizierung |
| `seco_list_cantons` | Alle 26 Kantonscodes und -namen | Hilfsfunktion |
| `seco_get_uvg_overview` | UVG-Schlüsselzahlen zu Berufsunfällen und Berufskrankheiten | Risiko-Überblick |
| `seco_get_uvg_by_branch` | Ergebnisse nach Wirtschaftszweig (NOGA 2008) | 🎓 Berufswahl |
| `seco_get_uvg_trends` | Zehnjahres-Zeitreihe je Branche | Trendanalyse |

12 von maximal 15 Tools.

---

## Unfallstatistik UVG (SSUV)

Die drei `seco_get_uvg_*`-Tools decken die Risikoseite desselben Arbeitsmarkts
ab, den die Arbeitslosen-Tools beschreiben: wie viele Berufsunfälle und
Berufskrankheiten je Branche anfallen und wie sich das über zehn Jahre
entwickelt.

**Herausgeber ist nicht das SECO.** Die Unfallstatistik UVG wird von der
Koordinationsgruppe KSUV und der Sammelstelle SSUV c/o Suva, Luzern
herausgegeben. Das Präfix `seco_` adressiert diesen Server, nicht die Quelle;
jede Response nennt den tatsächlichen Herausgeber im Feld `source`.

### Architektur-Entscheid: C (dump-first)

Live geprüft am 2026-08-05, vollständige Herleitung in
[`PROBE_REPORT_UVG.md`](PROBE_REPORT_UVG.md).

Die Quelle hat **keine API**. Ein Link-Scan über sämtliche Datenseiten ergab
165 PDFs und null Dateien mit `.csv`, `.xlsx` oder `.json`. opendata.swiss kennt
die Quelle nicht (`count=0` bei sechs von sieben Suchbegriffen), und die
BFS-dam-API ignoriert ihre Filterparameter stillschweigend. Übrig bleiben drei
Zugänge, die faktisch maschinenlesbar sind, aber nicht dafür gedacht:

| Zugang | Format | Aktualisierung |
|---|---|---|
| `schluesselzahlen_d.htm` | HTML-Tabelle, 5 Jahre, Gesamtschweiz | jährlich |
| `Ts{YY}.pdf` | Jahresausgabe, Tabellen 1.2 und 2.4 nach NOGA | jährlich, Juni |
| `WirtKl_{BUV\|NBUV}_{NN}.pdf` | Zehnjahres-Reihe je NOGA-Abteilung | jährlich, Januar |

PDFs werden 24 h gecacht und mit Backoff 2s/4s/8s geladen.

### Was jede Response mitliefert

- `source_freshness.data_year` — das **Datenjahr**, nicht das Ausgabejahr. Die
  Ausgabe 2026 weist 2024 aus; dieser Nachlauf von zwei Jahren steht da, statt
  im Kleingedruckten zu verschwinden.
- `totals_check` — die geparsten Zeilen werden summiert und gegen das in
  derselben Publikation gedruckte Total gehalten. Ein gebrochenes Layout fällt
  damit auf, statt zu einer plausibel aussehenden falschen Zahl zu werden.
- `significant` — die Quelle markiert statistisch signifikante Veränderungen
  zum Vorjahr mit einem Stern. Dieses Flag bleibt je Datenpunkt erhalten, damit
  eine Veränderung nur dort als bedeutsam gilt, wo die Quelle das sagt.

---

## Installation

### Claude Desktop (stdio)

Eintrag in `claude_desktop_config.json`:

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

### Cloud / HTTP

```bash
pip install seco-labor-mcp
MCP_TRANSPORT=http PORT=8000 seco-labor-mcp
```

`http` ist der Transport der Wahl — und der einzige, der die moderne
Protokoll-Ära trägt. Gegen dieses Server-Objekt gemessen: `http` handelt
**`2026-07-28`** aus, `sse` deckelt jeden Client auf **`2025-11-25`**, auch
einen, der die moderne Ära ausdrücklich anbietet. `sse` und `streamable-http`
bleiben für bestehende Deployments erreichbar;
`tests/test_transport_aera.py` fährt beide und hält fest, welche Ära dabei
wirklich herauskommt.

Der HTTP-Server bindet standardmässig auf **`127.0.0.1` (Loopback)**, um
NeighborJack in geteilten Netzen zu verhindern. Für Container-Deployments, die
Verkehr von aussen annehmen müssen, `HOST=0.0.0.0` ausdrücklich setzen — am
besten im Dockerfile bzw. in der Orchestrator-Konfiguration, und nur hinter
einem vorgelagerten Proxy oder einer Firewall:

```bash
HOST=0.0.0.0 MCP_TRANSPORT=http PORT=8000 seco-labor-mcp   # nur im Container
```

Ein unbekannter Wert in `MCP_TRANSPORT` bricht jetzt mit einer Fehlermeldung
ab. Vorher fiel er stumm auf stdio zurück — ein Tippfehler erzeugte damit
einen Server, der auf dem erwarteten Port schlicht nie erschien.

---

## Schlüsselkonzepte

### Arbeitslose vs. Stellensuchende

> **Eselsbrücke**: Arbeitslose ⊂ Stellensuchende — wie eine russische Matrjoschka.

| Begriff | Definition | Dez. 2025 |
|---------|-----------|-----------|
| Arbeitslose | RAV-gemeldet, sofort vermittelbar | ~149'000 (3.2%) |
| Stellensuchende | Alle RAV-Gemeldeten (inkl. Umschulung) | ~233'900 |

### Saisonalität der Jugendarbeitslosigkeit

- **Juli/August**: Starker Anstieg (Schulabgängerinnen und -abgänger ohne Anschlusslösung)
- **September/Oktober**: Rückgang (Lehrstellenantritt)
- Das verbleibende Residuum nach dem Herbstrückgang zeigt strukturellen Bedarf für **Brückenangebote**

### Stellenmeldepflicht (seit 2020)

Berufsarten mit Arbeitslosenquote ≥ 5% → offene Stellen müssen zuerst dem RAV gemeldet werden. Die Liste ändert sich jährlich. Für die Berufsberatung bedeutet das: Jugendliche in diesen Berufen haben durch Inländervorrang bessere Chancen.

---

## Bekannte Einschränkungen

- `amstat.arbeit.swiss` hat kein öffentliches REST API → Workaround via CKAN
- Kantonsebene-Detaildaten erfordern CSV-Download
- URL-Muster der Monatsberichte kann für ältere Reports abweichen
- UVG-Zahlen stammen aus PDF-Parsing — das Layout war über die Ausgaben 2025
  und 2026 stabil, ein Redesign kann es aber brechen. Der `totals_check` in
  jeder Response ist das, was einen solchen Bruch sichtbar statt still macht.
- UVG-Daten hinken rund zwei Jahre nach (Ausgabe 2026 weist 2024 aus)
- UVG-Branchendetails folgen NOGA 2008 und fassen Abteilungen teilweise
  zusammen (`41 – 42`, `77, 79 – 82`); eine kantonale Gliederung gibt es hier nicht
- Detaildaten jenseits der Publikationen liegen hinter dem CUG-Zugang der SSUV
  und sind für diesen No-Auth-Server ausser Reichweite

**Phase 2 (geplant):**
- Automatisches CSV-Caching (24h TTL)
- Direkte XLSX-Verarbeitung für kantonale Aufschlüsselungen
- Integration mit `zh-education-mcp` für Schulamt-spezifische Korrelationen

---

## Sicherheit & Grenzen

| Aspekt | Details |
|--------|---------|
| **Zugriff** | Read-only (`readOnlyHint: true`) — der Server kann keine Daten verändern oder löschen |
| **Personendaten** | Keine Personendaten — alle Quellen sind aggregierte, anonymisierte Statistiken |
| **Rate Limits** | Keine externen Limits; Server begrenzt Abfragen auf 20 Ergebnisse; 30 s HTTP-Timeout |
| **Authentifizierung** | Kein API-Schlüssel erforderlich — opendata.swiss und arbeit.swiss sind öffentlich zugänglich |
| **Lizenzen** | SECO-Daten unter [Creative Commons CCZero](https://creativecommons.org/publicdomain/zero/1.0/); UVG-Daten **nicht offen lizenziert** (nicht-kommerziell, siehe Datenlizenz) |
| **Nutzungsbedingungen** | Gemäss ToS von: [opendata.swiss](https://opendata.swiss/de/terms-of-use), [SECO](https://www.seco.admin.ch), [arbeit.swiss](https://www.arbeit.swiss) |
| **DSG / DSGVO** | Vollständig konform — keine Personendaten übermittelt oder gespeichert |

---

## Datenlizenz

Es gelten zwei verschiedene Lizenzen. Der Code dieses Servers steht in beiden
Fällen unter MIT — die Daten sind davon nicht gedeckt.

**SECO-/AMSTAT-Daten** auf opendata.swiss stehen unter **Creative Commons CCZero**.
Quelle: Staatssekretariat für Wirtschaft (SECO) — [seco.admin.ch](https://www.seco.admin.ch)

**Daten der Unfallstatistik UVG** sind **nicht** offen lizenziert. Die
Publikation hält fest:

> «Abdruck – ausser für kommerzielle Nutzung – mit Quellenangabe gestattet.»

Das ist eine Nicht-kommerziell-Klausel mit Quellenangabepflicht. Sie gehört
KSUV/SSUV und lässt sich durch die MIT-Lizenz dieses Repos nicht aufheben: MIT
deckt den Code, nicht die Zahlen, die der Code holt. **Wer diesen Server
kommerziell einsetzt, ist für die UVG-Tools nicht abgedeckt** — das ist direkt
mit der Sammelstelle zu klären (`unfallstatistik@suva.ch`). Jede UVG-Response
wiederholt die Einschränkung im Feld `source`, weil ein README dem Modell nicht
weitergereicht wird.

---

## MCP-Protokollversion

Dieser Server bedient auf fastmcp 4.x / `mcp` 2.x **zwei Protokoll-Ären** über
dasselbe Server-Objekt:

| Ära | Revision | Form |
|-----|----------|------|
| modern | **`2026-07-28`** | kein Handshake — `server/discover`, pro Anfrage ein eigener Umschlag |
| Handshake | **`2025-11-25`** | `initialize`, danach eine Sitzung mit Zustand |

Ein Client, der die moderne Ära anbietet, bekommt sie; einer, der nur den
Handshake kennt, wird weiter bedient. Beide sind in
`tests/test_protokoll_aeren.py` einzeln gepinnt — und beide werden *gemessen*:
Der Test handelt eine echte Verbindung gegen dieses Server-Objekt aus, statt
zwei Konstanten miteinander zu vergleichen.

Nur gegen `LATEST_PROTOCOL_VERSION` zu pinnen würde nicht reichen: In `mcp` 2.x
ist dieser Name ein Alias auf die *moderne* Ära. Die Handshake-Obergrenze
dürfte damit frei wandern — und genau die sprechen die meisten Clients im Feld.

Bis 0.4.0 lief dieser Server auf fastmcp 3.x, und das pinnt `mcp` 1.x. Dort ist
`2025-11-25` die höchste Revision, die das SDK überhaupt kennt; `2026-07-28`
war also nicht halb unterstützt, sondern gar nicht. Der Test, der früher den
Ein-Ära-Zustand bewachte, bewacht jetzt dessen Gegenteil: Er fällt, wenn ein
Downgrade die moderne Ära wieder wegnimmt.

Hinweis für alles, was Server-Metadaten liest: Auf einer modernen Verbindung
gibt es kein `InitializeResult`. Statt `initialize_result` die Ära-neutralen
`protocol_version` / `server_info` verwenden.

---

## Mitwirken

Entwicklungsrichtlinien finden Sie in [CONTRIBUTING.md](CONTRIBUTING.md)
([deutsche Version](CONTRIBUTING.de.md)).

---

## Sicherheit

Den Sicherheitsstatus und die Anleitung zum Melden von Schwachstellen finden Sie
in [SECURITY.md](SECURITY.md) ([deutsche Version](SECURITY.de.md)).

---

## Lizenz

Veröffentlicht unter der [MIT-Lizenz](LICENSE) — Copyright © 2026 Hayal Oezkan.

---

## Autor

**Hayal Oezkan** · [github.com/malkreide](https://github.com/malkreide)
