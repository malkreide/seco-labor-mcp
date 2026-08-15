"""Retry-Policy: Retry-After, Jitter und der Deckel.

Zusammen mit dem gehärteten Retry aus der mcp-data-source-probe-Vorlage
übernommen. Geprüft wird das Verhalten, nicht die Konstanten: ein
deterministischer Backoff und ein ungelesenes `Retry-After` sind genau das, was
eine Erhebung über elf Server am 3.8.2026 fand — und jeder davon sah in Ordnung
aus.

Beide HTTP-Pfade dieses Pakets (`server.py::_fetch_text_cached` und
`uvg.py::_fetch_bytes`) benutzen diese eine Policy. Vorher trug jeder seine
eigene Kopie derselben Leiter.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from seco_labor_mcp import retry_policy

# --- Retry policy: Retry-After, jitter, and the cap --------------------------
# Adopted together with the hardened retry from the mcp-data-source-probe
# reference template. These assert the behaviour, not the constants: a
# deterministic ladder and an unread `Retry-After` are what a sweep across
# eleven servers found on 2026-08-03, and every one of them looked fine.


def _retry_after_error(value: str) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.invalid/")
    return httpx.HTTPStatusError(
        "",
        request=request,
        response=httpx.Response(429, headers={"Retry-After": value}, request=request),
    )


def test_retry_after_reads_both_rfc9110_forms() -> None:
    def resp(status: int, headers: dict[str, str]) -> httpx.Response:
        request = httpx.Request("GET", "https://example.invalid/")
        return httpx.Response(status, headers=headers, request=request)

    assert retry_policy.parse_retry_after(resp(429, {"Retry-After": "120"})) == 120.0

    later = format_datetime(datetime.now(UTC) + timedelta(seconds=90))
    seconds = retry_policy.parse_retry_after(resp(503, {"Retry-After": later}))
    assert seconds is not None and 80 < seconds <= 90

    # A date in the past means "now", never a negative wait.
    past = "Wed, 21 Oct 2020 07:28:00 GMT"
    assert retry_policy.parse_retry_after(resp(503, {"Retry-After": past})) == 0.0

    # Unparseable falls back to the curve. It must not crash on the error path,
    # which is the one path already going badly.
    assert retry_policy.parse_retry_after(resp(429, {"Retry-After": "bald"})) is None
    assert retry_policy.parse_retry_after(resp(429, {})) is None

    # 500 does not carry a meaningful Retry-After.
    assert retry_policy.parse_retry_after(resp(500, {"Retry-After": "120"})) is None
    assert retry_policy.parse_retry_after(None) is None


def test_backoff_is_jittered() -> None:
    delays = {retry_policy.compute_delay(3, None) for _ in range(300)}
    # attempt 3 -> 2 * 2**2 = 8s, spread into [0.5x, 1.5x]
    assert len(delays) > 1, "a deterministic ladder synchronises every client"
    assert min(delays) >= 4.0
    assert max(delays) <= 12.0


def test_cap_binds_after_the_jitter() -> None:
    # Capping first and then multiplying by up to 1.5 would land at 30s, and
    # the constant would claim a ceiling it does not hold.
    deep = {retry_policy.compute_delay(9, None) for _ in range(200)}
    assert max(deep) <= retry_policy.RETRY_MAX_DELAY

    hinted = _retry_after_error("600")
    assert {retry_policy.compute_delay(1, hinted) for _ in range(100)} == {
        retry_policy.RETRY_MAX_DELAY
    }


def test_retry_after_jitter_is_one_sided() -> None:
    """The source said when. Later is polite; earlier ignores the value read."""
    delays = {retry_policy.compute_delay(1, _retry_after_error("4")) for _ in range(300)}
    assert min(delays) >= 4.0, "never earlier than the source asked for"
    assert max(delays) <= 5.0  # 4 * 1.25


# --- Die Naht, und warum sie nicht `asyncio.sleep` ist -----------------------


def test_beide_pfade_gehen_ueber_ihren_modul_alias() -> None:
    """Sonst patchen die Tests eine Naht, die der Code gar nicht benutzt.

    Ruft ein Modul `asyncio.sleep` direkt auf, bleibt jeder Patch am Alias
    wirkungslos und die Suite wartet die echte Leiter ab. Kein Test faellt
    dabei — sie wird nur um ein Vielfaches langsamer, und eine laengere
    Laufzeit ist kein Signal, das jemand liest. Diese Zusicherung macht daraus
    einen Fehlschlag.
    """
    import inspect

    from seco_labor_mcp import server, uvg

    for modul in (server, uvg):
        quelle = inspect.getsource(modul)
        assert "await _sleep(" in quelle, f"{modul.__name__} ruft den Modul-Alias nicht auf"
        assert "await asyncio.sleep(" not in quelle, f"{modul.__name__} umgeht den Alias"


def test_kein_test_patcht_die_wartezeit_am_fremden_modul() -> None:
    """Die andere Haelfte derselben Naht.

    Der Test oben bewacht die Module: sie sollen `_sleep` aufrufen. Diese
    Zusicherung bewacht die Tests: keiner darf am geteilten `asyncio`-Modul
    patchen. Ein Patch dort trifft den Retry nicht mehr und entschaerft
    stattdessen `asyncio.sleep` fuer jeden Importeur im Prozess.

    Gesucht wird der **Patch**, nicht das Wort: `asyncio.sleep` in einem
    Fliesstext ist eine Erklaerung, in einem `setattr` eine Entschaerfung. Ein
    Waechter, der beides gleich behandelt, verbietet das Erklaeren mit.
    """
    import re
    from pathlib import Path

    patch = re.compile(r"setattr\([^)]*asyncio[^)]*sleep", re.S)
    hier = Path(__file__)
    schuldig = {
        pfad.name: patch.search(pfad.read_text(encoding="utf-8")).group(0)
        for pfad in sorted(hier.parent.glob("test_*.py"))
        if pfad != hier and patch.search(pfad.read_text(encoding="utf-8"))
    }
    assert not schuldig, (
        f"patcht die Wartezeit am geteilten Modul statt am Alias: {schuldig}. "
        'Richtig ist `monkeypatch.setattr(<modul>, "_sleep", _instant)`.'
    )


async def test_der_uvg_retry_fragt_die_leiter_ab() -> None:
    """Die dritte Haelfte — und die, die hier gefehlt hat.

    Die beiden Zusicherungen oben haetten den letzten Ausfall **nicht**
    gefangen: `uvg.py` rief `asyncio.sleep` auf, aber die Fixture patchte
    `UVG_BACKOFF_SECONDS`. Eine Konstante, die seit dem Wechsel auf
    `retry_policy` nur noch die Anzahl der Versuche bestimmte — «Backoff auf
    null» stand im Docstring und traf nichts.

    Gegen diese Klasse hilft nur, den Alias mitschreiben zu lassen: er wird
    aufgerufen, mit welchen Werten, und wie oft. Bleibt die Liste leer, wartet
    der Retry woanders.
    """
    import httpx as _httpx
    import respx

    from seco_labor_mcp import uvg

    gefragt: list[float] = []

    async def _mitschreiben(sekunden: float) -> None:
        gefragt.append(sekunden)

    async def _erlauben(_url: str) -> None:
        return None

    url = "https://example.test/kaputt.pdf"
    uvg.uvg_cache_clear()
    with respx.mock:
        respx.get(url).mock(return_value=_httpx.Response(503))
        original_sleep, original_pruefung = uvg._sleep, None
        from seco_labor_mcp import server as _server

        original_pruefung = _server._validate_external_url
        uvg._sleep = _mitschreiben
        _server._validate_external_url = _erlauben
        try:
            with pytest.raises(uvg.UvgSourceUnavailableError):
                await uvg._fetch_bytes(url)
        finally:
            uvg._sleep = original_sleep
            _server._validate_external_url = original_pruefung
    uvg.uvg_cache_clear()

    assert gefragt, "der Retry hat den Alias nie gefragt — er wartet woanders"
    assert len(gefragt) == uvg.UVG_VERSUCHE - 1, (
        f"{len(gefragt)} Wartezeiten bei {uvg.UVG_VERSUCHE} Versuchen"
    )
    # Die Leiter 2/4/8 mit Jitter in [0.5x, 1.5x].
    for i, sekunden in enumerate(gefragt):
        basis = 2.0 * 2**i
        assert basis * 0.5 <= sekunden <= basis * 1.5, (
            f"Wartezeit {i + 1}: {sekunden:.2f}s liegt ausserhalb von "
            f"[{basis * 0.5}, {basis * 1.5}]"
        )
