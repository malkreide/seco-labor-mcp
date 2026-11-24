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

import json
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


def _dauer_text(sekunden: int) -> str:
    """Sekunden zurueck in die Schreibweise der Tabelle.

    Gebraucht, um die im Fliesstext genannten Ausreisser samt Dauer gegen die
    Tabelle zu halten. Unter einer Minute schreibt die Tabelle nur Sekunden.
    """
    if sekunden < 60:
        return f"{sekunden} s"
    return f"{sekunden // 60} min {sekunden % 60:02d} s"


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

    # Und zurueck, in beiden Formen. Ohne diese Kontrolle koennte der
    # Rueckwandler unten jede Dauer als nicht-genannt melden.
    for text in ("47 s", "1 min 01 s", "1 min 20 s", "3 min 11 s"):
        assert _dauer_text(_dauer_sek(text)) == text, (
            f"Hin und zurueck ergibt nicht «{text}», sondern «{_dauer_text(_dauer_sek(text))}»."
        )


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

    # Die Gruppe wird aus dem Band gerechnet, nicht aus «alle ausser dem
    # Ausreisser»: Seit #101 (1 min 20 s) liegt mehr als ein Lauf darueber, und
    # eine Zusicherung, die genau einen annimmt, waere beim naechsten Nachtrag
    # wieder die Behauptung, die sie pruefen soll.
    eng = {pr: s for pr, s in dauern.items() if _ENG_VON <= s <= _ENG_BIS}
    drueber = sorted(
        ((pr, s) for pr, s in dauern.items() if s > _ENG_BIS),
        key=lambda paar: paar[1],
    )
    assert eng, f"Kein Lauf liegt zwischen {_ENG_VON} s und {_ENG_BIS} s."

    text = _CLAUDE_MD.read_text(encoding="utf-8")
    satz = (
        f"{_ZAHLWORT[len(eng)].capitalize()} der {_ZAHLWORT[len(dauern)]} "
        "Läufe liegen dabei zwischen"
    )
    assert satz in text, (
        f"Der Text nennt nicht {_ZAHLWORT[len(eng)]} eng liegende Laeufe von "
        f"{_ZAHLWORT[len(dauern)]}. Erwartet war: «{satz} …»"
    )

    fehlend = [
        f"{pr} mit {_dauer_text(s)}"
        for pr, s in drueber
        if f"{pr} mit {_dauer_text(s)}" not in text
    ]
    assert not fehlend, (
        "Der Text nennt die Laeufe oberhalb des Bandes nicht so, wie die "
        f"Tabelle sie fuehrt. Nicht gefunden: {fehlend}"
    )


# ----------------------------------------------------------------------------
# Der Fund vom 22.11.2026: ein Lauf, der nicht stattfand
#
# Die drei Kommentartexte unten sind wortgetreu aus der GitHub-API geholt, mit
# Datum und Herkunft. Nachgebildet ist keiner — eine erfundene Fassung koennte
# genau die Annahme bestaetigen, gegen die der Erkenner gebaut ist.
#
# Sie liegen bewusst NICHT unter `tests/fixtures/`: `fixture_data.recorded_names`
# zaehlt alles direkt in diesem Verzeichnis, Unterordner eingeschlossen, und
# `test_jede_fixture_steht_in_der_provenance` verlangt fuer jeden Namen einen
# Block in der von `scripts/record_fixtures.py` geschriebenen PROVENANCE.md.
# Ein Ordner dort machte also zwei fremde Tests rot, und der Recorder kann
# GitHub-Kommentare nicht nachziehen.
# ----------------------------------------------------------------------------

# PR #99, abgefragt am 22.11.2026 um 18:34:42 UTC (Lauf gestartet, kein Urteil).
_KOMMENTAR_LAEUFT = """<!-- codex-pull-request-review-summary -->
<!-- codex-review-state:v1 {"code_review":{"commit_sha":"d87669ed9231aa83dade\
2240b4b57db816a0f46d","has_any_findings":null,"has_unresolved_findings":null,\
"status":"running"},"security_review":{"commit_sha":null,"has_any_findings":\
null,"has_unresolved_findings":null,"status":null}} -->

<details>
<summary><strong>Codex Review Summary</strong>: \U0001f504 Running</summary>

| Review | Status | Commit | Review trigger |
| --- | --- | --- | --- |
| \U0001f4dd **Code Review** | \U0001f504 **Running** since 2026-11-22T18:34:40.847626Z \
| `d87669e` | Draft marked ready |

</details>"""

