# Herkunft der Fixtures

**Erzeugt von `scripts/record_fixtures.py`. Nicht von Hand pflegen.**

Aufgezeichnet am **2026-08-15** von den Quellen dieses Servers:
`https://opendata.swiss/api/3/action`, `https://www.unfallstatistik.ch` und der CSV-Ressource des aufgezeichneten
Datensatzes.

Ohne Datum ist «aufgezeichnet» nach zwei Jahren von «ausgedacht» nicht
mehr zu unterscheiden — die Datei sieht gleich aus.

**Ein Teil sind Ausschnitte, keine Vollabzuege.** Die Auswahlregel steht
je Datei dabei. Gekuerzt ist immer die Zahl der Eintraege — Zeilen einer
CSV, Seiten eines PDF —, nie ihr Inhalt: keine Spalte entfernt, keine
Tabelle umgeschrieben. Eine Fixture belegt damit die *Form* der Antwort
und einen datierten Ausschnitt ihres Inhalts, nicht den Bestand.
Aussagen ueber Vollstaendigkeit gehoeren in `tests/test_live.py`.

**Die Eintraege sind gewaehlt, nicht genommen.** Die CSV beginnt mit
einer einzigen Gemeinde im aeltesten Jahr; aufgezeichnet sind zwei
vollstaendige Zeitreihen. Der Jahresbericht traegt seine drei Tabellen
auf den Seiten 13, 27 und 28 von 70 — der Recorder sucht sie an ihrer
Beschriftung, statt Seitenzahlen zu pinnen.

## Befund: der gepinnte Organisationsfilter trifft niemanden mehr

Der Client filtert jede CKAN-Suche auf `organization:staatssekretariat-fur-wirtschaft-seco`.
Diese Organisation gibt es auf opendata.swiss nicht (mehr):

| Abfrage | Treffer |
|---|---|
| `package_search` mit `fq=organization:staatssekretariat-fur-wirtschaft-seco` | **0** |
| dieselbe Suche ohne `fq` | 7810 |

`organization_show?id=staatssekretariat-fur-wirtschaft-seco` antwortet mit **404 Not found**, und in
den 176 Eintraegen von `organization_list` kommt kein SECO vor —
gesucht wurde auch nach den Schreibvarianten `…fuer…` und `seco`.
Datensaetze zum Thema gibt es, aber unter anderen Herausgebern (BFS,
kantonale Statistikaemter, Amt fuer Statistik FL).

Wirkung: **alle sechs CKAN-gestuetzten Tools liefern nichts.**
`seco_search_datasets` antwortet «Keine SECO-Datensaetze gefunden» und
empfiehlt andere Suchbegriffe — die aus demselben Grund auch nichts
finden. Die fuenf Tools mit CSV-Vorschau bekommen nie einen Datensatz,
durch den sie laufen koennten, und fallen still auf ihren statischen
Text zurueck.

Nicht in diesem Zug behoben: den Filter einfach zu streichen waere
keine Reparatur, sondern eine andere Zusage. Die Antworten hiessen
weiter «SECO-Datensaetze», waeren aber Daten des BFS und der Kantone.
Welche Quelle an die Stelle tritt, ist eine Entscheidung ueber den
Server und keine Nebenwirkung einer Aufzeichnung.

Die beiden aufgezeichneten Suchen halten den Stand fest. Kommt die
Organisation zurueck, faellt `test_der_filter_trifft_niemanden` — dann
gehoert die Aufzeichnung erneuert und dieser Befund gestrichen.

Fehlerpfade — Timeouts, 5xx, ein kaputtes PDF — bleiben handgeschrieben.
Die lassen sich nicht auf Zuruf aufzeichnen.

## `ckan_package_search.json`

- **Quelle:** `https://ckan.opendata.swiss/api/3/action/package_search?q=arbeitslose+kantone&fq=organization%3Astaatssekretariat-fur-wirtschaft-seco&rows=10&sort=score+desc%2C+metadata_modified+desc`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** vollstaendig; der Aufruf des Clients Wort fuer Wort — Suche nach 'arbeitslose kantone', gefiltert auf `organization:staatssekretariat-fur-wirtschaft-seco`. Ergebnis: **0 Treffer** (siehe Befund oben)
- **Groesse:** 219 B
- **SHA-256:** `1108f2a30e029490c6a1553c4a1f6e3e9d714b647cd7e17be6c11c24f6279f1d`

