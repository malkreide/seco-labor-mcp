"""Der Prune-Fund aus CLAUDE.md, als Zusicherung statt als Prosa.

Teil 1 haelt fest: `git fetch --prune origin` raeumt einen veralteten
Tracking-Ref weg, `git fetch --prune origin main` nicht. Das ist eine Aussage
ueber git, und Prosa veraltet still. Bleibt sie unbelegt, steht der Satz da,
bis der Stop-Hook das naechste Mal «1 unpushed commit» meldet — und dann
pusht jemand einen geloeschten, bereits gemergten Zweig wieder hoch.

Diese Datei stellt die Lage her, in der der Fund gemessen wurde, und faehrt
beide Aufrufe gegen das echte git. Kein Netz: ein Bare-Repo und ein Klon
unter `tmp_path`, Host-Konfiguration ausgeschaltet.

WARUM DIE LOESCHUNG IM BARE-REPO PASSIEREN MUSS
-----------------------------------------------
Die erste Nachstellung am 14.11.2026 zeigte das Gegenteil, und zwar aus einem
Fehler der Probe: Sie loeschte den Remote-Zweig mit `git push origin --delete`
aus demselben Klon. Das nimmt den Tracking-Ref als Nebenwirkung gleich mit,
und gemessen wurde danach ein Ref, der schon vor dem Fetch weg war — beide
Aufrufe sahen gleich gut aus, und der Befund schien widerlegt.

GitHub loescht den Zweig serverseitig. `git update-ref -d` im Bare-Repo
stellt genau das her, und `test_die_probe_stellt_die_lage_wirklich_her` haelt
die Bedingung fest. Ohne diese Kontrolle waere die Datei wieder die Probe,
die nur bestaetigen kann.

WAS HIER NICHT GEPRUEFT WIRD
----------------------------
Der Stop-Hook selbst. Er liegt ausserhalb des Repos (`~/.claude/`), und was
er rechnet, ist hier nur insofern von Belang, als die Zahl `1` aus dem
Abstand zwischen veraltetem Ref und Merge-Commit entsteht — das prueft
`test_prune_mit_refspec_laesst_den_ref_stehen` mit.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_CLAUDE_MD = _ROOT / "CLAUDE.md"

_ZWEIG = "claude/testzweig"
_REF = f"refs/remotes/origin/{_ZWEIG}"

# Der Aufruf, der laut CLAUDE.md aufraeumt — und der, der es nicht tut.
_OHNE_REFSPEC = "git fetch --prune origin"
_MIT_REFSPEC = "git fetch --prune origin main"

_UMGEBUNG = {
    # Host-Konfiguration draussen halten, damit die Probe nicht vom Profil
    # des Laufzeit-Kontos abhaengt. Welcher Schluessel sie kippen koennte, ist
    # offen; der naheliegende tut es nachweislich nicht — siehe
    # `test_fetch_prune_true_ersetzt_den_richtigen_aufruf_nicht`.
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_AUTHOR_NAME": "Probe",
    "GIT_AUTHOR_EMAIL": "probe@example.invalid",
    "GIT_COMMITTER_NAME": "Probe",
    "GIT_COMMITTER_EMAIL": "probe@example.invalid",
    "GIT_TERMINAL_PROMPT": "0",
}


def _git(*args: str, cwd: pathlib.Path) -> str:
    """git aufrufen und bei Fehlschlag mit dem Befehl im Text scheitern."""
    fertig = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", **_UMGEBUNG},
        capture_output=True,
        text=True,
        check=False,
    )
    assert fertig.returncode == 0, (
        f"`git {' '.join(args)}` scheiterte in {cwd} mit {fertig.returncode}:\n"
        f"{fertig.stdout}{fertig.stderr}"
    )
    return fertig.stdout.strip()


def _ref_existiert(klon: pathlib.Path) -> bool:
    return (
        subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", _REF],
            cwd=klon,
            env={"PATH": "/usr/bin:/bin:/usr/local/bin", **_UMGEBUNG},
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def _lage_nach_dem_merge(tmp_path: pathlib.Path) -> pathlib.Path:
    """Ein Klon in genau der Lage, die GitHub beim Merge hinterlaesst.

    Zweig gemergt, serverseitig geloescht, lokaler Zweig auf dem
    Merge-Commit, Tracking-Ref noch auf dem gemergten Head.
    """
    fernab = tmp_path / "fernab.git"
    klon = tmp_path / "klon"
    _git("init", "--quiet", "--bare", str(fernab), cwd=tmp_path)
    _git("init", "--quiet", "-b", "main", str(klon), cwd=tmp_path)

    _git("commit", "--quiet", "--allow-empty", "-m", "Basis", cwd=klon)
    _git("remote", "add", "origin", str(fernab), cwd=klon)
    _git("push", "--quiet", "origin", "main", cwd=klon)

    _git("checkout", "--quiet", "-b", _ZWEIG, cwd=klon)
    _git("commit", "--quiet", "--allow-empty", "-m", "Arbeit", cwd=klon)
    _git("push", "--quiet", "-u", "origin", _ZWEIG, cwd=klon)

    _git("checkout", "--quiet", "main", cwd=klon)
    _git("merge", "--quiet", "--no-ff", _ZWEIG, "-m", "Merge", cwd=klon)
    _git("push", "--quiet", "origin", "main", cwd=klon)

    # Serverseitig loeschen — NICHT per `git push origin --delete` aus diesem
    # Klon. Siehe Modul-Docstring: das raeumte den Tracking-Ref gleich mit.
    _git("update-ref", "-d", f"refs/heads/{_ZWEIG}", cwd=fernab)

    # Der lokale Zweig steht nach dem Merge auf dem Merge-Commit.
    _git("checkout", "--quiet", _ZWEIG, cwd=klon)
    _git("reset", "--quiet", "--hard", "main", cwd=klon)
    return klon


def _kode_stellen(text: str) -> list[str]:
    """Alle Inline-Kode-Spannen des Dokuments, entrandet.

    Gesucht wird der Befehl als Kode, nicht als Zeichenfolge irgendwo im
    Fliesstext: `git fetch --prune origin main` steht in CLAUDE.md als
    Gegenbeispiel, und ein Test, der bloss zaehlt, koennte beide nicht
    unterscheiden.
    """
    return [stelle.strip() for stelle in re.findall(r"`([^`\n]+)`", text)]


# Die beiden Zeilenbeschriftungen und die beiden Spaltenkoepfe der Tabelle in
# CLAUDE.md. Sie stehen hier als Werte, weil der Test sie zum Wiederfinden
# braucht — nicht als zweite Quelle fuer das Verhalten: das misst er selbst.
_ZEILEN = {"ohne `fetch.prune`": False, "`fetch.prune = true`": True}
_SPALTEN = {"`git fetch origin main`": True, "`git fetch origin`": False}

# Das Vokabular der Zellen. Mehr Woerter gibt es nicht; ein unbekanntes ist ein
# Fehlschlag mit Hinweis, kein stilles Durchwinken.
_ZELLEN = {"Ref bleibt": True, "Ref weg": False}


def _ref_ueberlebt(arbeitsplatz: pathlib.Path, *, konfig: bool, refspec: bool) -> bool:
    """Einmal die Lage herstellen, einmal fetchen, nachsehen, ob der Ref steht.

    `konfig` setzt `fetch.prune = true` im Klon, `refspec` haengt `main` an den
    Aufruf. Der Schalter `--prune` steht bewusst NICHT dabei: Gemessen wird die
    Tabelle, und die vergleicht den gewoehnlichen Fetch mit und ohne
    Konfiguration.
    """
    klon = _lage_nach_dem_merge(arbeitsplatz)
    if konfig:
        _git("config", "fetch.prune", "true", cwd=klon)
    _git("fetch", "origin", *(["main"] if refspec else []), cwd=klon)
    return _ref_existiert(klon)


def _tabelle() -> dict[tuple[str, str], str]:
    """Die vier Zellen aus CLAUDE.md, als {(Zeile, Spalte): Zellentext}.

    Gesucht wird ueber die Beschriftungen, nicht ueber Zeilennummern: Der
    Absatz darf sich verschieben. Was er nicht darf, ist die Beschriftungen
    oder das Zellen-Vokabular aendern, ohne dass hier jemand hinsieht — und
    genau das ist der Preis dafuer, dass die Tabelle gehalten wird.
    """
    zeilen = [
        [zelle.strip() for zelle in roh.strip().strip("|").split("|")]
        for roh in _CLAUDE_MD.read_text(encoding="utf-8").splitlines()
        if roh.lstrip().startswith("|")
    ]

    kopf = [z for z in zeilen if set(_SPALTEN) <= set(z)]
    assert len(kopf) == 1, (
        f"Kopfzeile der Tabelle nicht eindeutig gefunden ({len(kopf)} Treffer). "
        f"Erwartet sind die Spalten {sorted(_SPALTEN)} in einer Zeile."
    )
    spalte_bei = {name: kopf[0].index(name) for name in _SPALTEN}

    gelesen: dict[tuple[str, str], str] = {}
    for beschriftung in _ZEILEN:
        treffer = [z for z in zeilen if z and z[0] == beschriftung]
        assert len(treffer) == 1, (
            f"Zeile «{beschriftung}» nicht eindeutig gefunden "
            f"({len(treffer)} Treffer) — Tabelle in CLAUDE.md umgebaut?"
        )
        for spalte, stelle in spalte_bei.items():
            gelesen[(beschriftung, spalte)] = treffer[0][stelle]
    return gelesen


def test_git_steht_zur_verfuegung() -> None:
    """Positivkontrolle: Ohne git messen die Zusicherungen unten nichts.

    Bewusst ein Fehlschlag und kein Skip — ein uebersprungener Test meldet
    nichts, und dieses Repo setzt git ohnehin voraus.
    """
    assert shutil.which("git"), "git fehlt — dieser Test misst nichts."


def test_die_probe_stellt_die_lage_wirklich_her(tmp_path: pathlib.Path) -> None:
    """Die Kontrolle, die der ersten Nachstellung fehlte.

    Vor jedem Fetch muss zweierlei gelten, sonst pruefen die beiden Tests
    darunter einen Ref, der schon weg ist, und sehen beide Aufrufe als gut:
    der Remote kennt den Zweig nicht mehr, der Tracking-Ref steht aber noch.
    """
    klon = _lage_nach_dem_merge(tmp_path)

    zweige = _git("ls-remote", "--heads", "origin", cwd=klon)
    assert _ZWEIG not in zweige, f"Remote kennt {_ZWEIG} noch:\n{zweige}"

    assert _ref_existiert(klon), (
        f"{_REF} ist schon vor dem Fetch weg — die Probe kann den Unterschied "
        "zwischen den beiden Aufrufen nicht mehr messen."
    )
    assert _git("rev-parse", _REF, cwd=klon) == _git("rev-parse", f"{_ZWEIG}^2", cwd=klon), (
        f"{_REF} zeigt nicht auf den gemergten Head — dann ist die "
        "Voraus-Rechnung unten eine andere als die des Hooks."
    )


def test_prune_mit_refspec_laesst_den_ref_stehen(tmp_path: pathlib.Path) -> None:
    """Der Fund: Mit Refspec bleibt der Ref liegen — und die Zahl liest `1`.

    Die `1` ist nicht Beiwerk, sondern die Meldung des Stop-Hooks: Der
    Merge-Commit liegt genau einen Schritt ueber dem gemergten Head, auf dem
    der veraltete Ref noch steht.
    """
    klon = _lage_nach_dem_merge(tmp_path)
    _git(*_MIT_REFSPEC.split()[1:], cwd=klon)

    assert _ref_existiert(klon), (
        f"`{_MIT_REFSPEC}` hat {_REF} entfernt. Dann stimmt der Absatz in "
        "CLAUDE.md nicht mehr und gehoert korrigiert, nicht dieser Test."
    )
    voraus = _git("rev-list", "--count", f"{_REF}..HEAD", cwd=klon)
    assert voraus == "1", f"Erwartet war die Zahl des Hooks (1), gelesen: {voraus}"


def test_prune_ohne_refspec_raeumt_den_ref_weg(tmp_path: pathlib.Path) -> None:
    """Und die Gegenseite: ohne Refspec ist der Ref weg, der Upstream `[gone]`."""
    klon = _lage_nach_dem_merge(tmp_path)
    _git(*_OHNE_REFSPEC.split()[1:], cwd=klon)

    assert not _ref_existiert(klon), (
        f"`{_OHNE_REFSPEC}` hat {_REF} stehen gelassen — dann taugt der in "
        "CLAUDE.md empfohlene Handgriff nicht."
    )
    kurz = _git("status", "-sb", cwd=klon).splitlines()[0]
    assert "[gone]" in kurz, f"Upstream nicht als [gone] markiert: {kurz}"


def test_die_anweisung_empfiehlt_den_aufruf_ohne_refspec() -> None:
    """CLAUDE.md muss den Aufruf fuehren, der aufraeumt — als Kode, nicht als Prosa.

    Verboten ist damit nichts: Der Aufruf mit Refspec darf als Gegenbeispiel
    dastehen und tut es. Verlangt ist, dass der wirksame daneben steht.
    """
    assert _CLAUDE_MD.is_file(), "CLAUDE.md fehlt — der Test misst nichts."
    stellen = _kode_stellen(_CLAUDE_MD.read_text(encoding="utf-8"))
    assert _OHNE_REFSPEC in stellen, (
        f"CLAUDE.md nennt `{_OHNE_REFSPEC}` nicht mehr als Kode. Steht dort nur "
        f"noch `{_MIT_REFSPEC}`, empfiehlt die Anweisung den Aufruf, der den "
        "veralteten Ref liegen laesst."
    )


def test_der_erkenner_unterscheidet_die_beiden_aufrufe() -> None:
    """Gegenprobe zum Erkenner: Ein Muster, das beide gleich liest, waere blind."""
    nur_mit = _kode_stellen(f"Aufraeumen mit `{_MIT_REFSPEC}`, dann weiter.")
    assert _OHNE_REFSPEC not in nur_mit, (
        "Der Erkenner haelt den Aufruf mit Refspec fuer den ohne — dann ist "
        "die Zusicherung darueber immer gruen."
    )

    nur_ohne = _kode_stellen(f"Aufraeumen mit `{_OHNE_REFSPEC}`, dann weiter.")
    assert _OHNE_REFSPEC in nur_ohne, "Der Erkenner findet den eigenen Aufruf nicht."


def test_fetch_prune_true_ersetzt_den_richtigen_aufruf_nicht(tmp_path: pathlib.Path) -> None:
    """Gemessen: `fetch.prune = true` rettet den Aufruf mit Refspec nicht.

    Der naheliegende Schluss aus dem Fund waere, die Konfiguration zu setzen
    und den Aufruf nicht mehr zu beachten. Er traegt nicht: Mit
    `fetch.prune = true` im Klon bleibt der veraltete Ref nach
    `git fetch --prune origin main` genauso liegen. Die Option erweitert den
    Geltungsbereich des Prunes also nicht ueber die genannte Refspec hinaus.

    Diese Zusicherung ist zugleich die Korrektur einer falschen Vermutung: Im
    ersten Entwurf stand als Begruendung fuer die ausgeschaltete
    Host-Konfiguration, ein `fetch.prune = true` wuerde den Unterschied
    zudecken. Die Probe dazu zeigte das Gegenteil.
    """
    klon = _lage_nach_dem_merge(tmp_path)
    _git("config", "fetch.prune", "true", cwd=klon)
    _git(*_MIT_REFSPEC.split()[1:], cwd=klon)

    assert _ref_existiert(klon), (
        f"Mit `fetch.prune = true` hat `{_MIT_REFSPEC}` {_REF} entfernt. Dann "
        "waere die Konfiguration ein Ausweg und der Absatz in CLAUDE.md "
        "unvollstaendig."
    )


def test_fetch_prune_true_raeumt_den_aufruf_ohne_refspec_auf(tmp_path: pathlib.Path) -> None:
    """Die andere Haelfte der Tabelle: nutzlos ist die Option naemlich nicht.

    Ohne sie laesst ein gewoehnliches `git fetch origin` den Ref stehen; mit
    ihr raeumt derselbe Aufruf ihn weg, ohne dass `--prune` dabeistehen muss.
    Die Option entscheidet also ueber das *Ob*, die Refspec ueber das *Was* —
    und nur diese zweite Grenze ist die Falle.

    Ohne diese Zusicherung liesse der Test daneben sich auch so lesen, als
    bewirke `fetch.prune` ueberhaupt nichts. Das waere die falsche Lehre.
    """
    klon = _lage_nach_dem_merge(tmp_path)
    _git("config", "fetch.prune", "true", cwd=klon)
    _git("fetch", "origin", cwd=klon)

    assert not _ref_existiert(klon), (
        "Mit `fetch.prune = true` hat `git fetch origin` {REF} stehen lassen. "
        "Dann stimmt die Tabelle in CLAUDE.md nicht."
    ).replace("{REF}", _REF)


def test_die_tabelle_stimmt_mit_dem_gemessenen_verhalten_ueberein(
    tmp_path: pathlib.Path,
) -> None:
    """Alle vier Zellen gegen das echte git, nicht nur die beiden wichtigen.

    Die beiden Zusicherungen darueber halten die untere Haelfte der Tabelle,
    weil sie der Fund ist. Die obere stand bis hierher ungeprueft da — und eine
    Zelle, die niemand nachrechnet, ist genau die Prosa, gegen die diese Datei
    gebaut wurde.

    Der Preis ist benannt: Wer die Tabelle umformatiert oder ihr Vokabular
    aendert, macht diesen Test rot. Das ist gewollt; die Meldung sagt dann,
    welche Zelle womit nicht zusammengeht.
    """
    gelesen = _tabelle()
    abweichungen: list[str] = []

    for nummer, ((zeile, spalte), zelle) in enumerate(sorted(gelesen.items())):
        assert zelle in _ZELLEN, (
            f"Zelle ({zeile} | {spalte}) sagt «{zelle}». Bekannt sind nur "
            f"{sorted(_ZELLEN)} — ein neues Wort braucht hier eine Entsprechung."
        )
        arbeitsplatz = tmp_path / f"zelle-{nummer}"
        arbeitsplatz.mkdir()
        gemessen = _ref_ueberlebt(
            arbeitsplatz,
            konfig=_ZEILEN[zeile],
            refspec=_SPALTEN[spalte],
        )
        if gemessen is not _ZELLEN[zelle]:
            abweichungen.append(
                f"({zeile} | {spalte}): CLAUDE.md sagt «{zelle}», gemessen "
                f"wurde «{'Ref bleibt' if gemessen else 'Ref weg'}»"
            )

    assert not abweichungen, "Tabelle und git gehen auseinander:\n  " + "\n  ".join(abweichungen)


def test_push_delete_raeumt_den_tracking_ref_gleich_mit(tmp_path: pathlib.Path) -> None:
    """Die Nebenwirkung, an der die erste Nachstellung scheiterte.

    `git push origin --delete <zweig>` loescht nicht nur den Zweig im Remote,
    sondern entfernt im selben Zug den lokalen Tracking-Ref. Eine Probe, die
    die Lage so herstellt, hat damit genau das Beobachtungsobjekt beseitigt —
    danach sieht jeder Fetch gleich gut aus.

    Deshalb baut `_lage_nach_dem_merge` serverseitig ab (`git update-ref -d` im
    Bare-Repo). Diese Zusicherung haelt den Grund dafuer fest, statt ihn nur im
    Docstring zu behaupten; CLAUDE.md nennt denselben Fall im Abschnitt «Tests».
    """
    fernab = tmp_path / "fernab.git"
    klon = tmp_path / "klon"
    _git("init", "--quiet", "--bare", str(fernab), cwd=tmp_path)
    _git("init", "--quiet", "-b", "main", str(klon), cwd=tmp_path)
    _git("commit", "--quiet", "--allow-empty", "-m", "Basis", cwd=klon)
    _git("remote", "add", "origin", str(fernab), cwd=klon)
    _git("push", "--quiet", "origin", "main", cwd=klon)
    _git("checkout", "--quiet", "-b", _ZWEIG, cwd=klon)
    _git("commit", "--quiet", "--allow-empty", "-m", "Arbeit", cwd=klon)
    _git("push", "--quiet", "-u", "origin", _ZWEIG, cwd=klon)
    _git("checkout", "--quiet", "main", cwd=klon)

    assert _ref_existiert(klon), "Positivkontrolle: vor der Loeschung muss der Ref stehen."

    _git("push", "--quiet", "origin", "--delete", _ZWEIG, cwd=klon)

    assert not _ref_existiert(klon), (
        f"`git push origin --delete` hat {_REF} stehen gelassen. Dann waere die "
        "Begruendung fuer die serverseitige Loeschung in `_lage_nach_dem_merge` "
        "hinfaellig — und der Absatz in CLAUDE.md zu korrigieren."
    )


def _lage_nach_dem_merge_ohne_loeschung(arbeitsplatz: pathlib.Path) -> pathlib.Path:
    """Wie `_lage_nach_dem_merge`, nur loescht der Remote den Zweig NICHT.

    Das ist der Fall vom 22.11.2026: GitHub liess den Zweig beim Merge stehen,
    und der lokale Zweig wurde danach auf `main` vorgezogen. Der Tracking-Ref
    ist hier also gueltig und nicht veraltet — der Unterschied, auf den es im
    Absatz ankommt.
    """
    fernab = arbeitsplatz / "fernab.git"
    klon = arbeitsplatz / "klon"
    _git("init", "--quiet", "--bare", str(fernab), cwd=arbeitsplatz)
    _git("init", "--quiet", "-b", "main", str(klon), cwd=arbeitsplatz)

    _git("commit", "--quiet", "--allow-empty", "-m", "Basis", cwd=klon)
    _git("remote", "add", "origin", str(fernab), cwd=klon)
    _git("push", "--quiet", "origin", "main", cwd=klon)

    _git("checkout", "--quiet", "-b", _ZWEIG, cwd=klon)
    _git("commit", "--quiet", "--allow-empty", "-m", "Arbeit", cwd=klon)
    _git("push", "--quiet", "-u", "origin", _ZWEIG, cwd=klon)

    _git("checkout", "--quiet", "main", cwd=klon)
    _git("merge", "--quiet", "--no-ff", _ZWEIG, "-m", "Merge", cwd=klon)
    _git("push", "--quiet", "origin", "main", cwd=klon)

    # Kein `update-ref -d`: Der Zweig bleibt im Remote stehen.
    _git("checkout", "--quiet", _ZWEIG, cwd=klon)
    _git("merge", "--quiet", "--ff-only", "main", cwd=klon)
    _git("fetch", "--prune", "origin", cwd=klon)
    return klon


def test_der_vorsprung_kann_der_merge_commit_selbst_sein(tmp_path: pathlib.Path) -> None:
    """Die vierte Spielart der Hook-Meldung: Zahl richtig, Handlung falsch.

    Der Tracking-Ref ist hier gueltig — der Remote fuehrt den Zweig weiterhin —,
    und der lokale Zweig ist wirklich einen Commit voraus. Dieser eine Commit
    ist aber der Merge-Commit, der bereits in `main` liegt.

    Gehalten werden die drei Zahlen, an denen der Absatz die Faelle trennt: der
    Zweig existiert im Remote, `origin/<zweig>..HEAD` liest `1`, und
    `origin/main...HEAD` liest `0 0`. Die eine Zeile, die den Fall aufloest, ist
    `merge-base --is-ancestor HEAD origin/main`.
    """
    klon = _lage_nach_dem_merge_ohne_loeschung(tmp_path)

    assert _ZWEIG in _git("ls-remote", "--heads", "origin", cwd=klon), (
        "Positivkontrolle: Hier soll der Remote den Zweig gerade NICHT "
        "losgeworden sein — sonst misst dieser Test den veralteten Ref von oben."
    )
    assert _ref_existiert(klon), "Tracking-Ref fehlt — die Lage ist nicht hergestellt."

    voraus = _git("rev-list", "--count", f"{_REF}..HEAD", cwd=klon)
    assert voraus == "1", f"Erwartet war die Zahl des Hooks (1), gelesen: {voraus}"

    gegen_main = _git("rev-list", "--left-right", "--count", "origin/main...HEAD", cwd=klon)
    assert gegen_main.split() == ["0", "0"], (
        f"Gegen `main` gerechnet muesste HEAD deckungsgleich sein, gelesen: {gegen_main}"
    )

    _git("merge-base", "--is-ancestor", "HEAD", "origin/main", cwd=klon)
