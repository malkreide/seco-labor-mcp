#!/usr/bin/env python3
"""Was hat der geplante Live-Lauf festgestellt — clear, finding oder unknown?

WARUM DAS EIN SKRIPT IST UND KEIN YAML-BLOCK
--------------------------------------------
`if: failure()` kennt zwei Antworten: rot und nicht rot. Ein Live-Lauf hat
drei, und die dritte ist die, die zaehlt:

  clear    Die Suite ist gelaufen und war gruen.
  finding  Die Suite ist gelaufen und etwas ist gefallen.
  unknown  Die Suite ist NICHT gelaufen — und niemand weiss, ob der Vertrag
           mit der Quelle noch haelt.

Ein gescheitertes `pip install`, ein Timeout, eine umbenannte Marke: alles
`unknown`, alles sieht unter `if: failure()` aus wie ein gebrochener Vertrag.
Und ein Lauf, in dem jeder Test uebersprungen wurde, sieht unter jedem
Exit-Code-Check aus wie Erfolg.

Diese Einordnung entscheidet, ob ein Issue aufgeht oder zugeht. Sie in einen
`run:`-Block zu schreiben hiesse, den einzigen Teil des Workflows, der etwas
behauptet, an die einzige Stelle zu legen, an der ihn niemand testen kann.
Deshalb steht sie hier, neben ihrem Test.

DER UEBERSPRUNGENE LAUF
-----------------------
Gemessen am 7.8.2026 an `swiss-transport-mcp`: Ohne `TRANSPORT_API_KEY`
ueberspringt die Live-Suite alle sechs Tests, und pytest endet mit 0. Ein
woechentlicher Job haette gemeldet: gruen. Geprueft haette er nichts — und ein
offenes Issue haette er zugemacht, mit einem Vergleich, den es nie gab.

`tests - skipped == 0` ist deshalb `unknown` und nicht `clear`. Ein Secret, das
niemand gesetzt hat, ist kein gruener Vertrag mit der Quelle; es ist gar keiner.

DIE STUMME QUELLE
-----------------
Gemessen am 5.9.2026 an diesem Repo (Lauf 33953313377): unfallstatistik.ch
antwortete auf keine einzige Anfrage — `ConnectError: All connection attempts
failed`. Zehn Live-Tests fielen, dieser Reporter buchte `finding`, und der
Workflow eroeffnete Issue #72: «Der Vertrag mit der Quelle ist betroffen.» Am
naechsten Morgen war die Suite gruen und das Issue schloss sich selbst. Dasselbe
am 16.8.2026, Issue #34, mit derselben Ursache und demselben Verlauf.

Festgestellt hat so ein Lauf ueber den Vertrag gar nichts. Wer aus einer Stoerung
einen Befund macht, misst die eigene Erreichbarkeit — und wer zweimal ein Issue
sieht, das sich von selbst schliesst, sieht beim dritten Mal nicht mehr hin.

Die Live-Tests markieren diesen Fall jetzt selbst: Erreicht ein Test die Quelle
nicht, ueberspringt er sich mit `QUELLE_AUS_MARKE` als Praefix statt zu fallen.
Ein solcher Skip ist `unknown`, nie `clear` — auch dann nicht, wenn der Rest der
Suite gruen war. Sonst schliesst ein halber Ausfall ein echtes offenes Issue.

Die Marke ist unsere eigene und wird hier gesetzt, nicht aus fremdem Text
geraten. Ein Skip ohne sie bleibt, was er war: eine Entscheidung im Test.

DIE QUELLE IST DAS JUNIT-XML, NICHT DER EXIT-CODE
-------------------------------------------------
Der Exit-Code von pytest sagt 0 fuer «alles gruen» und fuer «alles
uebersprungen» dasselbe. Das XML zaehlt Tests, Fehler, Fehlschlaege und
Uebersprungene getrennt, also wird es gelesen. Fehlt es, ist pytest gar nicht
bis zum Schreiben gekommen — auch das ist `unknown`, und zwar mit Grund.

Aufruf:
    python scripts/classify_live_run.py live-report.xml
    python scripts/classify_live_run.py live-report.xml --pytest-exit 1

Gibt `state=...` und `reason=...` auf stdout aus und haengt beides an
`$GITHUB_OUTPUT` an, wenn die Variable gesetzt ist. Der Exit-Code ist immer 0:
Ueber rot oder gruen entscheidet der Workflow, nicht dieser Reporter.
"""

from __future__ import annotations

import argparse
import os
import xml.etree.ElementTree as ET
from pathlib import Path

