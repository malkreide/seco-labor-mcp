# Probe-Report — Unfallstatistik UVG (SSUV) für `seco-labor-mcp`

**Datum der Probe:** 2026-08-05
**Prüfling:** Aggregierte, anonymisierte Berufsunfall- und Berufskrankheitsstatistiken
der Sammelstelle für die Statistik der Unfallversicherung UVG (SSUV), Geschäftsstelle
c/o Suva, Luzern — publiziert unter [unfallstatistik.ch](https://www.unfallstatistik.ch/).
**Vorgehen:** «Probe, Plan, Patch» nach Skill `mcp-data-source-probe`, Schritt 1.
**Status:** Schritt 1 abgeschlossen. Schritt 2 wartet auf Freigabe.

**Ergebnis in einem Satz:** Die Quelle trägt — sie liefert genau die gesuchten Daten in
guter Tiefe und mit brauchbaren Frische-Signalen —, aber sie hat **keine API und kein
einziges maschinenlesbares Datenformat**; die Erweiterung ist deshalb nur als
Architektur C (dump-first, PDF-Parsing) machbar, und sie hängt an einer
**Lizenz-Entscheidung, die ich nicht allein treffen kann** (Abschnitt 6).

---

## 1. Quellenmatrix

Alle Proben mit browser-artigem User-Agent, Backoff 2s/4s/8s. HTTP-Codes sind
tatsächlich beobachtet, nicht aus der Doku übernommen.

| # | Quelle | URL | HTTP | Format | Status | Records / Umfang |
|---|---|---|---|---|---|---|
| 1 | Schlüsselzahlen | `/d/neuza/schluesselzahlen_d.htm` | 200 | **HTML-Tabelle** | ✅ nutzbar | 22 Kennzahlen × 5 Jahre (2021–2025) |
| 2 | Jahresausgabe «UVG-Statistik» | `/d/publik/unfstat/pdf/Ts{YY}.pdf` | 200 | PDF | ✅ nutzbar | 70 Seiten, 18 Tabellen, Jahrgänge `Ts00`–`Ts26` |
| 3 | Branchen-Zeitreihen | `/d/neuza/WirtKl_d/WirtKl_{BUV\|NBUV}_{NOGA}.pdf` | 200 | PDF | ✅ nutzbar | 165 Dateien, je 12 S., 10 Jahre (2015–2024) |
| 4 | Suva-Prämienklassen | `/d/neuza/suva_klasse_d.htm` → PDFs | 200 | PDF | ⚠️ nachrangig | 43 Klassen, Suva-only (nicht UVG-gesamt) |
| 5 | Quartalszahlen | `/d/neuza/quartal_d.htm` → PDFs | 200 | PDF | ⚠️ nachrangig | Q1 2026 bis 2000, nur Fallzahlen nach Versicherergruppe |
| 6 | Methodik-Beschrieb | `/d/neuza/Beschriebe/Beschrieb_Branchen_d.pdf` | 200 | PDF | ✅ Referenz | 6 S., Legende + Signifikanz-Definition |
| 7 | Fünfjahresbericht-Register | `/d/publik/fuenfjb/fuenfjb_index_d.htm` | 200 | HTML | ⚠️ Register | 3.3 MB Stichwortregister, keine Daten |
| 8 | CUG-Service | `/d/cug/` | 200 | — | ⛔ Phase 2 | Closed User Group, Zugang nicht offen |
| 9 | opendata.swiss (CKAN) | `/api/3/action/package_search` | 200 | JSON | ❌ **leer** | count=0 für alle UVG-Begriffe |
| 10 | BFS dam-api | `dam-api.bfs.admin.ch/hub/api/dam/assets` | 200 | JSON | ❌ **unbrauchbar** | Filterparameter werden ignoriert |
| 11 | BFS PXWeb | `pxweb.bfs.admin.ch/api/v1/...` | 400 / 500 | — | ❌ tot | kein erreichbarer Einstieg |

### 1.1 Format, Rhythmus, Lizenz, URL-Stabilität

| Aspekt | Befund | Beleg |
|---|---|---|
| **Format** | Kein JSON, kein CSV, kein Excel. Site-weit **null** maschinenlesbare Datendateien gefunden. Zwei echte HTML-Tabellen, alles Übrige PDF. | Link-Scan über alle Datenseiten: `ext histogram: Counter({'.pdf': 165})` |
| **Rhythmus Jahresausgabe** | Jährlich, Erscheinung Juni. `Ts26.pdf`: `Last-Modified: Fri, 12 Jun 2026`, PDF-`CreationDate: 2026-06-09`. | HEAD + PDF-Metadaten |
| **Rhythmus Branchen-Zeitreihen** | Jährlich, Erscheinung Januar. `Version: 2.01.00 / 09.01.2026`, `Last-Modified: 2026-01-09`. | Seite 1 jedes PDF + HEAD |
| **Datenstand (Lag)** | Ausgabe 2026 trägt **2024** als jüngstes vollständiges Branchenjahr. Schlüsselzahlen reichen bis 2025, teils lückenhaft. | Tabelle 1.2 «…, 2024»; Schlüsselzahlen-Spalte 2025 nur teilbefüllt |
| **Lizenz** | «Abdruck – **ausser für kommerzielle Nutzung** – mit Quellenangabe gestattet.» **Keine offene Lizenz**, kein CC, kein OGD-CH. | `Ts26.pdf`, Impressum S. 3 |
| **URL-Stabilität** | Sehr hoch. `Ts10.pdf` seit `Last-Modified: 2010-06-30` unverändert online — 16 Jahre stabile Archiv-URLs. Muster `Ts{YY}` deterministisch. | HEAD auf `Ts10.pdf` |
| **Fehlerverhalten** | Sauber. `Ts27.pdf` → 404, `WirtKl_BUV_XX.pdf` → 404, `WirtKl_BUV_00.pdf` → 404, gültige NOGA → 200. | Negativ-Proben |
| **Caching** | `ETag` **und** `Last-Modified` auf allen Assets → konditionale Requests möglich. | HEAD |
| **Zugangshürden** | Keine. Kein Auth, kein API-Key, kein Rate-Limit beobachtet, **kein UA-Gate** (Abruf ohne User-Agent liefert 200). Keine `robots.txt` (404). | Vergleichsprobe ohne UA |

---

## 2. Reality-Check gegen die offizielle Oberfläche

Pflichtschritt 1.4. Die Quelle hat kein Such-UI, daher Bestandsabgleich statt
Recall-Messung — plus eine interne Summenprobe, die als Ersatz-Ground-Truth taugt.

| Prüfung | Publiziert | Aus der Extraktion | Delta | Bewertung |
|---|---:|---:|---:|---|
| Unfälle total 2025 (Medienmitteilung Startseite) | «rund 937 000» | 936 965 (Schlüsselzahlen) | ~0 | ✅ deckungsgleich |
| Tabelle 2.4 BUV: Summe Sektoren I+II+III | — | 261 367 | — | — |
| … zzgl. Zeile «Unbekannt» | — | 79 | — | — |
| **Summe vs. gedruckte Zeile «Total»** | **261 446** | **261 446** | **0** | ✅ **exakt** |

Der letzte Vergleich ist der belastbarste Befund des ganzen Reports: Die aus dem PDF
extrahierten Zeilen addieren sich **exakt** auf das im selben PDF gedruckte Total. Das
validiert sowohl die Zahlenerkennung als auch die Zeilenabgrenzung, und es liefert eine
Invariante, die sich als Regressionstest festschreiben lässt (siehe 5.4).

Bedingung dafür: Die Zeile **«Unbekannt» (79 Fälle) darf nicht stillschweigend
wegfallen**. Wer nur die drei Sektoren summiert, landet bei 261 367 und liegt um 79
daneben — eine Abweichung, die klein genug ist, um unbemerkt zu bleiben, und die genau
deshalb gefährlich ist.

---

## 3. Architektur-Entscheid: **C (dump-first)**

Nach dem Entscheidungsbaum des Skills: *«Keine nutzbaren Endpoints, nur Dump → ARCH C».*

**Empirische Begründung:**

1. **Es gibt keine API.** Weder REST noch GraphQL noch SPARQL noch PXWeb. Kein einziger
   Endpunkt liefert strukturierte Daten. Der einzige `<form>` auf der Site ist eine
   Volltextsuche mit `method="get" action="/d/search.htm"`.
2. **Es gibt kein maschinenlesbares Format.** Der Link-Scan über sämtliche Datenseiten
   ergab 165 PDFs und null Dateien mit Endung `.csv`, `.xlsx`, `.json`.
3. **Die Katalog-Umwege sind alle tot** (Abschnitt 7): opendata.swiss kennt die Quelle
   nicht, BFS liefert keine brauchbare Schnittstelle.
4. **Dafür ist die Dump-Seite ungewöhnlich gut:** deterministische URL-Muster, 16 Jahre
   stabile Archiv-URLs, `ETag`/`Last-Modified`, sauberes 404-Verhalten, und ein
   Layout, das sich zwischen zwei Ausgaben als **identisch** erwiesen hat (siehe 4.6).

Architektur A scheidet mangels API aus, B mangels Live-Komponente, die einen Fallback
rechtfertigen würde. Bleibt C — und C ist hier keine Notlösung, sondern passt zu einer
Quelle, die ohnehin nur einmal jährlich neue Zahlen publiziert.

**Konsequenzen:**

- Loader lädt PDFs konditional (`If-None-Match` / `If-Modified-Since`) und cached auf
  Disk. TTL 24 h ist für eine jährlich aktualisierte Quelle grosszügig genug.
- `source_freshness` wird **nicht** aus dem Abrufzeitpunkt abgeleitet, sondern aus dem
  Versionsstring bzw. `Last-Modified` des PDF (siehe 4.4).
- Die aktuelle Ausgabe wird durch **direktes Proben** von `Ts{YY}.pdf` ermittelt, nicht
  über die Indexseite (siehe 4.5).

---

## 4. Fundstücke aus der Live-Probe

Diese Befunde sind der eigentliche Ertrag von Schritt 1. Jeder einzelne wäre beim
blinden Drauflosbauen zu einem stillen Datenfehler geworden.

### 4.1 Der Tausendertrenner ist ein gewöhnliches Leerzeichen

Nicht U+00A0, nicht U+2009 — **U+0020 SPACE**, 214-mal allein auf Seite 27.
`"1 097 154"` ist eine Zahl, `"4 831 5 0 4 0"` sind sechs. Ein `split()` auf Whitespace
zersägt jede Zahl in ihre Dreiergruppen und liefert trotzdem plausibel aussehende
Integers. Das ist der klassische Fall eines Parsers, der nicht abstürzt, sondern lügt.

> *Schweizer Statistik-PDFs trennen Tausender mit demselben Zeichen, mit dem sie Spalten
> trennen — wer beides gleich behandelt, bekommt aus 1 097 154 Vollbeschäftigten drei
> Zahlen und kein Fehlersignal.*

Dezimaltrenner ist zusätzlich das Komma (`137,5`), Prozent stehen als `0,8 %`.

### 4.2 Zeilenbeschriftungen brechen mit Trennstrich um

`"Herstellung von Nahrungsmitteln und Tabakerzeug -\nnissen"` — Bindestrich, Leerzeichen,
Zeilenumbruch. Vier Vorkommen pro Tabellenseite. Die Zahlen der Zeile stehen erst nach
dem Umbruch. Ein zeilenweiser Parser findet also Label-Zeilen ohne Zahlen und
Zahlen-Zeilen ohne Label. Fortsetzungszeilen müssen vor dem Parsen zusammengeführt und
das ` -` beim Verbinden entfernt werden.

### 4.3 Der Stern ist Information, kein Rauschen

Werte erscheinen als `162*`, `*155`, `*153`. Aus `Beschrieb_Branchen_d.pdf`, S. 5:

> «Statistisch bedeutsame, also signifikante Veränderungen der Erfolgskennzahlen zum
> Vorjahr sind mit einem Stern (\*) gekennzeichnet.»

Der Stern markiert **statistische Signifikanz gegenüber dem Vorjahr** und steht mal vor,
mal nach der Zahl. Ihn beim Parsen wegzuwerfen wäre Informationsverlust an genau der
Stelle, an der ein Modell sonst «Anstieg» sagt, wo «nicht signifikanter Anstieg» richtig
wäre. Vorschlag: als eigenes Feld `significant: bool` je Datenpunkt erhalten.

### 4.4 Die Indexseite lügt über die Aktualität, die Datei sagt die Wahrheit

`branchen_d.htm` behauptet im Fliesstext «Letzte Aktualisierung: 07.11.2023». Die
verlinkten PDFs tragen `Version: 2.01.00 / 09.01.2026` und `Last-Modified: 2026-01-09`.
Die Seite ist über zwei Jahre veraltet, die Daten sind es nicht.

**Folge für `source_freshness`:** niemals aus HTML-Fliesstext ableiten. Primärquelle ist
der Versionsstring auf Seite 1 des Branchen-PDF bzw. das `/ModDate` des Jahres-PDF,
sekundär der `Last-Modified`-Header.

### 4.5 Der eigene Index der Site hinkt eine Ausgabe hinterher

`jahr_d.htm` verlinkt am Probetag durchgehend auf `Ts25.pdf#page=...`, obwohl `Ts26.pdf`
seit dem 12. Juni 2026 online liegt und die Startseite die Ausgabe 2026 bewirbt.

**Folge:** Die aktuelle Ausgabe darf nicht durch Scrapen der Indexseite bestimmt werden.
Stattdessen `Ts{YY}.pdf` vom erwarteten Jahr abwärts proben — `Ts27` → 404, `Ts26` → 200
ist ein sauberes, billiges Verfahren, das das saubere 404-Verhalten der Site ausnutzt.

### 4.6 Das Tabellen-Layout ist zwischen Ausgaben identisch

Gegenprobe `Ts25.pdf` vs. `Ts26.pdf`: beide 70 Seiten, und **alle 18 Tabellen liegen auf
denselben Seiten** (`2.4` → S. 27/28, `5.1` → S. 62, usw.).

Das ist eine gute Nachricht, aber kein Freibrief: zwei Ausgaben sind eine schmale Basis
für eine Serie, die bis 2000 zurückreicht. Der Loader soll deshalb auf die Bildunterschrift
`Tabelle X.Y` ankern und die Seitenzahl nur als Startpunkt der Suche verwenden. Kosten
gering, Bruchrisiko deutlich kleiner.

### 4.7 «Unbekannt» ist eine echte Zeile

Siehe Abschnitt 2. Tabelle 2.4 führt neben den NOGA-Zeilen eine Kategorie «Unbekannt».
Sie gehört in die Ausgabe, sonst stimmt die Summe nicht mehr mit der Publikation überein.

---

## 5. Tool-Vorschlag

### 5.1 Tool-Budget

| Posten | Anzahl |
|---|---:|
| Ist-Bestand (`src/seco_labor_mcp/server.py`, gezählt) | **9** |
| … `seco_search_datasets`, `seco_get_dataset`, `seco_get_unemployment_overview`, `seco_get_youth_unemployment`, `seco_get_job_seekers`, `seco_get_open_positions`, `seco_get_monthly_report_url`, `seco_get_unemployment_by_occupation`, `seco_list_cantons` | |
| Neu vorgeschlagen | **3** |
| **Summe** | **12** |
| Portfolio-Limit | 15 |
| **Verbleibender Spielraum** | **3** |

Budget eingehalten. Die drei verbleibenden Plätze sind bewusst frei; Kandidaten für
später wären Quartalszahlen und Suva-Prämienklassen (beide in Abschnitt 8 zurückgestellt).

### 5.2 Namensgebung — offener Punkt

Der Bestand nutzt durchgängig das Präfix `seco_`. Die Arbeitshypothese der Aufgabe lautete
`labor_uvg_*`. Angeglichen an die Bestandeskonvention ergäbe das `seco_get_uvg_*`.

**Das ist inhaltlich nicht ganz sauber, und ich möchte es nicht stillschweigend
entscheiden:** Herausgeber der Unfallstatistik UVG sind KSUV und SSUV c/o Suva — **nicht
das SECO**. Ein Toolname `seco_get_uvg_overview` legt eine Urheberschaft nahe, die nicht
zutrifft.

| Option | Für | Gegen |
|---|---|---|
| **A** `seco_get_uvg_*` | konsistent mit allen 9 Bestandstools; `seco_` liest sich als Server-Namespace | suggeriert SECO als Quelle |
| **B** `uvg_get_*` | quellenehrlich | bricht die einheitliche Präfix-Konvention des Servers |

**Meine Empfehlung: Option A**, weil das Präfix in MCP faktisch den Server adressiert und
nicht die Datenquelle — **kombiniert mit zwei Korrektiven:** das `source`-Feld jedes
Envelopes nennt ausschliesslich KSUV/SSUV, und die Repo-Description wird von «(SECO/AMSTAT)»
auf «(SECO/AMSTAT, SSUV)» erweitert. Falls Du Option B bevorzugst, ist das ein Einzeiler
in Schritt 2 — sag einfach Bescheid.

### 5.3 Die drei Tools

Alle mit `readOnlyHint: true`, testbare `*_impl`-Funktion getrennt vom Tool-Wrapper.

#### `seco_get_uvg_overview`

Gesamtschweizerische Kennzahlen zu Berufsunfällen (BUV) und Berufskrankheiten.
Quelle: Schlüsselzahlen-HTML (primär) mit Jahresausgabe-PDF als Rückfallebene.

```python
class UvgOverviewInput(BaseModel):
    years: int = Field(default=5, ge=1, le=5,
                       description="Anzahl Jahre rückwärts ab dem jüngsten publizierten Jahrgang.")
    include_nbuv: bool = Field(default=False,
                               description="Nichtberufsunfälle (Freizeit) mit ausweisen. "
                                           "Standard ist False: der Server deckt Arbeitsmarkt ab, "
                                           "Freizeitunfälle sind Kontext, nicht Gegenstand.")

async def seco_get_uvg_overview_impl(params: UvgOverviewInput) -> UvgOverviewResponse: ...
```

#### `seco_get_uvg_by_branch`

Unfallrisiko und anerkannte Fälle je Wirtschaftszweig (NOGA 2008).
Quelle: `Ts{YY}.pdf`, Tabellen 1.2 und 2.4.

```python
class UvgBranchInput(BaseModel):
    noga: str | None = Field(default=None,
        description="NOGA-2008-Code, wie im Publikationsraster: zweistellig ('43') oder "
                    "als Bereich ('41 – 42'). Weglassen liefert ALLE Zeilen inklusive der "
                    "Sektor-Summen und der Kategorie 'Unbekannt' — es filtert nichts weg.")
    metric: Literal["risk", "cases", "occupational_disease", "all"] = "all"
```

Die Beschreibung des Weglassens ist bewusst explizit ausformuliert — nach Skill 1.2b ist
«optional heisst unbeschränkt» die teuerste stille Fehlannahme, und hier heisst Weglassen
tatsächlich «alles».

#### `seco_get_uvg_trends`

Zehnjahres-Zeitreihe der Erfolgskennzahlen je Branche, inklusive
Signifikanz-Markierung und UVG-Gesamtvergleichslinie.
Quelle: `WirtKl_{BUV|NBUV}_{NOGA}.pdf`.

```python
class UvgTrendInput(BaseModel):
    noga: str = Field(description="Zweistelliger NOGA-2008-Code, z. B. '43' (Ausbaugewerbe), "
                                  "'86' (Gesundheitswesen), '85' (Erziehung und Unterricht).")
    branch_type: Literal["BUV", "NBUV"] = Field(default="BUV",
        description="BUV = Berufsunfallversicherung, NBUV = Nichtberufsunfallversicherung.")
    indicator: str | None = Field(default=None,
        description="Kennzahl, z. B. 'Fallrisiko' oder 'Berufskrankheiten BK / 100'000 VB'. "
                    "Weglassen liefert alle 12 Kennzahlen der Zeitreihe.")
```

### 5.4 Beispiel-Envelope

```jsonc
{
  "source": "Unfallstatistik UVG (UVG-Statistik 2026), Hrsg. Koordinationsgruppe für die "
            "Statistik der Unfallversicherung KSUV, Sammelstelle SSUV c/o Suva, Luzern. "
            "Abdruck ausser für kommerzielle Nutzung mit Quellenangabe gestattet.",
  "provenance": "annual_pdf",          // annual_pdf | branch_pdf | key_figures_html | cached
  "retrieved_at": "2026-08-05T09:14:22Z",
  "source_freshness": {
    "edition": "UVG-Statistik 2026",
    "data_year": 2024,                 // jüngstes vollständiges Datenjahr, NICHT Ausgabejahr
    "published": "2026-06-09",         // PDF /CreationDate
    "last_modified": "2026-06-12T08:25:04Z",
    "lag_note": "Ausgabe 2026 weist 2024 als jüngstes vollständiges Branchenjahr aus."
  },
  "noga": "43",
  "label": "Vorbereitende Baustellenarbeiten, Bauinstallation und sonstiges Ausbaugewerbe",
  "series": [
    { "year": 2023, "case_risk_per_1000": 153, "significant": false },
    { "year": 2024, "case_risk_per_1000": 145, "significant": true }
  ],
  "totals_check": { "sum_rows": 261446, "printed_total": 261446, "match": true },
  "degraded": false
}
```

`totals_check` ist die Invariante aus Abschnitt 2, in die Response gehoben: Der Loader
rechnet bei jedem Parse gegen das gedruckte Total und meldet eine Abweichung, statt sie zu
verschweigen. Sie wird zusätzlich als `@pytest.mark.live`-Canary festgeschrieben.

Bei Quellenausfall nach 2s/4s/8s:

```jsonc
{
  "degraded": true,
  "provenance": "cached",
  "source_freshness": { "edition": "UVG-Statistik 2026", "cached_at": "2026-08-04T06:00:00Z" },
  "note": "unfallstatistik.ch war nach drei Versuchen nicht erreichbar. Ausgewiesen sind "
          "Werte aus dem lokalen Cache vom 2026-08-04. Erneut versuchen in einigen Minuten."
}
```

---

## 6. Was ich vor Schritt 2 von Dir brauche

Zwei Punkte, die ich bewusst nicht selbst entschieden habe.

### 6.1 Lizenz — der einzige echte Blocker

> «Abdruck – ausser für kommerzielle Nutzung – mit Quellenangabe gestattet.»
> — `Ts26.pdf`, Impressum

Das ist **keine offene Lizenz**. Kein CC BY, kein CC BY-SA, kein OGD-CH. Es ist eine
Erlaubnis mit einer **Nicht-kommerziell-Klausel** — restriktiver als alles andere im
Portfolio.

Konkret bedeutet das:

- Die Quellenangabe ist erfüllbar und ohnehin Portfolio-Standard: `source` in jedem Envelope.
- Die NC-Klausel ist das Problem. Ein MCP-Server auf PyPI unter MIT gibt seinen Nutzern
  Rechte, die für die **Daten** so nicht gelten. Der Code darf MIT sein, die durch ihn
  gelieferten Zahlen nicht ohne Weiteres kommerziell verwertet werden.
- Ein Nutzer, der den Server in einem kommerziellen Produkt einsetzt, verletzt
  möglicherweise die Nutzungsbedingungen der SSUV — ohne dass ihm das auffällt.

Ich halte das für lösbar, aber nicht für ignorierbar. Drei gangbare Wege:

| Weg | Beschreibung | Aufwand |
|---|---|---|
| **1** (empfohlen) | Bauen, mit expliziter NC-Warnung in `source` **jedes** Envelopes, in beiden READMEs und im Tool-Docstring. Parallel eine formlose Anfrage an `unfallstatistik@suva.ch` zur Klarstellung. | gering |
| **2** | Bauen, aber erst nach schriftlicher Rückmeldung der SSUV freigeben. | Wartezeit unbestimmt |
| **3** | Verwerfen und stattdessen nur auf die Publikationen **verlinken**, statt Zahlen auszuliefern (analog `seco_get_monthly_report_url`). | sehr gering, aber geringer Nutzen |

Ich empfehle **Weg 1**. Er liefert den Nutzen sofort, macht die Einschränkung an der
einzigen Stelle sichtbar, die das Modell tatsächlich zu sehen bekommt, und die Anfrage
läuft nebenher. Sag mir bitte, ob Du das mitträgst — oder Weg 2 bevorzugst.

### 6.2 Namensgebung

Siehe 5.2. Meine Empfehlung ist Option A (`seco_get_uvg_*`) plus Anpassung der
Repo-Description. Eine Zeile Rückmeldung genügt.

---

## 7. Geprüfte und verworfene Quellen

| Quelle | Probe | Befund | Verworfen, weil |
|---|---|---|---|
| **opendata.swiss (CKAN)** | `package_search` mit `UVG`, `SSUV`, `Unfallstatistik`, `Berufsunfall`, `Berufskrankheit`, `Suva`, `Unfallversicherung`; `rows=50`, Mozilla-UA | `count=0` für sechs von sieben Begriffen. Der einzige Treffer (`Unfallversicherung`, count=1) ist eine Personal- und Lohnstatistik des Kantons Zürich — thematisch unbeteiligt. | Die SSUV publiziert **nicht** auf opendata.swiss. Kein Datensatz vorhanden, nicht bloss schlecht auffindbar. Sauberer Negativbefund. |
| **BFS dam-api** | `assets?limit=1` mit `query=`, `q=`, `search=` je `Berufsunfall` | `total` bleibt bei **186 408** — identisch mit dem Aufruf **ohne** jeden Parameter. | Die API **ignoriert alle drei Filterparameter stillschweigend** und antwortet mit 200. Genau das Muster aus Skill 1.2b: sieht nach Suche aus, liefert den Gesamtkatalog. Ohne dokumentierte Filtersyntax unbrauchbar — und gefährlich, weil ein 200 mit vollem Katalog wie Erfolg aussieht. |
| **BFS PXWeb / STAT-TAB** | `pxweb.bfs.admin.ch/api/v1/de/...`, `bfs.admin.ch/asset/de/pxweb` | HTTP 400 bzw. 500 | Kein erreichbarer Einstiegspunkt unter den geprüften Pfaden. |
| **Fünfjahresbericht-Register** | `fuenfjb_index_d.htm` | 3.3 MB, 10 990 Links — **ausschliesslich** Sprungmarken (`#A`…`#Z`), null PDF- oder Datenlinks | Reines alphabetisches Stichwortregister ohne eigene Daten. |
| **CUG-Service** | `/d/cug/` | Closed User Group für KSUV/SSUV-Mitglieder | Zugangsbeschränkt. Nach Portfolio-Regel Phase 1 = No-Auth: nicht anfassen. Kein Mischen von Auth- und No-Auth-Pfaden. |
| **Suva-Prämienklassen** | `suva_klasse_d.htm`, 43 Klassen | Funktioniert technisch | Fachlich zurückgestellt: deckt nur den Suva-Versichertenbestand ab, nicht UVG-gesamt. Als vierte Datenachse neben NOGA würde es die Tools mehrdeutig machen. Kandidat für später. |
| **Quartalszahlen** | `quartal_d.htm`, Q1 2026 bis 2000 | Funktioniert technisch | Zurückgestellt: enthält nur Fallzahlen nach Versicherergruppe, **keine** Branchen- oder Berufskrankheitsgliederung. Deckt die Fragestellung nicht ab. |

---

## 8. Empfehlung

**Bauen — mit der Lizenz-Entscheidung aus 6.1 als Vorbedingung.**

Dafür spricht:

- Die Quelle liefert **exakt** das Gesuchte: Berufsunfälle und Berufskrankheiten,
  aggregiert und anonymisiert, nach NOGA-Wirtschaftszweig, mit 10-Jahres-Zeitreihen und
  ausgewiesener statistischer Signifikanz.
- Sie ist technisch bemerkenswert robust: deterministische URLs, 16 Jahre stabiles
  Archiv, `ETag`/`Last-Modified`, sauberes 404-Verhalten, kein Auth, kein Rate-Limit.
- Die Extraktion ist **verifiziert**, nicht angenommen: Die Summenprobe geht exakt auf.
- Portfolio-Synergie ist real und nicht konstruiert: `seco-labor-mcp` weist heute
  Arbeitslosigkeit und Stellensuche aus. Mit UVG kommt die Risikoseite desselben
  Arbeitsmarkts dazu — und die Schlüsselzahlen führen «Stellensuchende» als
  UVAL-Versichertenbestand sogar selbst, mit ausdrücklichem Verweis auf die
  SECO-Registrierung. Die beiden Quellen zeigen dieselbe Population aus zwei Richtungen.

Dagegen spricht — und das ist ehrlich zu benennen:

- **PDF-Parsing bleibt PDF-Parsing.** Layoutstabilität über zwei Ausgaben ist ein gutes
  Zeichen, keine Garantie. Der Loader braucht Caption-Anker und die Summenprobe als
  Selbstkontrolle, sonst liefert er beim nächsten Redesign still falsche Zahlen.
- **Der Datenstand hinkt zwei Jahre nach.** Zur Erwartungssteuerung gehört das
  prominent in `source_freshness` und in beide READMEs, nicht ins Kleingedruckte.
- **Die NC-Lizenz ist eine echte Einschränkung**, kein Formalismus.

Eine **Verwerfung wäre vertretbar**, wenn Dir die NC-Klausel für ein öffentlich auf PyPI
publiziertes Portfolio-Paket zu heikel ist. In dem Fall ist Weg 3 aus 6.1 die saubere
Rückfallposition: nur verlinken statt Zahlen ausliefern, ein einziges Tool
`seco_get_uvg_publication_url` analog zum bestehenden `seco_get_monthly_report_url`,
Aufwand ein Bruchteil. Der Nutzen wäre allerdings entsprechend klein.

---

## 9. Reproduzierbarkeit

Alle Befunde stammen aus Live-Abrufen vom **2026-08-05** mit browser-artigem
User-Agent. Geprüfte Artefakte: `Ts25.pdf` (2 524 864 B), `Ts26.pdf` (2 168 646 B),
`WirtKl_BUV_43.pdf` (220 304 B), `Beschrieb_Branchen_d.pdf` (209 928 B),
`schluesselzahlen_d.htm` (21 930 B). PDF-Textextraktion mit `pypdf`.

Ein Negativbefund ist ein Resultat: opendata.swiss (Abschnitt 7) und die BFS-dam-api sind
belastbar als **nicht nutzbar** dokumentiert, damit die Prüfung nicht beim nächsten
Portfolio-Server erneut anfällt.
