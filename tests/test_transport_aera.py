"""Welche Protokoll-Aera ein Transport ueberhaupt tragen kann — und `main()`.

Zwei Dinge, die zusammengehoeren, weil das eine das andere begruendet.

**Der Transport entscheidet die Aera mit.** Die moderne Aera 2026-07-28 kennt
keinen `initialize`-Handshake; sie laeuft als in sich geschlossener POST. Der
SSE-Transport hat diese Form nicht, und deshalb einigt sich auch ein Client,
der die moderne Aera anbietet, dort auf 2025-11-25. Ein Server, der `sse` als
Default fuehrt, spricht die neue Spec also nicht — egal, welches SDK er pinnt.
Genau das ist der Grund, warum `main()` jetzt `http` dokumentiert.

Das steht hier als Messung und nicht als Notiz, weil es eine Aussage ueber das
SDK ist und nicht ueber unseren Code: Aendert eine kuenftige fastmcp-Version
das Verhalten, faellt dieser Test und nicht bloss ein Absatz in der README.

**`main()` selbst war unter FastMCP 4 kaputt**, und kein Test hat es gesehen.
Der alte SSE-Zweig setzte `mcp.settings.host` / `.port`; FastMCP 4 fuehrt kein
`settings`-Attribut mehr auf dem Server-Objekt. Der AttributeError waere beim
Start eines Netz-Deployments gekommen, nie in der CI. Die Tests unten rufen
`main()` deshalb wirklich auf, statt den Code zu lesen.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket

import pytest
from fastmcp import Client

# Ohne Paket-Praefix: `tests/` ist kein Paket, und `pytest tests/` (so faehrt
# es die CI) legt das Testverzeichnis selbst in den Suchpfad. `from
# tests.test_protokoll_aeren import ...` laeuft nur unter `python -m pytest`,
# das zusaetzlich das Arbeitsverzeichnis einhaengt — lokal gruen, in der CI rot.
# Dieselbe Schreibweise nutzt `test_recorded_fixtures.py` fuer `fixture_data`.
from test_protokoll_aeren import (
    DOKUMENTIERTE_HANDSHAKE_REVISION,
    DOKUMENTIERTE_MODERNE_REVISION,
)

from seco_labor_mcp import server as srv

# ---------------------------------------------------------------------------
# Teil 1: Was der Transport traegt (gemessen, ueber echtes HTTP)
# ---------------------------------------------------------------------------


async def _ausgehandelte_aera(transport: str, pfad: str) -> str:
    """Startet den Server auf einem vorgebundenen Socket und fragt die Aera ab.

    Der Socket wird *vor* dem Start auf Port 0 gebunden und an uvicorn
    weitergereicht. Ein `getsockname()`-und-dann-neu-binden haette ein
    Zeitfenster, in dem ein anderer Prozess denselben Port nimmt — auf einem
    CI-Runner mit parallelen Jobs ist das kein theoretischer Fall.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]

    server = asyncio.create_task(
        srv.mcp.run_async(transport=transport, sockets=[sock], show_banner=False)
    )
    try:
        # `mode="auto"` bietet die moderne Aera an und nimmt, was der Server
        # hergibt. Mit `mode="legacy"` waere das Ergebnis vorherbestimmt und
        # der Test wertlos.
        letzter: Exception | None = None
        for _ in range(50):
            if server.done():  # Startfehler nicht als Timeout tarnen
                server.result()
            try:
                async with Client(f"http://127.0.0.1:{port}{pfad}", mode="auto") as client:
                    return client.protocol_version
            except Exception as exc:  # Server noch nicht oben
                letzter = exc
                await asyncio.sleep(0.1)
        raise AssertionError(f"{transport} kam nicht hoch; zuletzt: {letzter!r}")
    finally:
        server.cancel()
        with contextlib.suppress(BaseException):
            await server
        sock.close()


async def test_http_traegt_die_moderne_aera() -> None:
    """Der Weg, den die READMEs fuehren — und der einzige, der 2026-07-28 kann."""
    aera = await asyncio.wait_for(_ausgehandelte_aera("http", "/mcp/"), timeout=60)
    assert aera == DOKUMENTIERTE_MODERNE_REVISION