CLEAR = "clear"
FINDING = "finding"
UNKNOWN = "unknown"

# Praefix, mit dem ein Live-Test sich selbst ueberspringt, wenn die Quelle nicht
# geantwortet hat. `tests/test_live.py` importiert die Marke von hier — eine
# Kopie auf beiden Seiten wuerde beim naechsten Umformulieren auseinanderlaufen,
# und zwar still: Der Reporter faende die Marke nicht mehr und buchte wieder
# `finding`, ohne dass irgendetwas rot wird.
QUELLE_AUS_MARKE = "QUELLE-AUS:"


def _quelle_aus(suites: list[ET.Element]) -> int:
    """Wie viele Tests haben sich uebersprungen, weil die Quelle stumm blieb?

    Gelesen wird das `message`-Attribut von `<skipped>`; dort steht der Grund
    von `pytest.skip(...)` woertlich, ohne Praefix (gemessen mit pytest 8 im
    JUnit-XML). Der Elementtext traegt zusaetzlich Datei und Zeile — er wird
    bewusst nicht gelesen, damit ein Testname, der die Marke zufaellig enthaelt,
    hier nichts ausloest.
    """
    return sum(
        1
        for suite in suites
        for skipped in suite.iter("skipped")
        if (skipped.get("message") or "").lstrip().startswith(QUELLE_AUS_MARKE)
    )


def classify(report: Path, pytest_exit: int | None = None) -> tuple[str, str]:
    """(state, reason) aus einem JUnit-XML und optional dem pytest-Exit-Code."""
    if not report.is_file():
        return (
            UNKNOWN,
            f"kein Report unter {report} — pytest ist nicht bis zum Schreiben "
            "gekommen" + (f" (Exit {pytest_exit})" if pytest_exit is not None else ""),
        )
    try:
        root = ET.parse(report).getroot()
    except (ET.ParseError, OSError) as exc:
        return UNKNOWN, f"{report} ist nicht lesbar: {exc}"

    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        return UNKNOWN, f"{report} enthaelt keine testsuite"

    def total(attr: str) -> int:
        return sum(int(s.get(attr) or 0) for s in suites)

    tests, failures, errors, skipped = (
        total("tests"),
        total("failures"),
        total("errors"),
        total("skipped"),
    )

    if failures or errors:
        return (
            FINDING,
            f"{failures} Fehlschlag/Fehlschlaege und {errors} Fehler von {tests} Test(s)",
        )
    if tests == 0:
        return (
            UNKNOWN,
            "null Tests eingesammelt — die Marke oder die Dateien haben sich "
            "bewegt, und ein Erfolg ohne Test ist kein Erfolg",
        )

    # Vor dem allgemeinen Uebersprungen-Zweig, weil diese Auskunft die genauere
    # ist: «alle uebersprungen» raet auf ein fehlendes Secret, hier steht die
    # Ursache fest. Beide enden auf `unknown`, aber der Grund geht ins Log und
    # in den Issue-Kommentar.
    stumm = _quelle_aus(suites)
    if stumm:
        return (
            UNKNOWN,
            f"{stumm} von {tests} Test(s) haben unfallstatistik.ch nicht erreicht — "
            "ueber den Vertrag mit der Quelle ist damit nichts festgestellt, "
            "weder im Guten noch im Schlechten",
        )

    if tests - skipped == 0:
        return (
            UNKNOWN,
            f"alle {tests} Test(s) uebersprungen — meist ein fehlendes Secret oder "
            "eine nicht erfuellte Vorbedingung. Geprueft wurde nichts",
        )
    return CLEAR, f"{tests - skipped} von {tests} Test(s) ausgefuehrt, alle gruen"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="classify_live_run")
    ap.add_argument("report", type=Path, help="Pfad zum JUnit-XML von pytest")
    ap.add_argument("--pytest-exit", type=int, default=None)
    args = ap.parse_args(argv)

    state, reason = classify(args.report, args.pytest_exit)
    print(f"state={state}")
    print(f"reason={reason}")

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        # Zeilenumbruch raus, bevor der Grund in `$GITHUB_OUTPUT` geht: Die
        # `key=value`-Form endet an der ersten neuen Zeile, und was danach
        # steht, liest der Runner als naechstes Output. Ein Grund koennte so
        # ein `state=clear` nachschieben und den roten Lauf gruen faerben.
        flat = " ".join(reason.split())
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"state={state}\n")
            fh.write(f"reason={flat}\n")
    # Immer 0: Ueber rot oder gruen entscheidet der Workflow.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
