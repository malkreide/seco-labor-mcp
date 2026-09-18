"""Die beiden MCP-Protokoll-Aeren, die dieser Server bedient.

Bis 0.4.0 stand hier eine einzige Revision, und das war unter fastmcp 3.x auch
richtig: jene Linie pinnt `mcp` 1.x, dort ist `LATEST_PROTOCOL_VERSION` die
ganze Geschichte und 2025-11-25 die hoechste Revision, die das SDK ueberhaupt
kennt. Die Spec 2026-07-28 war damit nicht halb unterstuetzt, sondern gar
nicht.

Seit dem Upgrade auf fastmcp 4.x / `mcp` 2.x bedient derselbe Server zwei
Aeren:

  - **Handshake-Aera** (bis 2025-11-25): `initialize`, danach eine Sitzung mit
    Zustand. Das ist, was heutige Clients ueberwiegend sprechen.
  - **Moderne Aera** (2026-07-28): kein `initialize` mehr, sondern
    `server/discover` und pro Anfrage ein eigener Umschlag.

Beide werden hier einzeln gepinnt. Nur gegen `LATEST_PROTOCOL_VERSION` zu
pinnen waere die Falle, vor der die Vorgaengerfassung dieses Moduls gewarnt
hat: die Konstante ist in `mcp` 2.x ein Alias auf die *moderne* Aera. Wer nur
sie prueft, laesst eine Aenderung der Handshake-Obergrenze durch -- und die
betrifft praktisch jeden Client.

Gemessen statt geschlossen: `test_beide_aeren_werden_wirklich_ausgehandelt`
verhandelt gegen genau dieses `mcp`-Objekt, statt zwei Konstanten miteinander
zu vergleichen.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from fastmcp import Client
from mcp.types import LATEST_PROTOCOL_VERSION

from seco_labor_mcp.server import mcp

# Die beiden Revisionen, gegen die dieser Server gebaut und geprueft ist. Sie
# stehen hier und in beiden READMEs; die Tests unten halten alle drei Orte
# gegeneinander, damit die Doku nicht davonlaeuft.
DOKUMENTIERTE_HANDSHAKE_REVISION = "2025-11-25"
DOKUMENTIERTE_MODERNE_REVISION = "2026-07-28"

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_das_sdk_fuehrt_ueberhaupt_zwei_aeren() -> None:
    """Der Gegentest zur frueheren Ein-Aera-Wache.

    Bis 0.4.0 stand hier das Spiegelbild: ein Test, der fiel, sobald das SDK
    die Zwei-Aeren-Konstanten hereinzog. Genau das ist eingetreten. Jetzt
    faellt der Test in die andere Richtung -- naemlich dann, wenn ein
    Downgrade auf `mcp` 1.x die moderne Aera wieder entfernt. Ohne ihn waere
    ein solcher Rueckfall still: `LATEST_PROTOCOL_VERSION` gibt es in beiden
    Majors, nur bedeutet er dort Verschiedenes.
    """
    try:
        import mcp.types.version as sdk_version
    except ModuleNotFoundError:  # pragma: no cover - waere `mcp` 1.x
        pytest.fail(
            "`mcp.types.version` fehlt. Das ist `mcp` 1.x — vermutlich hat ein "
            "Downgrade fastmcp 3.x hereingezogen, und der Server spricht "
            "2026-07-28 nicht mehr, auch nicht halb."
        )

    # Kein `skipif`, kein `importorskip`: ein uebersprungener Test ist gruen,
    # und gruen ist hier genau die falsche Antwort auf ein fehlendes SDK.
    for name in ("LATEST_HANDSHAKE_VERSION", "LATEST_MODERN_VERSION"):
        assert hasattr(sdk_version, name), f"{name} fehlt im SDK"


def test_die_dokumentierten_revisionen_sind_die_des_sdk() -> None:
    """Gegen die SDK-Konstanten gehalten, nicht gegen abgeschriebenen Spec-Text.

    Hebt ein Bump eine der beiden an, faellt genau diese Zeile — und zwar
    bevor es jemandem an einem Client auffaellt.
    """
    from mcp.types.version import LATEST_HANDSHAKE_VERSION, LATEST_MODERN_VERSION

    assert LATEST_HANDSHAKE_VERSION == DOKUMENTIERTE_HANDSHAKE_REVISION, (
        f"Handshake-Obergrenze des SDK ist {LATEST_HANDSHAKE_VERSION}, "
        f"dokumentiert ist {DOKUMENTIERTE_HANDSHAKE_REVISION}."
    )
    assert LATEST_MODERN_VERSION == DOKUMENTIERTE_MODERNE_REVISION, (
        f"Moderne Revision des SDK ist {LATEST_MODERN_VERSION}, dokumentiert "
        f"ist {DOKUMENTIERTE_MODERNE_REVISION}."
    )


def test_latest_protocol_version_zeigt_auf_die_moderne_aera() -> None:
    """Warum der Pin oben ein Paar ist und kein einzelner Wert.

    `LATEST_PROTOCOL_VERSION` ist in `mcp` 2.x ein Alias auf die moderne Aera.
    Ein Server, der nur gegen ihn pinnt, sichert die Aera, die die wenigsten
    Clients sprechen, und laesst die Handshake-Obergrenze frei wandern. Faellt
    diese Zusicherung, hat das SDK die Bedeutung des Alias geaendert und der
    Absatz im Modulkopf stimmt nicht mehr.
    """
    assert LATEST_PROTOCOL_VERSION == DOKUMENTIERTE_MODERNE_REVISION


def test_nur_eine_moderne_revision_ist_bekannt() -> None:
    """Eine zweite moderne Revision waere eine Entscheidung, kein Bump.

    Solange `MODERN_PROTOCOL_VERSIONS` genau einen Eintrag hat, ist «die
    moderne Aera» eindeutig. Kommt eine dazu, muss jemand entscheiden, welche
    dieser Server dokumentiert — dieser Test erzwingt, dass das jemand tut,
    statt dass der Alias es stillschweigend tut.
    """
    from mcp.types.version import MODERN_PROTOCOL_VERSIONS

    assert MODERN_PROTOCOL_VERSIONS == (DOKUMENTIERTE_MODERNE_REVISION,), (
        f"Das SDK kennt jetzt die modernen Revisionen {MODERN_PROTOCOL_VERSIONS}. "
        "Welche dieser Server dokumentiert, ist eine Entscheidung."
    )


@pytest.mark.parametrize(
    ("modus", "erwartet"),
    [
        ("auto", DOKUMENTIERTE_MODERNE_REVISION),
        ("legacy", DOKUMENTIERTE_HANDSHAKE_REVISION),
    ],
)
async def test_beide_aeren_werden_wirklich_ausgehandelt(modus: str, erwartet: str) -> None:
    """Gemessen statt aus den Konstanten geschlossen.

    Die Zusicherungen darueber vergleichen Konstanten miteinander; sie sagen
    nichts darueber, was der Server am Draht aushandelt. Erst eine echte
    Verbindung gegen genau dieses `mcp`-Objekt tut das.

    `mode="auto"` nimmt, was der Server anbietet — hier also die moderne Aera.
    `mode="legacy"` erzwingt den `initialize`-Handshake und zeigt, dass die
    alte Aera weiter bedient wird. Ein Server, der nur eine der beiden koennte,
    faellt in genau einem der beiden Faelle.
    """
    async with Client(mcp, mode=modus) as client:
        assert client.protocol_version == erwartet


async def test_die_moderne_aera_hat_kein_initialize_ergebnis() -> None:
    """Der Formunterschied, an dem die Migration zuerst auffiel.

    Unter der modernen Aera gibt es keinen `initialize`-Handshake, also auch
    kein `InitializeResult` — `client.initialize_result` ist `None`. Die
    Vorgaengerfassung dieses Tests las genau dort die Revision ab und starb am
    Upgrade mit einem AttributeError auf `None`.

    Das ist keine Fussnote: Wer Servermetadaten ueber `initialize_result`
    liest, verliert sie an dem Tag, an dem ein Client die moderne Aera waehlt.
    Aera-neutral ist `protocol_version` / `server_info`.
    """
    async with Client(mcp, mode="auto") as client:
        assert client.initialize_result is None
        assert client.server_info is not None
        assert client.server_info.name == "seco_labor_mcp"

    async with Client(mcp, mode="legacy") as client:
        assert client.initialize_result is not None
        # `.protocol_version`, nicht `.protocolVersion`: `mcp` 2.x hat das Feld
        # umbenannt und laesst den alten Namen nur noch mit einer
        # Deprecation-Warnung durch.
        assert client.initialize_result.protocol_version == DOKUMENTIERTE_HANDSHAKE_REVISION


async def test_dieselben_werkzeuge_in_beiden_aeren() -> None:
    """Eine Aera, die weniger kann, waere eine halbe Migration.

    Ohne diese Zusicherung koennte der Server die moderne Aera formal
    aushandeln und darin nichts anbieten — die Revision am Draht waere richtig
    und der Server trotzdem kaputt.
    """
    async with Client(mcp, mode="auto") as client:
        modern = {t.name for t in await client.list_tools()}
    async with Client(mcp, mode="legacy") as client:
        handshake = {t.name for t in await client.list_tools()}

    assert modern == handshake, f"nur in einer Aera: {modern ^ handshake}"
    assert len(modern) == 12, f"12 Werkzeuge erwartet, gefunden {len(modern)}"


@pytest.mark.parametrize("datei", ["README.md", "README.de.md"])
def test_beide_readmes_nennen_beide_revisionen(datei: str) -> None:
    """Eine Doku, die weniger oder anderes sagt als der Server tut, ist die
    teurere Haelfte des Problems: sie sieht geprueft aus.

    Beide Sprachen einzeln parametrisiert. Nur die englische zu pruefen waere
    genau die Luecke, an der die zwei schon anderswo im Portfolio
    auseinandergelaufen sind — eine README wandert, die andere bleibt stehen,
    und niemand merkt es, weil der Test die stehengebliebene nie ansieht.
    """
    text = (_ROOT / datei).read_text(encoding="utf-8")
    revisionen = set(re.findall(r"`(20\d\d-\d\d-\d\d)`", text))
    fehlend = {DOKUMENTIERTE_HANDSHAKE_REVISION, DOKUMENTIERTE_MODERNE_REVISION} - revisionen
    assert not fehlend, f"{datei} nennt {sorted(revisionen)}, es fehlen {sorted(fehlend)}"