## `ckan_package_search_ohne_organisation.json`

- **Quelle:** `https://ckan.opendata.swiss/api/3/action/package_search?q=arbeitslose+kantone&rows=10&sort=score+desc%2C+metadata_modified+desc`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** vollstaendig; dieselbe Suche ohne `fq`. Ergebnis: **7810 Treffer**. Belegt, dass der Endpunkt antwortet und der Filter die Ursache ist — nicht die Suche und nicht das Netz
- **Groesse:** 124625 B
- **SHA-256:** `e6a7c74e21114fdafc0d89c3b1bf57e106deb11c654b5c76ef9b6e1b6ebd2bc5`

## `ckan_package_show.json`

- **Quelle:** `https://ckan.opendata.swiss/api/3/action/package_show?id=arbeitslose-anz`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** vollstaendig; Datensatz 'arbeitslose-anz' — ein beliebiger Datensatz, an dem die Form einer `package_show`-Antwort belegt ist. Die gepinnte Jahresreihe steht eigens weiter unten
- **Groesse:** 7063 B
- **SHA-256:** `88c006f402a07863358c3eaec33c16e9375db54e40da45365742d95c01b2265d`

## `ckan_package_show_jahresreihe.json`

- **Quelle:** `https://ckan.opendata.swiss/api/3/action/package_show?id=13f60916-3df1-495a-9b30-4e9b1daea562`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** vollstaendig; die gepinnte Kennung aus `sources.py` (erwerbslose-gemass-ilo-registrierte-arbeitslose-und-registrierte-stellensuchende4)
- **Groesse:** 17116 B
- **SHA-256:** `fc2b5f03e8031c752316795ea2dfc8ecf7c2f676364621b27f143d61631853fc`

## `bfs_jahresreihe.xlsx`

- **Quelle:** `https://dam-api.bfs.admin.ch/hub/api/dam/assets/36346864/master`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** vollstaendig; Blatt T3.3.0.1 mit den drei Reihen ['erwerbslose_ilo', 'registrierte_arbeitslose', 'registrierte_stellensuchende'], Jahre 2000-2025. Ungekuerzt, weil die ganze Mappe 17 kB misst
- **Groesse:** 17600 B
- **SHA-256:** `619ef4aff31943c86d168b70ded23a64fe486e311b7440fb54079a29de02c77b`

## `uvg_schluesselzahlen.html`

- **Quelle:** `https://www.unfallstatistik.ch/d/neuza/schluesselzahlen_d.htm`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** vollstaendig; Schluesselzahlen
- **Groesse:** 21930 B
- **SHA-256:** `5fea0264f6c79bed8805847a6006ad9c0bcf46a5d06554d02ec90c455e138c50`

## `uvg_publikationen.html`

- **Quelle:** `https://www.unfallstatistik.ch/d/publik/unfstat/unfstat_d.htm`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** vollstaendig; Publikationsliste
- **Groesse:** 12705 B
- **SHA-256:** `7fc8b9f57ad201784b37b7fccaf3e03f275d735d547e832671a0333844cd7919`

## `uvg_jahresbericht_ts26.pdf`

- **Quelle:** `https://www.unfallstatistik.ch/d/publik/unfstat/pdf/Ts26.pdf`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** 3 von 70 Seiten, Inhalt unveraendert: Tabelle 1.2 auf S. 13, Tabelle 2.4/Berufsunfallversicherung auf S. 27, Tabelle 2.4/Nichtberufsunfallversicherung auf S. 28. Gekuerzt ist die Zahl der Seiten, nie ihr Text — der Parser liest Beschriftung, Zeilen und Spalten aus dem Layout
- **Groesse:** 66363 B (Quelle: 70 Seiten, 2168646 B)
- **SHA-256:** `ac0f653c6881fa65cddc491d5199c1a47155e5ea4e18169d7118abaaee2fbd50`

## `uvg_branche_buv_41.pdf`

- **Quelle:** `https://www.unfallstatistik.ch/d/neuza/WirtKl_d/WirtKl_BUV_41.pdf`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** vollstaendig; NOGA 41, BUV — klein genug, um ungekuerzt zu bleiben
- **Groesse:** 219236 B
- **SHA-256:** `3f9c50e4f940ae9bc3ccc29271fb10dd9861dda21c3d3eba3c30ddff103205a2`