async def test_sse_deckelt_auf_die_handshake_aera() -> None:
    """Die Gegenprobe, ohne die der Test darueber nichts zeigt.

    Liefe `sse` ebenfalls auf 2026-07-28, waere die Aera keine Eigenschaft des
    Transports und die Begruendung in `main()` falsch. Der Client bietet in
    beiden Faellen dasselbe an; verschieden ist nur der Transport.
    """
    aera = await asyncio.wait_for(_ausgehandelte_aera("sse", "/sse/"), timeout=60)
    assert aera == DOKUMENTIERTE_HANDSHAKE_REVISION


# ---------------------------------------------------------------------------
# Teil 2: Was `main()` daraus macht
# ---------------------------------------------------------------------------


@pytest.fixture
def aufrufe(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Faengt `mcp.run` ab, statt wirklich einen Server zu starten."""
    gesehen: list[dict] = []
    monkeypatch.setattr(srv.mcp, "run", lambda **kwargs: gesehen.append(kwargs))
    return gesehen


def test_ohne_variable_laeuft_stdio(monkeypatch: pytest.MonkeyPatch, aufrufe: list[dict]) -> None:
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    srv.main()
    assert aufrufe == [{"transport": "stdio"}]


def test_stdio_bekommt_weder_host_noch_port(
    monkeypatch: pytest.MonkeyPatch, aufrufe: list[dict]
) -> None:
    """Host und Port sind fuer stdio bedeutungslos und wuerden `run` sprengen."""
    monkeypatch.setenv("MCP_TRANSPORT", "stdio")
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "9999")
    srv.main()
    assert aufrufe == [{"transport": "stdio"}]


@pytest.mark.parametrize("transport", ["http", "streamable-http", "sse"])
def test_netz_transporte_binden_per_default_auf_loopback(
    transport: str, monkeypatch: pytest.MonkeyPatch, aufrufe: list[dict]
) -> None:
    """SEC-016. Ein Default von `0.0.0.0` waere NeighborJack im selben Netz."""
    monkeypatch.setenv("MCP_TRANSPORT", transport)
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    srv.main()
    assert aufrufe == [{"transport": transport, "host": "127.0.0.1", "port": 8000}]


def test_host_und_port_kommen_aus_der_umgebung(
    monkeypatch: pytest.MonkeyPatch, aufrufe: list[dict]
) -> None:
    """Der Zweig, der unter FastMCP 4 mit AttributeError starb.

    Frueher liefen Host und Port ueber `mcp.settings`; das Attribut gibt es
    nicht mehr. Dass die Werte ueberhaupt ankommen, ist deshalb keine
    Nebensache — es ist die Zusicherung, die den Ausfall beim naechsten Mal
    in der CI zeigt statt im Container.
    """
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "8080")
    srv.main()
    assert aufrufe == [{"transport": "http", "host": "0.0.0.0", "port": 8080}]


def test_mcp_settings_gibt_es_nicht_mehr() -> None:
    """Warum der Umbau noetig war — an das SDK gebunden, nicht an den Absatz.

    Kehrt `settings` eines Tages zurueck, faellt dieser Test und jemand liest
    nach, ob die Begruendung oben noch stimmt.
    """
    assert not hasattr(srv.mcp, "settings")


def test_ein_unbekannter_transport_faellt_auf(
    monkeypatch: pytest.MonkeyPatch, aufrufe: list[dict]
) -> None:
    """Frueher fiel jeder unbekannte Wert stumm auf stdio zurueck.

    `MCP_TRANSPORT=htttp` startete dann einen stdio-Server, der auf dem
    erwarteten Port nie erschien. Das ist dieselbe Klasse wie eine leere
    Trefferliste, die wie eine echte Leermenge aussieht: ein Ausfall, der sich
    als normaler Betrieb tarnt.
    """
    monkeypatch.setenv("MCP_TRANSPORT", "htttp")
    with pytest.raises(SystemExit) as exc:
        srv.main()
    assert "htttp" in str(exc.value)
    assert aufrufe == [], "unbekannter Transport darf keinen Server starten"
