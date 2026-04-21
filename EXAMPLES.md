# Use Cases & Examples — seco-labor-mcp

Real-world queries by audience. Indicate per example whether an API key is required.

### 🏫 Bildung & Schule
Lehrpersonen, Schulbehörden, Fachreferent:innen

**Regionale Jugendarbeitslosigkeit analysieren**
«Wie hat sich die Jugendarbeitslosigkeit im Kanton Zürich im Vergleich zum Vormonat entwickelt?»
→ `seco_get_youth_unemployment(canton="ZH")`
Warum nützlich: Hilft der Schulbehörde und der Berufsberatung, den aktuellen Druck auf dem Lehrstellenmarkt im eigenen Kanton frühzeitig zu erkennen.

**Offene Stellen in bestimmten Berufen prüfen**
«Welche Lehrberufe unterliegen aktuell der Stellenmeldepflicht, weil die Arbeitslosenquote über 5% liegt?»
→ `seco_search_datasets(query="Stellenmeldepflicht")`
→ `seco_get_dataset(dataset_id="stellenmeldepflicht-berufe")`
Warum nützlich: Ermöglicht Fachlehrpersonen, Schülerinnen und Schüler auf Berufe mit Inländervorrang und damit besseren Einstellungschancen hinzuweisen.

### 👨‍👩‍👧 Eltern & Schulgemeinde
Elternräte, interessierte Erziehungsberechtigte

**Chancen auf dem Arbeitsmarkt verstehen**
«Gibt es im Moment viele offene Stellen in der Informatik, oder ist der Markt dort gesättigt?»
→ `seco_get_open_positions(response_format="markdown")`
Warum nützlich: Gibt Eltern eine faktenbasierte Grundlage, um mit ihren Kindern realistische Karriereaussichten bei der Berufswahl zu besprechen.

**Regionale Arbeitsmarktlage einschätzen**
«Wie steht unser Kanton im nationalen Vergleich bei der Arbeitslosigkeit da?»
→ `seco_get_unemployment_overview(canton="ZH")`
Warum nützlich: Erlaubt interessierten Eltern, die wirtschaftliche Lage in ihrer Wohnregion besser einzuordnen.

### 🗳️ Bevölkerung & öffentliches Interesse
Allgemeine Öffentlichkeit, politisch und gesellschaftlich Interessierte

**Aktuelle Arbeitsmarktzahlen abrufen**
«Wie hoch ist die aktuelle Arbeitslosenquote in der Schweiz, und wie viele Personen sind als stellensuchend gemeldet?»
→ `seco_get_unemployment_overview()`
→ `seco_get_job_seekers()`
Warum nützlich: Fördert die Transparenz und ermöglicht Bürgerinnen und Bürgern, sich auf Basis offizieller SECO-Zahlen eine eigene Meinung zur Wirtschaftslage zu bilden.

**Offizielle Berichte lesen**
«Wo finde ich den neuesten SECO-Monatsbericht zur Arbeitsmarktlage als PDF?»
→ `seco_get_monthly_report_url(year=2026, month=2, language="de")`
Warum nützlich: Schafft direkten Zugang zu den originalen Pressedokumenten des Bundes für eine vertiefte politische Meinungsbildung.

### 🤖 KI-Interessierte & Entwickler:innen
MCP-Enthusiast:innen, Forscher:innen, Prompt Engineers, öffentliche Verwaltung

**Automatisierter Arbeitsmarkt-Report**
«Erstelle eine Zusammenfassung der nationalen Arbeitslosenzahlen und vergleiche sie mit den aktuellen Jobangeboten.»
→ `seco_get_unemployment_overview(response_format="json")`
→ `seco_get_open_positions(response_format="json")`
Warum nützlich: Demonstriert, wie LLMs strukturierte Json-Daten nutzen können, um automatisiert wirtschaftliche Dashboards oder Berichte zu generieren.

**Kontextualisierte Wirtschaftsanalyse (Multi-Server)**
«Wie korreliert die Arbeitslosigkeit im Kanton Zürich mit den dortigen Bildungsabschlüssen und den nationalen Wirtschaftsdaten?»
→ `seco_get_unemployment_overview(canton="ZH")`
→ `zurich_get_education_stats(...)` *(via [zurich-opendata-mcp](https://github.com/malkreide/zurich-opendata-mcp))*
→ `snb_get_gdp_growth(...)` *(via [swiss-snb-mcp](https://github.com/malkreide/swiss-snb-mcp))*
Warum nützlich: Zeigt die Stärke des Portfolios, indem Arbeitsmarktdaten des SECO mit lokalen Bildungsdaten der Stadt Zürich und makroökonomischen Zahlen der SNB kombiniert werden.

---

### 🔧 Technische Referenz: Tool-Auswahl nach Anwendungsfall

| Ich möchte… | Tool(s) | Auth nötig? |
|-------------|---------|-------------|
| **SECO-Datensätze nach Themen durchsuchen** | `seco_search_datasets` | Nein |
| **Download-Links für einen Datensatz erhalten** | `seco_get_dataset` | Nein |
| **Die allgemeine Arbeitslosenquote abrufen** | `seco_get_unemployment_overview` | Nein |
| **Daten zur Jugendarbeitslosigkeit einsehen** | `seco_get_youth_unemployment` | Nein |
| **Zahlen zu Stellensuchenden analysieren** | `seco_get_job_seekers` | Nein |
| **Informationen zu offenen Stellen finden** | `seco_get_open_positions` | Nein |
| **Arbeitslosigkeit nach Berufen aufschlüsseln** | `seco_get_unemployment_by_occupation` | Nein |
| **Den offiziellen Monatsbericht herunterladen** | `seco_get_monthly_report_url` | Nein |