# Derselbe Kommentar, abgefragt um 18:35:41 UTC — in place aktualisiert.
_KOMMENTAR_BEFUNDLOS = """<!-- codex-pull-request-review-summary -->
<!-- codex-review-state:v1 {"code_review":{"commit_sha":"d87669ed9231aa83dade\
2240b4b57db816a0f46d","has_any_findings":false,"has_unresolved_findings":false,\
"status":"completed"},"security_review":{"commit_sha":null,"has_any_findings":\
null,"has_unresolved_findings":null,"status":null}} -->

<details>
<summary><strong>Codex Review Summary</strong>: ✅ Completed</summary>

| Review | Status | Commit | Review trigger |
| --- | --- | --- | --- |
| \U0001f4dd **Code Review** | ✅ **Completed** 2026-11-22T18:35:13.668776Z \
| `d87669e` | Draft marked ready |

</details>"""

# PR #100, 22.11.2026 um 18:42:35 UTC — acht Sekunden nach dem Eroeffnen des
# Entwurfs. Der ganze Kommentar, nicht ein Ausschnitt.
_KOMMENTAR_KEIN_LAUF = (
    "To use Codex here, [create an environment for this repo]"
    "(https://chatgpt.com/codex/cloud/settings/environments)."
)

# PR #100, abgefragt am 22.11.2026 um 19:03 UTC. Derselbe Head wie der
# Nicht-Lauf darueber — siebzehn Minuten spaeter, Ausloeser «Draft marked
# ready». Diese Aufzeichnung ist der Grund, warum die zweite Lesart im Absatz
# von CLAUDE.md gestrichen ist: An der Codex-Einrichtung war nichts kaputt.
_KOMMENTAR_NACHGEHOLT = """<!-- codex-pull-request-review-summary -->
<!-- codex-review-state:v1 {"code_review":{"commit_sha":"f279973d4e657e2aeef1\
d018e4aee840079436d5","has_any_findings":false,"has_unresolved_findings":false,\
"status":"completed"},"security_review":{"commit_sha":null,"has_any_findings":\
null,"has_unresolved_findings":null,"status":null}} -->

<details>
<summary><strong>Codex Review Summary</strong>: \u2705 Completed</summary>

| Review | Status | Commit | Review trigger |
| --- | --- | --- | --- |
| \U0001f4dd **Code Review** | \u2705 **Completed** 2026-11-22T19:00:37.765915Z \
| `f279973` | Draft marked ready |

</details>"""

_MARKER_TABELLE = "<!-- codex-pull-request-review-summary -->"
_MARKER_ZUSTAND = "<!-- codex-review-state:v1"


def _codex_zustand(kommentare: list[str], reviews: list[object]) -> str:
    """Die Regel aus CLAUDE.md als Kode: «kein Lauf», «laeuft», «befundlos», «Befund».

    Erste Pruefung ist, ob ueberhaupt ein Statuskommentar da ist. Fehlt er, ist
    das die Auskunft — und nicht, wie das leere `get_reviews` daneben
    nahelegt, ein sauberer Lauf.

    Der Rueckfall ohne `codex-review-state:v1` liest die Statustabelle, weil der
    Marker nicht rueckwirkend gesetzt wird.
    """
    statusk = [k for k in kommentare if _MARKER_TABELLE in k]
    if not statusk:
        return "kein Lauf"
    assert len(statusk) == 1, f"Mehr als ein Statuskommentar ({len(statusk)})."
    k = statusk[0]

    if _MARKER_ZUSTAND in k:
        roh = k.split(_MARKER_ZUSTAND, 1)[1].split("-->", 1)[0].strip()
        zustand = json.loads(roh)["code_review"]
        if zustand["status"] != "completed":
            return "laeuft"
        return "Befund" if (zustand["has_any_findings"] or reviews) else "befundlos"

    if "**Completed**" not in k:
        return "laeuft"
    return "Befund" if reviews else "befundlos"


def _nur_reviews(reviews: list[object]) -> str:
    """Die falsche Regel, als Kode: «sauber, weil `get_reviews` leer ist».

    Steht hier, damit die Zusicherung darunter den Unterschied messen kann
    statt ihn zu behaupten.
    """
    return "Befund" if reviews else "befundlos"


def test_der_erkenner_liest_die_aufgezeichneten_kommentare() -> None:
    """Drei echte Kommentare, drei verschiedene Zustaende — bei leerem `get_reviews`.

    Das ist der Kern des Funds in einer Zusicherung: Dasselbe leere
    `get_reviews` begleitet einen laufenden, einen befundlosen und einen gar
    nicht stattgefundenen Lauf.
    """
    assert _codex_zustand([_KOMMENTAR_LAEUFT], []) == "laeuft"
    assert _codex_zustand([_KOMMENTAR_BEFUNDLOS], []) == "befundlos"
    assert _codex_zustand([_KOMMENTAR_KEIN_LAUF], []) == "kein Lauf"


