"""Die drei Codex-Tabellen aus CLAUDE.md, gegen sich selbst gerechnet.

Die Zahlen darin stammen aus der GitHub-API und sind nicht offline
nachstellbar — ein Test kann sie also nicht gegen die Quelle halten. Was er
kann, ist die Arithmetik: Jede Tabelle fuehrt Anfang, Ende und Abstand
nebeneinander, und drei der fuenf Spalten sind aus den anderen zwei
ausgerechnet.

WARUM DAS NOETIG IST
--------------------
Am 13.11. und am 22.11.2026 wurde je ein Merge-Zeitpunkt aus dem Zeitstempel
einer Benachrichtigung gelesen statt aus `merged_at`; beide Male lag die Zahl
um wenige Sekunden daneben, und beide Male fiel es erst beim zweiten Hinsehen
auf. Eine falsche Sekunde macht die Tabelle nicht unbrauchbar, aber sie macht
sie unpruefbar — und der Absatz darueber behauptet Spannen, die auf genau
diesen Sekunden stehen.

Gehalten werden ausserdem die Zahlwoerter im Fliesstext. Wer eine Zeile
anfuegt und «acht» stehen laesst, wo neun Zeilen stehen, hinterlaesst denselben
stillen Fehler wie eine falsche Sekunde.

WAS HIER NICHT GEPRUEFT WIRD
----------------------------
Ob die Zahlen stimmen. Dieser Test kann eine in sich konsistente, aber
durchgehend falsch abgeschriebene Tabelle nicht erkennen. Dagegen hilft nur
die Regel aus dem Abschnitt selbst: Zeiten aus `merged_at`, `created_at` und
`updated_at`, nicht aus einer Benachrichtigung.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_CLAUDE_MD = _ROOT / "CLAUDE.md"

_LAUFZEIT = ("PR", "Datum", "Start (UTC)", "Ende (UTC)", "Dauer")
_MERGE = ("PR", "Merge", "Kommentar erscheint", "Urteil steht", "Merge vor dem Urteil um")
_BEFUNDLOS = ("PR", "Datum", "Commit", "`get_reviews`", "Befundlos-Kommentar")

# Der eine Lauf, der die Spanne aufmacht. Steht hier als Wert, weil der Text
# ihn namentlich nennt; gemessen wird, dass er wirklich der Ausreisser ist.
_AUSREISSER = "#73"
_ENG_VON, _ENG_BIS = 47, 61

_ZAHLWORT = {
    2: "zwei",
    3: "drei",
    4: "vier",
    5: "fünf",
    6: "sechs",
    7: "sieben",
    8: "acht",
    9: "neun",
    10: "zehn",
    11: "elf",
    12: "zwölf",
}


def _tabelle(kopf: tuple[str, ...]) -> list[dict[str, str]]:
    """Die Zeilen der Tabelle mit genau diesem Kopf, als Liste von Abbildungen.

    Gesucht wird ueber die Spaltenkoepfe, nicht ueber Zeilennummern: Der
    Abschnitt darf sich verschieben. Mehrdeutigkeit ist ein Fehlschlag mit
    Hinweis, kein stilles Nehmen der ersten Tabelle.
    """
    zeilen = [
        [z.strip() for z in roh.strip().strip("|").split("|")]
        for roh in _CLAUDE_MD.read_text(encoding="utf-8").splitlines()
        if roh.lstrip().startswith("|")
    ]
    treffer = [i for i, z in enumerate(zeilen) if tuple(z) == kopf]
    assert len(treffer) == 1, (
        f"Tabellenkopf {kopf} nicht eindeutig gefunden ({len(treffer)} Treffer) "
        "— Abschnitt in CLAUDE.md umgebaut?"
    )

    gelesen: list[dict[str, str]] = []
    for z in zeilen[treffer[0] + 1 :]:
        if len(z) != len(kopf) or set("".join(z)) <= set("-: "):
            if gelesen:
                break
            continue
        if not z[0].startswith("#"):
            break
        gelesen.append(dict(zip(kopf, z)))
    assert gelesen, f"Tabelle {kopf} hat keine Datenzeilen."
    return gelesen


def _sek(uhrzeit: str) -> int:
    stunde, minute, sekunde = (int(teil) for teil in uhrzeit.split(":"))
    return stunde * 3600 + minute * 60 + sekunde


def _dauer_sek(text: str) -> int:
    """«3 min 11 s», «47 s» und «1 min 01 s» in Sekunden.

    Ein unbekanntes Format ist ein Fehlschlag: Ein Erkenner, der daraus still
    eine 0 macht, liesse jede Abweichung als Null-Differenz durchgehen.
    """
    treffer = re.fullmatch(r"(?:(\d+) min )?(\d+) s", text.strip())
    assert treffer, f"Dauerangabe «{text}» nicht lesbar."
    minuten, sekunden = treffer.group(1), treffer.group(2)
    return (int(minuten) if minuten else 0) * 60 + int(sekunden)


def test_der_erkenner_liest_beide_dauerformen() -> None:
    """Gegenprobe zum Erkenner, bevor er etwas behauptet."""
    assert _dauer_sek("47 s") == 47
    assert _dauer_sek("1 min 01 s") == 61
    assert _dauer_sek("3 min 11 s") == 191
    for kaputt in ("47", "1 min", "eine Minute", ""):
        try:
            _dauer_sek(kaputt)
        except AssertionError:
            continue
        raise AssertionError(f"«{kaputt}» haette nicht gelesen werden duerfen.")


def test_die_laufzeiten_rechnen_sich_aus_start_und_ende() -> None:
    """Spalte «Dauer» gegen «Ende» minus «Start», Zeile fuer Zeile."""
    abweichungen = []
    for zeile in _tabelle(_LAUFZEIT):
        gerechnet = _sek(zeile["Ende (UTC)"]) - _sek(zeile["Start (UTC)"])
        if gerechnet != _dauer_sek(zeile["Dauer"]):
            abweichungen.append(
                f"{zeile['PR']}: {zeile['Start (UTC)']} bis {zeile['Ende (UTC)']} "
                f"sind {gerechnet} s, die Tabelle sagt «{zeile['Dauer']}»"
            )
    assert not abweichungen, "Laufzeit-Tabelle rechnet nicht auf:\n  " + "\n  ".join(abweichungen)


def test_der_abstand_zum_merge_rechnet_sich_auf() -> None:
    """Spalte «Merge vor dem Urteil um» gegen «Urteil steht» minus «Merge».

    Mitgeprueft ist damit die Behauptung des Absatzes: In jeder Zeile liegt
    der Merge *vor* dem Urteil. Ein negativer Abstand waere kein Rechenfehler,
    sondern das Ende des Befunds.
    """
    abweichungen = []
    for zeile in _tabelle(_MERGE):
        gerechnet = _sek(zeile["Urteil steht"]) - _sek(zeile["Merge"])
        if gerechnet <= 0:
            abweichungen.append(f"{zeile['PR']}: Urteil liegt nicht nach dem Merge")
        elif gerechnet != _dauer_sek(zeile["Merge vor dem Urteil um"]):
            abweichungen.append(
                f"{zeile['PR']}: {zeile['Merge']} bis {zeile['Urteil steht']} sind "
                f"{gerechnet} s, die Tabelle sagt «{zeile['Merge vor dem Urteil um']}»"
            )
    assert not abweichungen, "Merge-Tabelle rechnet nicht auf:\n  " + "\n  ".join(abweichungen)


def test_die_beiden_tabellen_nennen_dieselben_zeiten() -> None:
    """Wo beide Tabellen denselben PR fuehren, muss der Lauf derselbe sein.

    Die Laufzeit-Tabelle nennt Start und Ende des Statuskommentars, die
    Merge-Tabelle dieselben zwei Zeitpunkte unter anderen Namen. Driften sie
    auseinander, stammt eine der beiden aus einer anderen Abfrage.
    """
    laufzeit = {z["PR"]: (z["Start (UTC)"], z["Ende (UTC)"]) for z in _tabelle(_LAUFZEIT)}
    gemeinsam = 0
    abweichungen = []
    for zeile in _tabelle(_MERGE):
        if zeile["PR"] not in laufzeit:
            continue
        gemeinsam += 1
        erwartet = (zeile["Kommentar erscheint"], zeile["Urteil steht"])
        if laufzeit[zeile["PR"]] != erwartet:
            abweichungen.append(
                f"{zeile['PR']}: Laufzeit-Tabelle {laufzeit[zeile['PR']]}, Merge-Tabelle {erwartet}"
            )
    assert not abweichungen, "Die Tabellen gehen auseinander:\n  " + "\n  ".join(abweichungen)
    assert gemeinsam >= 2, (
        f"Nur {gemeinsam} PR in beiden Tabellen — dann vergleicht dieser Test praktisch nichts."
    )


def test_der_fliesstext_nennt_so_viele_laeufe_wie_die_tabellen_fuehren() -> None:
    """Die Zahlwoerter im Text gegen die Zeilenzahl.

    Das ist der Fehler, der beim Anfuegen einer Zeile am naechsten liegt: Die
    Tabelle waechst, der Satz darueber bleibt stehen, und der Abschnitt
    behauptet eine Stichprobe, die er nicht mehr hat.
    """
    text = _CLAUDE_MD.read_text(encoding="utf-8")
    befundlos = len(_tabelle(_BEFUNDLOS))
    nach_dem_merge = len(_tabelle(_MERGE))

    fehlend = [
        satz
        for satz in (
            f"Auf den {_ZAHLWORT[befundlos]} befundlosen Läufen dieses Repos",
            f"Was die {_ZAHLWORT[befundlos]} Messungen **nicht** hergeben",
            f"{_ZAHLWORT[befundlos].capitalize()} Läufe aus einem Repo sind kein Produktentscheid",
            f"Und {_ZAHLWORT[nach_dem_merge]}mal urteilte Codex erst nach dem Merge",
        )
        if satz not in text
    ]
    assert not fehlend, (
        f"Die Tabellen fuehren {befundlos} befundlose Laeufe und {nach_dem_merge} "
        "Faelle nach dem Merge, der Fliesstext sagt etwas anderes. Nicht "
        "gefunden:\n  " + "\n  ".join(fehlend)
    )


def test_die_haeufung_und_der_ausreisser_stimmen() -> None:
    """Die beiden Behauptungen zur Spanne, aus der Tabelle gerechnet.

    Der Absatz sagt: Faktor vier zwischen dem laengsten und dem kuerzesten
    Lauf, und alle ausser einem liegen eng beieinander. Beides haengt an genau
    einer Zeile — faellt sie weg oder kommt eine lange hinzu, ist der Satz zu
    schreiben, nicht der Test zu lockern.
    """
    dauern = {z["PR"]: _dauer_sek(z["Dauer"]) for z in _tabelle(_LAUFZEIT)}
    laengster = max(dauern, key=lambda pr: dauern[pr])
    assert laengster == _AUSREISSER, (
        f"Laengster Lauf ist {laengster}, der Text nennt {_AUSREISSER}."
    )

    faktor = dauern[laengster] / min(dauern.values())
    assert int(faktor) == 4, (
        f"Verhaeltnis zwischen laengstem und kuerzestem Lauf ist {faktor:.2f} — "
        "«Faktor vier» im Text stimmt dann nicht mehr."
    )

    eng = {pr: s for pr, s in dauern.items() if pr != _AUSREISSER}
    assert all(_ENG_VON <= s <= _ENG_BIS for s in eng.values()), (
        f"Nicht alle uebrigen Laeufe liegen zwischen {_ENG_VON} s und "
        f"{_ENG_BIS} s: {sorted(eng.items(), key=lambda paar: paar[1])}"
    )
    text = _CLAUDE_MD.read_text(encoding="utf-8")
    assert f"Sieben der {_ZAHLWORT[len(dauern)]} Läufe liegen dabei zwischen" in text, (
        f"Der Text nennt nicht {_ZAHLWORT[len(eng)]} eng liegende Laeufe von "
        f"{_ZAHLWORT[len(dauern)]}."
    )
