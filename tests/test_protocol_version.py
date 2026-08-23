"""Die MCP-Protokollrevision, die dieser Server tatsaechlich aushandelt.

Bisher stand dazu nirgends etwas — weder eine Konstante im Code noch ein Satz
in der README noch ein Test. Ein SDK-Bump, der die Revision aendert, waere
lautlos durchgelaufen: alles gruen, andere Revision am Draht.

**Warum hier nur eine Revision steht und nicht zwei.** Die Schwester-Server im
Portfolio pinnen ein Paar — eine Handshake-Obergrenze und eine moderne
Revision —, weil `mcp` 2.x zwei Protokoll-Aeren ueber denselben Server bedient.
Dieser Server fährt fastmcp 3.x, und das pinnt `mcp` 1.x: dort gibt es
`mcp.types.version` gar nicht, `LATEST_PROTOCOL_VERSION` ist die ganze
Geschichte. Ein Zwei-Aeren-Pin waere hier keine Vorsicht, sondern eine
Behauptung ueber ein SDK, das der Server nicht benutzt.

Damit das keine Notiz bleibt, die veraltet, ist
`test_das_sdk_kennt_hier_nur_eine_aera` an das SDK gebunden statt an diesen
Absatz: er faellt, sobald ein Upgrade die Zwei-Aeren-Konstanten hereinzieht.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from fastmcp import Client
from mcp.types import LATEST_PROTOCOL_VERSION

from seco_labor_mcp.server import mcp

# Die Revision, gegen die dieser Server gebaut und geprueft ist. Sie steht hier
# und in der README; `test_die_readme_nennt_dieselbe_revision` haelt beide
# gegeneinander, damit die Doku nicht davonlaeuft.
DOCUMENTED_PROTOCOL_VERSION = "2025-11-25"

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_die_dokumentierte_revision_ist_die_des_sdk() -> None:
    """Gegen die SDK-Konstante gehalten, nicht gegen abgeschriebenen Spec-Text.

    Hebt ein Bump `LATEST_PROTOCOL_VERSION` an, faellt genau diese Zeile — und
    zwar bevor jemand die Aenderung an einem Client bemerkt.
    """
    assert LATEST_PROTOCOL_VERSION == DOCUMENTED_PROTOCOL_VERSION, (
        f"Das SDK handelt {LATEST_PROTOCOL_VERSION} aus, dokumentiert ist "
        f"{DOCUMENTED_PROTOCOL_VERSION}. README und diese Konstante nachziehen."
    )


async def test_ein_echter_handshake_liefert_genau_diese_revision() -> None:
    """Gemessen statt aus der Konstante geschlossen.

    Die Zusicherung darueber vergleicht zwei Konstanten miteinander; sie sagt
    nichts darueber, was der Server am Draht aushandelt. Erst ein echter
    `initialize` gegen genau dieses `mcp`-Objekt tut das.
    """
    async with Client(mcp) as client:
        ausgehandelt = client.initialize_result.protocolVersion
    assert ausgehandelt == DOCUMENTED_PROTOCOL_VERSION


@pytest.mark.parametrize("datei", ["README.md", "README.de.md"])
def test_beide_readmes_nennen_dieselbe_revision(datei: str) -> None:
    """Eine Doku, die weniger oder anderes sagt als der Server tut, ist die
    teurere Haelfte des Problems: sie sieht geprueft aus.

    Beide Sprachen einzeln parametrisiert. Nur die englische zu pruefen waere
    genau die Luecke, an der die zwei schon anderswo im Portfolio
    auseinandergelaufen sind — eine README wandert, die andere bleibt stehen,
    und niemand merkt es, weil der Test die stehengebliebene nie ansieht.
    """
    text = (_ROOT / datei).read_text(encoding="utf-8")
    revisionen = set(re.findall(r"`(20\d\d-\d\d-\d\d)`", text))
    assert DOCUMENTED_PROTOCOL_VERSION in revisionen, (
        f"{datei} nennt {sorted(revisionen)}, erwartet {DOCUMENTED_PROTOCOL_VERSION}"
    )


def test_das_sdk_kennt_hier_nur_eine_aera() -> None:
    """Warum dieser Server keinen Zwei-Aeren-Pin fuehrt — und wann er einen braucht.

    `mcp` 2.x bedient zwei Protokoll-Aeren ueber denselben Server: den alten
    `initialize`-Handshake mit eigener Obergrenze und die neuere Umschlagform
    pro Anfrage. Beide Konstanten leben in `mcp.types.version`, und
    `LATEST_PROTOCOL_VERSION` ist dort ein Alias auf die *moderne* Aera — wer
    nur gegen ihn pinnt, sichert die Aera, die heute praktisch niemand spricht.

    Unter `mcp` 1.x gibt es das Modul nicht und die Frage stellt sich nicht.
    Zieht ein fastmcp-Upgrade `mcp` 2.x herein, faellt dieser Test und sagt,
    dass der Pin oben auf ein Paar erweitert werden muss.
    """
    try:
        import mcp.types.version as sdk_version
    except ModuleNotFoundError:
        return  # mcp 1.x: eine Aera, nichts zu trennen

    handshake = getattr(sdk_version, "LATEST_HANDSHAKE_VERSION", None)
    modern = getattr(sdk_version, "LATEST_MODERN_VERSION", None)
    pytest.fail(
        "Das SDK fuehrt jetzt zwei Protokoll-Aeren "
        f"(Handshake {handshake}, modern {modern}). Dieser Test pinnt nur eine "
        "Revision; er muss auf ein Paar erweitert werden, sonst sichert er die "
        "Aera, die heutige Clients nicht sprechen."
    )
