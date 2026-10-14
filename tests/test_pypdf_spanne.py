"""pypdf zieht nur minorweise ein — und das bleibt so.

Unter der frueheren Spanne `>=5.0.0,<7` kam pypdf 6.20.0 am 2026-10-09 still
in jede frische Installation. Es skalierte die Spaltenabstaende im
Layout-Modus herunter und brach die Spaltentrennung der UVG-Jahrestabellen;
die Offline-Suite blieb gruen, gesehen hat es erst der naechtliche Live-Lauf
(Issue #83). Vier Tage lang lieferte der Server unvollstaendige Tabellen.

Eine Obergrenze auf dem naechsten Minor macht aus einem solchen Bump einen
Dependabot-PR, in dem die Offline-Proben gegen das aufgezeichnete Jahres-PDF
entscheiden. Der Rueckfall auf eine Major-Grenze ist still: Er macht nichts
rot, er laesst das naechste brechende Minor nur wieder ungefragt herein.
"""

from __future__ import annotations

import pathlib
import tomllib

from packaging.requirements import Requirement
from packaging.version import Version

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _pypdf() -> Requirement:
    daten = tomllib.loads((_ROOT / "pyproject.toml").read_text())
    treffer = [
        Requirement(spec)
        for spec in daten["project"]["dependencies"]
        if Requirement(spec).name == "pypdf"
    ]
    assert len(treffer) == 1, f"genau ein pypdf-Specifier erwartet, gefunden: {treffer}"
    return treffer[0]


def _grenze(requirement: Requirement, operator: str) -> Version:
    grenzen = [s for s in requirement.specifier if s.operator == operator]
    assert len(grenzen) == 1, f"genau eine Grenze {operator!r} erwartet in {requirement}"
    return Version(grenzen[0].version)


def test_pypdf_hat_eine_obergrenze_auf_einem_minor() -> None:
    """`<6.21` ja, `<7` oder `<7.0` nicht.

    Verlangt ist nur, dass die Grenze innerhalb des Majors der Untergrenze auf
    einem Minor liegt — nicht, dass sie genau ein Minor ueber ihr steht. Sonst
    wuerde jeder Dependabot-PR, der die Grenze bloss anhebt, an dieser Regel
    rot statt an den Proben, um die es geht.
    """
    pypdf = _pypdf()
    unten = _grenze(pypdf, ">=")
    oben = _grenze(pypdf, "<")
    assert oben.major == unten.major, (
        f"pypdf-Obergrenze {oben} liegt auf einem anderen Major als die Untergrenze "
        f"{unten}. Damit zieht jedes neue Minor ungefragt ein — genau so kam 6.20.0 "
        "herein. Die Grenze gehoert auf das naechste Minor."
    )
    assert oben > unten, f"Obergrenze {oben} schliesst die Untergrenze {unten} aus"
    assert oben.micro == 0, (
        f"Obergrenze {oben} liegt auf einem Patch-Release; Patch-Releases sollen "
        "innerhalb des Minors frei einziehen."
    )
