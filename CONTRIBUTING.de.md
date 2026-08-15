# Mitwirken an seco-labor-mcp

🌐 **[English](CONTRIBUTING.md)** | **Deutsch**

Vielen Dank für Ihr Interesse, zum Swiss Public Data MCP Portfolio beizutragen!

## Entwicklungsumgebung einrichten

```bash
git clone https://github.com/malkreide/seco-labor-mcp.git
cd seco-labor-mcp
pip install -e ".[dev]"
```

## Tests ausführen

```bash
# Unit-Tests (kein Internet erforderlich)
pytest tests/ -m "not live" -v

# Live-API-Tests (Internet erforderlich)
pytest tests/ --run-live -v
```

## Code-Stil

- Python 3.11+
- Type-Hints erforderlich
- Pydantic v2 für alle Eingabemodelle
- `ruff` für Linting
- Alle Tools benötigen umfassende Docstrings

## Ein neues Tool hinzufügen

1. Ein Pydantic-Eingabemodell mit `ConfigDict(extra='forbid')` definieren
2. Den Decorator `@mcp.tool(name="seco_*", annotations={...})` verwenden
3. Docstring mit Abschnitten Args, Returns und Schema ergänzen
4. Tests in `tests/test_unit.py` hinzufügen
5. Die Tool-Tabelle in `README.md` und `README.de.md` aktualisieren

## Grundsatz «No-Auth-First»

Phase-1-Tools müssen ohne jeden API-Schlüssel funktionieren. Authentifizierte
Quellen kommen in Phase 2 mit Graceful Degradation hinzu.

## Die Live-Suite: wann sie läuft, und wer ein rotes Ergebnis sieht

**Kadenz:** täglich um 03:17 UTC, dazu jederzeit von Hand über *Actions → Live tests (nightly) → Run
workflow*. Siehe [`.github/workflows/live.yml`](.github/workflows/live.yml).

**Wer es sieht:** Ein roter Lauf öffnet ein Issue mit dem Label `upstream` und dem stabilen Titel «Live-Tests gegen unfallstatistik.ch rot (<Datum>)». Ein zweiter roter Lauf erkennt das offene Issue am Titelanfang und hängt sich an denselben Thread, statt ein zweites aufzumachen. Wird die Suite wieder grün, schliesst sich das Issue selbst.

**Drei Antworten, nicht zwei.** `scripts/classify_live_run.py` liest das JUnit-XML statt des
Exit-Codes und unterscheidet: `clear` (gelaufen, grün), `finding` (gelaufen,
etwas gefallen) und `unknown` (nicht gelaufen — Installation gescheitert, null
Tests eingesammelt, alle übersprungen). Ein `unknown` schliesst nie ein Issue:
Zuzumachen hiesse zu behaupten, der Vergleich sei gelaufen.

**Ein roter Live-Lauf heisst nicht zwingend «unser Fehler».** Er heisst: Der
Vertrag mit der Quelle hat sich geändert, oder die Quelle ist gerade aus. Beides
gehört gesehen, nur das Erste gehört gefixt. Bitte den Lauf lesen, bevor der Job
deaktiviert wird — so stirbt dieser Check, und er ist der einzige im Repo, der
einer falschen Grundannahme über unfallstatistik.ch widersprechen kann. Jeder andere Test
prüft gegen eine Fixture, und die Fixture ist aus derselben Annahme geschrieben
wie der Code.

## Lizenz

Mit Ihrem Beitrag erklären Sie sich damit einverstanden, dass Ihre Beiträge unter
der [MIT-Lizenz](LICENSE) lizenziert werden.
