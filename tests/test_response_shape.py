"""Die CKAN-Hülle wird bestätigt, nicht angenommen (FID-006).

Sechs Werkzeuge lasen die Trefferliste mit zwei Defaults hintereinander:

    datasets = search_result.get("result", {}).get("results", [])

Fällt `result` weg — weil opendata.swiss seine Antwort umbaut oder die Anfrage
nie richtig war —, war `datasets` leer, und die Werkzeuge antworteten «Keine
SECO-Datensätze für '<Suche>' gefunden» samt Vorschlägen für andere
Suchbegriffe. Für das Modell ist das nicht davon zu unterscheiden, dass es zu
dieser Anfrage wirklich nichts gibt — und der Vorschlag, es mit
«Arbeitslosigkeit» statt «Kurzarbeit» zu versuchen, macht den Ausfall noch
überzeugender.

Fünf der sechs Stellen sahen das `success`-Envelope dabei gar nicht erst an.

Der Portfolio-Durchlauf am 2026-08-07 fand acht Server, die mit CKAN sprechen;
alle acht prüfen das `success`-Envelope irgendwo, sieben defaulteten `result`
danach.
"""

import httpx
import pytest
import respx

from seco_labor_mcp.server import (
    CKAN_BASE,
    DatasetSearchInput,
    UpstreamSchemaError,
    _ckan_result,
    _ckan_results,
    _to_execution_error,
    seco_search_datasets,
)


def _mock(payload):
    return respx.get(f"{CKAN_BASE}/package_search").mock(
        return_value=httpx.Response(200, json=payload)
    )


# --- Die Helfer --------------------------------------------------------------


def test_a_missing_result_raises_instead_of_returning_nothing():
    with pytest.raises(UpstreamSchemaError):
        _ckan_results({"success": True, "help": "…"})


def test_the_message_names_the_keys_that_are_actually_there():
    """Ohne die vorhandenen Schlüssel ist der nächste Schritt Raten."""
    with pytest.raises(UpstreamSchemaError) as excinfo:
        _ckan_results({"success": True, "help": "…", "payload": {}})
    message = str(excinfo.value)
    assert "'help'" in message and "'payload'" in message, message
    assert "package_search" in message
    assert "keine Leermenge" in message


def test_a_result_without_results_is_rejected():
    """Die Ebene darunter zählt genauso.

    CKAN liefert `results` auch bei null Treffern. Fehlt es, ist das eine
    andere Antwort und keine leere Suche.
    """
    with pytest.raises(UpstreamSchemaError) as excinfo:
        _ckan_results({"result": {"count": 0}})
    assert "results" in str(excinfo.value)


def test_a_non_object_response_is_rejected():
    with pytest.raises(UpstreamSchemaError) as excinfo:
        _ckan_results(["unerwartet", "liste"])
    assert "list" in str(excinfo.value)


def test_an_empty_hit_list_is_still_a_normal_answer():
    """Ein Wächter, der die echte Leermenge mitfängt, wird abgeschaltet.

    Bestätigt wird die **Anwesenheit** von `results`, nicht sein Inhalt.
    """
    assert _ckan_results({"result": {"results": [], "count": 0}}) == []


def test_the_dataset_helper_confirms_the_root_too():
    """`package_show` liest denselben Wurzelpfad mit demselben Default."""
    assert _ckan_result({"result": {"title": "x"}}, "package_show") == {"title": "x"}
    with pytest.raises(UpstreamSchemaError):
        _ckan_result({"success": True}, "package_show")


# --- Wohin der Fehler geht ---------------------------------------------------


def test_a_schema_error_is_not_an_execution_error():
    """Die Einordnung ist die eigentliche Entscheidung.

    `_to_execution_error` gibt für Ausführungsfehler eine Zeichenkette an das
    Modell zurück, damit es etwas anderes versuchen kann. Bei einer
    Formänderung gibt es nichts anderes zu versuchen — ein anderer Suchbegriff
    hilft nicht. Der Typ ist `_to_execution_error` deshalb unbekannt und wird
    weitergereicht, sodass FastMCP daraus `isError: true` macht (OBS-001).
    """
    with pytest.raises(UpstreamSchemaError):
        _to_execution_error(UpstreamSchemaError("Antwort ohne `result`."))


# --- Am Werkzeug -------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_the_search_tool_reports_a_shape_change_instead_of_no_hits():
    """Die Zusage dort, wo der Nutzer sie merkt.

    Vorher: «Keine SECO-Datensätze für 'kurzarbeit' gefunden» plus vier
    Vorschläge — die exakt gleiche Antwort wie bei einer korrekten Suche ohne
    Treffer.
    """
    _mock({"success": True, "help": "https://opendata.swiss/api/3/"})
    with pytest.raises(UpstreamSchemaError):
        await seco_search_datasets(DatasetSearchInput(query="kurzarbeit"))


@pytest.mark.asyncio
@respx.mock
async def test_a_real_empty_search_still_suggests_other_terms():
    """Die Gegenrichtung, und sie ist die wichtigere Hälfte.

    `results: []` ist eine Aussage der Quelle. Genau diese Antwort muss
    weiterhin die freundliche Vorschlagsliste ergeben.
    """
    _mock({"success": True, "result": {"results": [], "count": 0}})
    out = await seco_search_datasets(DatasetSearchInput(query="gibtesnicht"))
    assert "Keine Datensätze" in out
    assert "Arbeitslosigkeit" in out


# --- Dass alle sechs Suchstellen umgestellt sind -----------------------------


def test_every_search_tool_goes_through_the_helper():
    """Keine Suchstelle liest die Trefferliste an der Bestätigung vorbei.

    Eine davon zu vergessen halbiert die Zusage still: die betroffenen
    Werkzeuge verschlucken ihren CKAN-Fehler ohnehin (`except Exception:
    datasets = []`) und würden auch nach dem Fix nicht von selbst rot.

    Gezählt wird deshalb nicht mehr eine feste Zahl von Fundstellen — die
    änderte sich mit jedem Umbau, zuletzt von sechs auf drei, ohne dass an der
    Regel etwas anders wäre. Geprüft wird die Regel selbst: **jedem
    `_ckan_search(` folgt in den nächsten Zeilen ein `_ckan_results(`.**
    """
    from pathlib import Path

    source = Path(__file__).parent.parent / "src" / "seco_labor_mcp" / "server.py"
    zeilen = source.read_text(encoding="utf-8").split("\n")
    aufrufe = [
        i
        for i, z in enumerate(zeilen)
        if "await _ckan_search(" in z and not z.lstrip().startswith("#")
    ]
    assert aufrufe, "keine einzige Suchstelle gefunden — Test ins Leere gelaufen"
    for i in aufrufe:
        umgebung = "\n".join(zeilen[i : i + 6])
        assert "_ckan_results(" in umgebung, (
            f"Suchstelle in Zeile {i + 1} liest die Trefferliste ohne "
            f"`_ckan_results()`:\n{umgebung}"
        )
    assert '.get("result", {}).get("results", [])' not in "\n".join(zeilen)
