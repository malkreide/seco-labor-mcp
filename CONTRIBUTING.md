# Contributing to seco-labor-mcp

Thank you for your interest in contributing to the Swiss Public Data MCP Portfolio!

## Development Setup

```bash
git clone https://github.com/malkreide/seco-labor-mcp.git
cd seco-labor-mcp
pip install -e ".[dev]"
```

## Running Tests

```bash
# Unit tests (no internet required)
pytest tests/ -m "not live" -v

# Live API tests (requires internet)
pytest tests/ --run-live -v
```

## Code Style

- Python 3.11+
- Type hints required
- Pydantic v2 for all input models
- `ruff` for linting
- All tools must have comprehensive docstrings

## Adding a New Tool

1. Define a Pydantic input model with `ConfigDict(extra='forbid')`
2. Use `@mcp.tool(name="seco_*", annotations={...})` decorator
3. Include docstring with Args, Returns, and Schema sections
4. Add tests in `tests/test_server.py`
5. Update README tool table

## No-Auth-First Principle

Phase 1 tools must work without any API key. Authenticated sources go in Phase 2 with graceful degradation.
