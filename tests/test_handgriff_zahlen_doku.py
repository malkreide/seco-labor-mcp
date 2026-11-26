"""Die Zahlwoerter der «… Handgriffe daraus»-Listen gegen ihre Punkte.

Dieselbe Drift wie bei den Codex-Tabellen, eine Ebene kleiner: Eine Liste
waechst um einen Punkt, die Zeile darueber bleibt stehen, und der Abschnitt
kuendigt drei Handgriffe an und liefert vier. Nichts wird rot, und wer die
Zeile liest statt zu zaehlen, haelt den vierten fuer einen Einschub.

WARUM DAS NOETIG IST
--------------------
Am 24.11.2026 ist genau das passiert: Der Handgriff «Wer zum Warten raet,
liest vorher merged_at» wurde angefuegt, die Ueberschrift blieb auf «Drei».
Aufgefallen ist es nicht beim Schreiben und nicht in der CI, sondern erst beim
Aufraeumen zweier zu langer Zeilen im selben Abschnitt. Am selben Tag hatte
`tests/test_codex_tabellen_doku.py` dieselbe Drift in einer Tabelle gefangen —
weil sie dort gegatet war und hier nicht.

WAS HIER NICHT GEPRUEFT WIRD
----------------------------
Ob die Handgriffe etwas taugen, und ob die Liste vollstaendig ist. Geprueft
wird nur, dass die angekuendigte Zahl der gelieferten entspricht.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_CLAUDE_MD = _ROOT / "CLAUDE.md"

# So viele Listen traegt die Datei. Die Zahl steht hier, damit ein Erkenner,
# der ploetzlich nichts mehr findet, auffaellt statt leer durchzulaufen.
_ERWARTETE_LISTEN = 4

_ZAHLWORT = {
    1: "Ein",
    2: "Zwei",
    3: "Drei",
    4: "Vier",
    5: "Fünf",
    6: "Sechs",
    7: "Sieben",
    8: "Acht",
}

_UEBERSCHRIFT = re.compile(r"^(\w+) Handgriffe daraus:$")


def _listen(text: str) -> list[tuple[int, str, int]]:
    """Je Liste: Zeilennummer, angekuendigtes Zahlwort, gezaehlte Punkte.

    Ein Punkt ist eine Zeile, die mit «- ` beginnt; Fortsetzungszeilen sind
    eingerueckt und zaehlen nicht. Die Liste endet an der ersten Zeile, die
    weder leer noch eingerueckt noch ein Punkt ist.
    """
    zeilen = text.splitlines()
    gefunden: list[tuple[int, str, int]] = []
    for i, zeile in enumerate(zeilen):
        treffer = _UEBERSCHRIFT.match(zeile)
        if not treffer:
            continue
        punkte = 0
        for weiter in zeilen[i + 1 :]:
            if weiter.startswith("- "):
                punkte += 1
            elif weiter.strip() == "" or weiter.startswith("  "):
                continue
            else:
                break
        gefunden.append((i + 1, treffer.group(1), punkte))
    return gefunden


def test_der_erkenner_findet_die_listen() -> None:
    """Kontrolle vor der Messung: Ein Erkenner, der nichts findet, prueft nichts."""
    gefunden = _listen(_CLAUDE_MD.read_text(encoding="utf-8"))
    assert len(gefunden) == _ERWARTETE_LISTEN, (
        f"{len(gefunden)} «… Handgriffe daraus»-Listen gefunden, erwartet "
        f"{_ERWARTETE_LISTEN}. Kommt eine hinzu, ist diese Zahl zu erhoehen; "
        "findet der Erkenner keine, misst der Test darunter nichts."
    )
    assert all(punkte > 0 for _, _, punkte in gefunden), f"Eine Liste hat keine Punkte: {gefunden}"


def test_die_zahlwoerter_stimmen_mit_den_punkten() -> None:
    """Das eigentliche Gate: angekuendigte Zahl gegen gelieferte."""
    abweichungen = []
    for zeilennummer, wort, punkte in _listen(_CLAUDE_MD.read_text(encoding="utf-8")):
        erwartet = _ZAHLWORT.get(punkte)
        assert erwartet, (
            f"Zeile {zeilennummer}: {punkte} Punkte — fuer diese Zahl fehlt hier das Zahlwort."
        )
        if wort != erwartet:
            abweichungen.append(
                f"Zeile {zeilennummer}: «{wort} Handgriffe daraus» bei {punkte} "
                f"Punkten — erwartet «{erwartet}»"
            )
    assert not abweichungen, "Zahlwort und Liste gehen auseinander:\n  " + "\n  ".join(abweichungen)


def test_der_erkenner_zaehlt_fortsetzungszeilen_nicht_mit() -> None:
    """Gegenprobe zum Erkenner, an einem Text mit bekannter Antwort.

    Ohne diese Kontrolle koennte er eingerueckte Fortsetzungszeilen als
    eigene Punkte lesen und waere dann immer anderer Meinung als die Datei.
    """
    probe = (
        "Zwei Handgriffe daraus:\n"
        "\n"
        "- **Erster.** Mit einer Zeile,\n"
        "  die eingerueckt weitergeht.\n"
        "- **Zweiter.** Und noch einer.\n"
        "\n"
        "Danach gewoehnlicher Text, der die Liste beendet.\n"
        "- Dieser Punkt gehoert nicht mehr dazu.\n"
    )
    assert _listen(probe) == [(1, "Zwei", 2)], _listen(probe)