def test_kein_statuskommentar_ist_nicht_befundlos() -> None:
    """Der Fund von PR #100, und was die falsche Regel daraus gemacht haette.

    Gemessen wird nicht nur, dass der Erkenner «kein Lauf» sagt, sondern dass
    die naheliegende Regel auf derselben Eingabe «befundlos» sagt. Ohne diesen
    Vergleich waere der Satz in CLAUDE.md eine Behauptung ueber einen Fehler,
    den niemand nachgerechnet hat.
    """
    richtig = _codex_zustand([_KOMMENTAR_KEIN_LAUF], [])
    falsch = _nur_reviews([])
    assert richtig == "kein Lauf"
    assert falsch == "befundlos"
    assert richtig != falsch, (
        "Die beiden Regeln kommen auf derselben Eingabe zum selben Ergebnis — "
        "dann belegt diese Zusicherung die Kosten der falschen Regel nicht."
    )

    # Positivkontrolle: Auf einem echten befundlosen Lauf sind beide einig.
    # Ohne sie liesse sich der Erkenner auch so lesen, als sage er immer
    # «kein Lauf».
    assert _codex_zustand([_KOMMENTAR_BEFUNDLOS], []) == _nur_reviews([]) == "befundlos"


def test_ein_befund_schlaegt_den_marker() -> None:
    """Nicht-leeres `get_reviews` bleibt ein Befund, auch bei «completed».

    CLAUDE.md nennt den Fall von PR #73: «Completed» stand zur selben Minute
    wie ein P2-Befund im Review-Objekt. Ein Erkenner, der nur den Marker liest,
    wuerde ihn durchwinken.
    """
    assert _codex_zustand([_KOMMENTAR_BEFUNDLOS], [object()]) == "Befund"


def test_die_anweisung_nennt_das_fehlen_als_auskunft() -> None:
    """Der Satz muss in CLAUDE.md stehen — sonst gatet dieser Test nichts.

    Hier stand zuerst eine zweite Zusicherung, der Tabellen-Marker duerfe nicht
    wortgetreu im Dokument vorkommen. Sie fiel sofort, und zu Recht: CLAUDE.md
    zitiert den Marker als Inline-Kode, weil der Abschnitt ihn erklaert. Die
    Sorge dahinter war gegenstandslos — `_codex_zustand` bekommt nur
    Kommentartexte, nie das Dokument. Die Gegenprobe zum Erkenner leistet der
    Vergleich mit `_nur_reviews` darueber.
    """
    text = _CLAUDE_MD.read_text(encoding="utf-8")
    assert "Kein Statuskommentar\nheisst nicht befundlos, sondern ungeprüft." in text, (
        "CLAUDE.md nennt nicht mehr, dass ein fehlender Statuskommentar die "
        "Auskunft ist. Ohne diesen Satz bleibt nur das Paar von oben, und das "
        "sieht auf PR #100 wie ein sauberer Lauf aus."
    )


def test_der_nicht_lauf_stoert_den_spaeteren_lauf_nicht() -> None:
    """Beide Kommentare von PR #100 zusammen, wie sie dort wirklich stehen.

    Der Zustand ist eine Eigenschaft des Statuskommentars, nicht des PR: Auf
    demselben Head stand erst die Absage und siebzehn Minuten spaeter ein
    regulaerer, befundloser Lauf. Ein Erkenner, der den ersten Kommentar
    nimmt oder sich an ihm verschluckt, laese den PR fuer immer als ungeprueft.

    Das ist zugleich die Aufzeichnung, die die zweite Lesart im Absatz
    widerlegt hat — gaebe es sie nicht, stuende dort noch eine Vermutung ueber
    die Codex-Einrichtung.
    """
    beide = [_KOMMENTAR_KEIN_LAUF, _KOMMENTAR_NACHGEHOLT]
    assert _codex_zustand(beide, []) == "befundlos"

    # Und in der anderen Reihenfolge ebenso: Die Liste der Kommentare ist
    # nach Alter sortiert, aber darauf soll sich der Erkenner nicht stuetzen.
    assert _codex_zustand(list(reversed(beide)), []) == "befundlos"

    # Positivkontrolle: Ohne den nachgeholten Lauf bleibt es «kein Lauf».
    assert _codex_zustand([_KOMMENTAR_KEIN_LAUF], []) == "kein Lauf"
