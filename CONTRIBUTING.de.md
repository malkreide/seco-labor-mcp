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

## Lizenz

Mit Ihrem Beitrag erklären Sie sich damit einverstanden, dass Ihre Beiträge unter
der [MIT-Lizenz](LICENSE) lizenziert werden.
