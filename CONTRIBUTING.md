# Contributing to seco-labor-mcp

🌐 **English** | **[Deutsch](CONTRIBUTING.de.md)**

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
4. Add tests in `tests/test_unit.py`
5. Update the tool table in `README.md` and `README.de.md`

## No-Auth-First Principle

Phase 1 tools must work without any API key. Authenticated sources go in Phase 2 with graceful degradation.

## The live suite: when it runs, and who sees a red result

**Cadence:** daily at 03:17 UTC, plus on demand via *Actions → Live tests (nightly) → Run
workflow*. See [`.github/workflows/live.yml`](.github/workflows/live.yml).

**Who sees it:** A red run opens an issue labelled `upstream` and the stable title “Live-Tests gegen unfallstatistik.ch rot (<Datum>)”. A second red run recognises the open issue by its title prefix and appends to that same thread rather than opening a second one. Once the suite is green again, the issue closes itself.

**Three answers, not two.** `scripts/classify_live_run.py` reads the JUnit XML rather than
the exit code and separates `clear` (ran, green), `finding` (ran, something
fell) and `unknown` (did not run — install failed, nothing collected,
everything skipped). An `unknown` never closes an issue: closing would claim a
comparison that never happened.

**A red live run does not necessarily mean *our* bug.** It means the contract
with the source has changed, or the source is down. Both belong seen; only the
first belongs fixed. Please read the run before disabling the job — that is how
this check dies, and it is the only one in the repository that can contradict a
wrong assumption about unfallstatistik.ch. Every other test asserts against a fixture, and
the fixture was written from the same assumption as the code.
