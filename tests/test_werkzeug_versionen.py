"""Die ruff-Version steht an genau einer Stelle — und bleibt dort.

Sie stand an zweien: `ruff==0.16.1` im `[dev]`-Extra und noch einmal als
`pip install ruff==0.16.1` in `ci.yml`. Beide nannten dieselbe Version, der
Aufbau war also nicht rot — aber der CI-Schritt lief nach dem Install des
Extras und gewann gegen pyproject. Wer den Pin dort anhob, veraenderte damit
die CI nicht; wer den in `ci.yml` anhob, veraenderte den lokalen Lauf nicht.
Zwei Angaben, die sich stumm einigen muessen, sind eine Angabe zu viel.

Der Rueckfall ist still: Er macht kein Gate rot, er laesst es lediglich mit
einer anderen Version laufen als der, gegen die lokal geprueft wurde.
"""

from __future__ import annotations

import pathlib
import re
import tomllib

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_WORKFLOWS = _ROOT / ".github" / "workflows"


def _dev_abhaengigkeiten() -> list[str]:
    daten = tomllib.loads((_ROOT / "pyproject.toml").read_text())
    return daten["project"]["optional-dependencies"]["dev"]


def test_ruff_ist_exakt_gepinnt() -> None:
    """Eine Spanne laesst lokalen Lauf und CI verschiedene Versionen fahren."""
    specs = [s for s in _dev_abhaengigkeiten() if re.match(r"^ruff\b", s)]
    assert len(specs) == 1, f"genau ein ruff-Specifier erwartet, gefunden: {specs}"
    assert re.fullmatch(r"ruff==\d+\.\d+\.\d+", specs[0]), (
        f"ruff muss als ruff==X.Y.Z gepinnt sein, gefunden {specs[0]!r}."
    )


def test_der_pin_ist_die_einzige_versionsquelle() -> None:
    """Kein Workflow darf ruff selbst installieren."""
    for workflow in sorted(_WORKFLOWS.glob("*.yml")):
        # Kommentarzeilen raus, damit ein erklaerender Hinweis auf den
        # frueheren Schritt den Test nicht selbst ausloest.
        zeilen = [z for z in workflow.read_text().splitlines() if not z.lstrip().startswith("#")]
        treffer = [z.strip() for z in zeilen if re.search(r"pip install\s+ruff", z)]
        assert not treffer, (
            f"{workflow.name} installiert ruff direkt ({treffer}). Dieser Schritt "
            "laeuft nach dem dev-Install und ueberstimmt den Pin in pyproject."
        )


def test_der_workflow_scan_findet_ueberhaupt_etwas() -> None:
    """Sichert die Pruefung oben gegen ein leeres Verzeichnis ab.

    Faende der Glob nichts, waere die Schleife leer und die Zusicherung
    trivialerweise wahr — gruen, ohne irgendetwas geprueft zu haben.
    """
    workflows = list(_WORKFLOWS.glob("*.yml"))
    assert len(workflows) >= 2, f"Workflow-Scan findet fast nichts: {workflows}"
    assert any("ruff check" in w.read_text() for w in workflows), (
        "kein Workflow ruft ruff auf — der Scan sucht am falschen Ort"
    )
