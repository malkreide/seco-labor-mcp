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


# ----------------------------------------------------------------------------
# Der FETCH_HEAD-Fund vom 22.11.2026
#
# Dieselbe Familie wie oben, eine Ebene weiter: Nicht mehr, ob der Prune den
# Ref raeumt, sondern ob der Merge danach `main` ueberhaupt holt. Der Aufruf
# `git fetch --prune origin && git merge --ff-only FETCH_HEAD` meldet
# «Already up to date.» mit Rueckgabe 0 und laesst den Klon einen Commit
# hinter `main` — also in genau dem Zustand, vor dem der erste Abschnitt von
# CLAUDE.md warnt.
# ----------------------------------------------------------------------------

_EMPFOHLEN = "git fetch --prune origin && git merge --ff-only origin/main"


def _kodeblock_zeilen(text: str) -> list[str]:
    """Die Zeilen aus eingezaeunten Kodebloecken, entrandet.

    `_kode_stellen` findet nur Inline-Spannen. Der empfohlene Aufruf steht in
    CLAUDE.md in einem ```bash-Block, und ein Test, der ihn im Fliesstext
    gelten liesse, waere wieder die Prosa-Pruefung, gegen die diese Datei
    gebaut ist.
    """
    zeilen: list[str] = []
    drin = False
    for roh in text.splitlines():
        if roh.lstrip().startswith("```"):
            drin = not drin
            continue
        if drin:
            zeilen.append(roh.strip())
    return zeilen


def _lage_mit_vorgezogenem_main(
    arbeitsplatz: pathlib.Path, *, zweig_loeschen: bool
) -> pathlib.Path:
    """Ein Klon, der einen Commit hinter `main` liegt und nichts davon weiss.

    Anders als `_lage_nach_dem_merge`: Dort steht der lokale Zweig schon auf
    dem Merge-Commit. Hier wird im Remote gemergt, *nachdem* der Klon gezogen
    wurde — die Lage also, die man vorfindet, wenn man nach dem Merge des
    eigenen PR den Klon nachziehen will.

    Dafuer braucht es zwei Arbeitskopien: `saat` schiebt den Merge in den
    Remote, `klon` ist der Gemessene. Mit nur einer Kopie waere `origin/main`
    im Gemessenen schon durch den eigenen Push aktuell, und die Messung liefe
    an der Sache vorbei.

    `zweig_loeschen` entscheidet, ob GitHub den Zweig beim Merge entfernt hat.
    Davon haengt ab, ob FETCH_HEAD ueberhaupt eine `for-merge`-Zeile traegt —
    und das ist der eine der beiden Gruende, aus denen der Merge ins Leere
    laeuft.
    """
    fernab = arbeitsplatz / "fernab.git"
    saat = arbeitsplatz / "saat"
    klon = arbeitsplatz / "klon"

    _git("init", "--quiet", "--bare", str(fernab), cwd=arbeitsplatz)
    _git("init", "--quiet", "-b", "main", str(saat), cwd=arbeitsplatz)
    _git("commit", "--quiet", "--allow-empty", "-m", "Basis", cwd=saat)
    _git("remote", "add", "origin", str(fernab), cwd=saat)
    _git("push", "--quiet", "origin", "main", cwd=saat)
    _git("checkout", "--quiet", "-b", _ZWEIG, cwd=saat)
    _git("commit", "--quiet", "--allow-empty", "-m", "Arbeit", cwd=saat)
    _git("push", "--quiet", "origin", _ZWEIG, cwd=saat)

    # Erst jetzt klonen: der Klon kennt `main` noch vor dem Merge.
    _git("clone", "--quiet", str(fernab), str(klon), cwd=arbeitsplatz)
    _git("checkout", "--quiet", _ZWEIG, cwd=klon)

    _git("checkout", "--quiet", "main", cwd=saat)
    _git("merge", "--quiet", "--no-ff", _ZWEIG, "-m", "Merge", cwd=saat)
    _git("push", "--quiet", "origin", "main", cwd=saat)
    if zweig_loeschen:
        _git("update-ref", "-d", f"refs/heads/{_ZWEIG}", cwd=fernab)
    return klon


def _hinter_main(klon: pathlib.Path) -> str:
    return _git("rev-list", "--count", "HEAD..origin/main", cwd=klon)


def _for_merge_zeilen(klon: pathlib.Path) -> list[str]:
    datei = klon / ".git" / "FETCH_HEAD"
    return [
        zeile
        for zeile in datei.read_text(encoding="utf-8").splitlines()
        if zeile.strip() and "not-for-merge" not in zeile
    ]


def test_die_probe_liegt_wirklich_hinter_main(tmp_path: pathlib.Path) -> None:
    """Die Kontrolle zur Lage: Ohne Rueckstand misst alles darunter nichts.

    Ein Klon, der schon auf `main` steht, liest nach jedem Aufruf «0 hinter
    main» — und beide Haelften der Tabelle sahen gleich gut aus. Deshalb hier
    zuerst: Nach einem Fetch mit Refspec, der nur `origin/main` nachfuehrt und
    HEAD nicht anfasst, muss der Rueckstand genau `1` sein.
    """
    for nummer, zweig_loeschen in enumerate((True, False)):
        arbeitsplatz = tmp_path / f"lage-{nummer}"
        arbeitsplatz.mkdir()
        klon = _lage_mit_vorgezogenem_main(arbeitsplatz, zweig_loeschen=zweig_loeschen)
        _git("fetch", "origin", "main", cwd=klon)
        assert _hinter_main(klon) == "1", (
            f"Mit zweig_loeschen={zweig_loeschen} liegt der Klon "
            f"{_hinter_main(klon)} Commits hinter `main`, erwartet war 1 — die "
            "Probe stellt den Rueckstand nicht her."
        )


def test_merge_fetch_head_ohne_refspec_bringt_main_nicht(tmp_path: pathlib.Path) -> None:
    """Der Fund, beide Zeilen: ohne Refspec holt der Merge `main` nicht.

    Gemessen wird nicht die Meldung, sondern der Rueckstand danach. Dass der
    Befehl dabei mit 0 endet, ist der gefaehrliche Teil und steht als eigene
    Zusicherung da: `_git` wuerde bei einem Fehlschlag selbst scheitern, und
    ein Test, der nur den Rueckstand liest, koennte «lief nicht» nicht von
    «lief und tat nichts» unterscheiden.
    """
    for nummer, zweig_loeschen in enumerate((True, False)):
        arbeitsplatz = tmp_path / f"ohne-{nummer}"
        arbeitsplatz.mkdir()
        klon = _lage_mit_vorgezogenem_main(arbeitsplatz, zweig_loeschen=zweig_loeschen)

        _git("fetch", "--prune", "origin", cwd=klon)
        meldung = _git("merge", "--ff-only", "FETCH_HEAD", cwd=klon)

        assert "Already up to date" in meldung, (
            f"Mit zweig_loeschen={zweig_loeschen} meldete der Merge «{meldung}» "
            "statt «Already up to date.» — dann stimmt die Tabelle in "
            "CLAUDE.md nicht mehr."
        )
        assert _hinter_main(klon) == "1", (
            f"Mit zweig_loeschen={zweig_loeschen} hat "
            "`git merge --ff-only FETCH_HEAD` nach einem Fetch ohne Refspec "
            "`main` doch geholt. Dann ist der Absatz in CLAUDE.md zu "
            "korrigieren, nicht dieser Test."
        )


def test_merge_fetch_head_mit_refspec_bringt_main(tmp_path: pathlib.Path) -> None:
    """Die andere Haelfte — und zugleich die Kontrolle zur Haelfte darueber.

    Ohne diese Zusicherung koennte der Test daneben auch dann gruen bleiben,
    wenn die Probe den Merge grundsaetzlich nicht zum Laufen bringt. Hier
    rueckt derselbe Merge in derselben Lage wirklich vor.
    """
    for nummer, zweig_loeschen in enumerate((True, False)):
        arbeitsplatz = tmp_path / f"mit-{nummer}"
        arbeitsplatz.mkdir()
        klon = _lage_mit_vorgezogenem_main(arbeitsplatz, zweig_loeschen=zweig_loeschen)

        _git("fetch", "--prune", "origin", "main", cwd=klon)
        meldung = _git("merge", "--ff-only", "FETCH_HEAD", cwd=klon)

        assert "Updating" in meldung, (
            f"Mit zweig_loeschen={zweig_loeschen} rueckte der Merge nicht vor "
            f"(«{meldung}») — dann misst der Test darueber nicht den Aufruf, "
            "sondern eine Probe, die den Merge ueberhaupt nicht ans Laufen "
            "bringt."
        )
        assert _hinter_main(klon) == "0", (
            f"Mit zweig_loeschen={zweig_loeschen} liegt der Klon nach dem "
            "Merge mit Refspec weiter hinter `main`."
        )


def test_die_for_merge_zeilen_erklaeren_beide_faelle(tmp_path: pathlib.Path) -> None:
    """Der Mechanismus hinter den zwei Zeilen, nicht bloss ihr Ausgang.

    CLAUDE.md nennt zwei verschiedene Gruende fuer dieselbe Meldung. Diese
    Zusicherung haelt sie auseinander: Beim geloeschten Zweig traegt FETCH_HEAD
    keine `for-merge`-Zeile, beim vorhandenen genau eine — und die zeigt auf
    den Zweig, nicht auf `main`. Ohne diese Trennung liesse sich der Absatz
    auch mit nur einem der beiden Gruende lesen.
    """
    arbeitsplatz = tmp_path / "geloescht"
    arbeitsplatz.mkdir()
    klon = _lage_mit_vorgezogenem_main(arbeitsplatz, zweig_loeschen=True)
    _git("fetch", "--prune", "origin", cwd=klon)
    assert _for_merge_zeilen(klon) == [], (
        "Beim geloeschten Zweig traegt FETCH_HEAD doch eine `for-merge`-Zeile: "
        f"{_for_merge_zeilen(klon)}"
    )

    arbeitsplatz = tmp_path / "vorhanden"
    arbeitsplatz.mkdir()
    klon = _lage_mit_vorgezogenem_main(arbeitsplatz, zweig_loeschen=False)
    _git("fetch", "--prune", "origin", cwd=klon)
    zeilen = _for_merge_zeilen(klon)
    assert len(zeilen) == 1, f"Erwartet war genau eine `for-merge`-Zeile, gelesen: {zeilen}"
    assert zeilen[0].split()[0] == _git("rev-parse", _REF, cwd=klon), (
        "Die `for-merge`-Zeile zeigt nicht auf den Zweig — dann ist der in "
        f"CLAUDE.md genannte Grund ein anderer. Gelesen: {zeilen[0]}"
    )


def test_zaehlen_gegen_fetch_head_ist_ohne_refspec_nicht_an_main_verankert(
    tmp_path: pathlib.Path,
) -> None:
    """Die zweite Regel: `HEAD..FETCH_HEAD` nimmt die erste Zeile der Datei.

    Deshalb traegt der Aufruf im ersten Abschnitt von CLAUDE.md seine Refspec.
    Gemessen wird der belastbare Fall — Zweig vorhanden, also die erste Zeile
    der Upstream des aktuellen Zweigs: Die Zahl liest `0`, waehrend `main`
    einen Commit voraus ist. Mit Refspec liest dieselbe Rechnung `1`; das ist
    hier die Kontrolle, ohne die ein stets falsch rechnender Aufbau gleich
    aussaehe.
    """
    arbeitsplatz = tmp_path / "ohne"
    arbeitsplatz.mkdir()
    klon = _lage_mit_vorgezogenem_main(arbeitsplatz, zweig_loeschen=False)
    _git("fetch", "--prune", "origin", cwd=klon)
    gezaehlt = _git("rev-list", "--count", "HEAD..FETCH_HEAD", cwd=klon)
    assert gezaehlt == "0" and _hinter_main(klon) == "1", (
        "Ohne Refspec rechnet `HEAD..FETCH_HEAD` nicht mehr am Upstream des "
        f"Zweigs vorbei: gezaehlt {gezaehlt}, hinter `main` "
        f"{_hinter_main(klon)}. Erwartet waren 0 und 1."
    )

    arbeitsplatz = tmp_path / "mit"
    arbeitsplatz.mkdir()
    klon = _lage_mit_vorgezogenem_main(arbeitsplatz, zweig_loeschen=False)
    _git("fetch", "--prune", "origin", "main", cwd=klon)
    assert _git("rev-list", "--count", "HEAD..FETCH_HEAD", cwd=klon) == "1", (
        "Mit Refspec zaehlt die Rechnung nicht gegen `main` — dann misst die "
        "Zusicherung darueber nicht die Refspec, sondern einen immer falschen "
        "Aufbau."
    )


def test_der_empfohlene_aufruf_tut_beides(tmp_path: pathlib.Path) -> None:
    """Und der Aufruf, den CLAUDE.md daraus ableitet: raeumt *und* holt.

    Die beiden Haelften sind oben je einzeln gemessen. Hier zusammen, weil
    CLAUDE.md genau diese Kombination empfiehlt und eine Empfehlung, die
    niemand nachrechnet, dieselbe Prosa ist wie die, gegen die diese Datei
    gebaut wurde.
    """
    arbeitsplatz = tmp_path / "empfohlen"
    arbeitsplatz.mkdir()
    klon = _lage_mit_vorgezogenem_main(arbeitsplatz, zweig_loeschen=True)

    _git("fetch", "--prune", "origin", cwd=klon)
    _git("merge", "--ff-only", "origin/main", cwd=klon)

    assert not _ref_existiert(klon), f"{_REF} steht noch — der Prune hat nicht gegriffen."
    assert _hinter_main(klon) == "0", (
        f"Der Klon liegt weiter {_hinter_main(klon)} Commits hinter `main` — "
        "dann holt der empfohlene Aufruf nicht, was er holen soll."
    )


def test_die_anweisung_nennt_den_empfohlenen_aufruf_als_kode() -> None:
    """Der Aufruf muss in CLAUDE.md stehen, und zwar in einem Kodeblock.

    Gegenprobe zum Erkenner gleich mit: Ein Muster, das denselben Text im
    Fliesstext gelten liesse, waere blind fuer den Fall, dass aus der
    Empfehlung eine Nebenbemerkung wird.
    """
    assert _CLAUDE_MD.is_file(), "CLAUDE.md fehlt — der Test misst nichts."
    assert _EMPFOHLEN in _kodeblock_zeilen(_CLAUDE_MD.read_text(encoding="utf-8")), (
        f"CLAUDE.md nennt `{_EMPFOHLEN}` nicht mehr als Kodeblock-Zeile. Ohne "
        "ihn empfiehlt die Anweisung entweder den Aufruf, der nicht prunt, "
        "oder den, der `main` nicht holt."
    )
    assert _EMPFOHLEN not in _kodeblock_zeilen(f"Nebenbei: {_EMPFOHLEN} genuegt."), (
        "Der Erkenner nimmt Fliesstext fuer einen Kodeblock — dann ist die "
        "Zusicherung darueber immer gruen."
    )


# ----------------------------------------------------------------------------
# Der Pipe-Fund vom 26.11.2026
#
# `git push origin --delete … 2>&1 | tail -5 && echo …` scheiterte am Proxy mit
# HTTP 403 und endete doch mit 0, weil `tail` den Status liefert. Das `&&`
# feuerte, und die Ausgabe las sich wie eine gelungene Folge. Gemessen wird die
# Tabelle, die CLAUDE.md dazu fuehrt — an einem echten, scheiternden git-Aufruf
# ohne Netz: der Loeschung eines Refs, den der Remote nicht kennt.
# ----------------------------------------------------------------------------

_PIPE_SPALTEN = ("Aufruf", "Exit")

# Beschriftung -> Shell-Gestalt des Aufrufs. Der Platzhalter {b} nimmt den
# git-Befehl auf, damit keine Zeile ihn zweimal buchstabiert.
_PIPE_FORMEN = {
    "ohne Pipe": "{b}",
    "in `tail -5` gepipet": "{b} 2>&1 | tail -5",
    "gepipet, `set -o pipefail` davor": "set -o pipefail; {b} 2>&1 | tail -5",
    "gepipet, danach `PIPESTATUS[0]` gelesen": (
        "{b} 2>&1 | tail -5 >/dev/null; exit ${PIPESTATUS[0]}"
    ),
}


def _pipe_tabelle() -> dict[str, str]:
    """Die Zeilen der Exit-Code-Tabelle als {Beschriftung: Zellentext}.

    Gesucht wird ueber die Spaltenkoepfe, wie bei der Prune-Tabelle oben.
    Sternchen fallen weg: Die Null steht im Dokument fett, weil sie die
    ueberraschende ist.
    """
    zeilen = [
        [zelle.strip() for zelle in roh.strip().strip("|").split("|")]
        for roh in _CLAUDE_MD.read_text(encoding="utf-8").splitlines()
        if roh.lstrip().startswith("|")
    ]
    kopf = [i for i, z in enumerate(zeilen) if tuple(z) == _PIPE_SPALTEN]
    assert len(kopf) == 1, (
        f"Kopfzeile {_PIPE_SPALTEN} nicht eindeutig gefunden ({len(kopf)} "
        "Treffer) — Absatz in CLAUDE.md umgebaut?"
    )
    gelesen = {}
    for z in zeilen[kopf[0] + 1 :]:
        if len(z) != 2 or set("".join(z)) <= set("-: "):
            if gelesen:
                break
            continue
        gelesen[z[0]] = z[1].replace("*", "").strip()
    assert gelesen, "Die Exit-Code-Tabelle hat keine Datenzeilen."
    return gelesen


def _bash(befehl: str, *, cwd: pathlib.Path) -> tuple[int, str]:
    fertig = subprocess.run(
        ["bash", "-c", befehl],
        cwd=cwd,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", **_UMGEBUNG},
        capture_output=True,
        text=True,
        check=False,
    )
    return fertig.returncode, (fertig.stdout + fertig.stderr).strip()


def _klon_mit_remote(arbeitsplatz: pathlib.Path) -> pathlib.Path:
    """Ein Klon mit erreichbarem Remote — fuer einen Push, der sicher scheitert."""
    fernab = arbeitsplatz / "fernab.git"
    klon = arbeitsplatz / "klon"
    _git("init", "--quiet", "--bare", str(fernab), cwd=arbeitsplatz)
    _git("init", "--quiet", "-b", "main", str(klon), cwd=arbeitsplatz)
    _git("commit", "--quiet", "--allow-empty", "-m", "Basis", cwd=klon)
    _git("remote", "add", "origin", str(fernab), cwd=klon)
    _git("push", "--quiet", "origin", "main", cwd=klon)
    return klon


def test_bash_steht_zur_verfuegung(tmp_path: pathlib.Path) -> None:
    """Positivkontrolle: Ohne bash messen die Zusicherungen unten nichts.

    Geprueft wird zugleich, dass `set -o pipefail` ueberhaupt verstanden wird —
    eine Shell ohne diese Option liesse den Unterschied verschwinden, den die
    Tabelle behauptet.
    """
    assert shutil.which("bash"), "bash fehlt — dieser Test misst nichts."
    rc, _ = _bash("set -o pipefail; false | true", cwd=tmp_path)
    assert rc != 0, "Diese Shell kennt `set -o pipefail` nicht."


def test_die_pipe_tabelle_stimmt_mit_dem_gemessenen_verhalten_ueberein(
    tmp_path: pathlib.Path,
) -> None:
    """Alle Zeilen der Exit-Code-Tabelle gegen einen echt scheiternden Aufruf.

    Die erste Zeile ist zugleich die Positivkontrolle: Scheitert der Aufruf
    ohne Pipe nicht, dann misst der Rest nichts, und die Tabelle waere auch
    ohne die Pipe-Mechanik gruen.
    """
    gelesen = _pipe_tabelle()
    assert set(gelesen) == set(_PIPE_FORMEN), (
        "Die Beschriftungen der Tabelle sind nicht die erwarteten.\n"
        f"  im Dokument: {sorted(gelesen)}\n  erwartet:    {sorted(_PIPE_FORMEN)}"
    )

    befehl = "git push origin --delete gibtesnicht"
    abweichungen: list[str] = []
    letzte_zeilen: set[str] = set()

    for nummer, (beschriftung, form) in enumerate(sorted(_PIPE_FORMEN.items())):
        arbeitsplatz = tmp_path / f"pipe-{nummer}"
        arbeitsplatz.mkdir()
        klon = _klon_mit_remote(arbeitsplatz)
        rc, ausgabe = _bash(form.replace("{b}", befehl), cwd=klon)
        if ausgabe and "PIPESTATUS" not in form:
            # Der Pfad des Wegwerf-Remotes steht in der Meldung und ist je
            # Arbeitsplatz anders; verglichen wird die Meldung, nicht der Pfad.
            letzte_zeilen.add(ausgabe.splitlines()[-1].split(" to '")[0])
        erwartet = gelesen[beschriftung]
        if str(rc) != erwartet:
            abweichungen.append(f"«{beschriftung}»: CLAUDE.md sagt Exit {erwartet}, gemessen {rc}")

    assert not abweichungen, "Tabelle und Shell gehen auseinander:\n  " + "\n  ".join(abweichungen)
    assert gelesen["ohne Pipe"] == "1", (
        "Die Positivkontrolle der Tabelle sagt, der Aufruf ohne Pipe scheitere "
        "nicht — dann ist der ganze Absatz gegenstandslos."
    )
    # Die PIPESTATUS-Variante leitet die Ausgabe nach /dev/null und endet mit
    # ihrer eigenen Zeile; sie bleibt hier draussen. Der Absatz sagt das auch
    # so — zuerst stand dort «in allen Faellen», und dieser Test hat es
    # widerlegt.
    assert len(letzte_zeilen) == 1, (
        "Die letzte Ausgabezeile ist nicht in allen durchgelassenen Faellen "
        f"dieselbe; der Satz dazu in CLAUDE.md stimmt dann nicht: "
        f"{sorted(letzte_zeilen)}"
    )
    assert len(_PIPE_FORMEN) - 1 == 3, (
        "Es sind nicht mehr drei Aufrufe, die die Ausgabe durchlassen — dann "
        "nennt der Absatz die falsche Zahl."
    )


def test_eine_loeschung_ohne_remote_ref_meldet_sich_deutlich(
    tmp_path: pathlib.Path,
) -> None:
    """Die widerlegte Erklaerung, als Zusicherung festgehalten.

    Zuerst stand im Absatz die Vermutung, eine fehlgeschlagene
    Ref-Advertisement lasse jede Loeschung wie erledigt aussehen — daher
    «Everything up-to-date». Die Probe zeigt das Gegenteil: Eine Loeschung, die
    der Remote nicht kennt, sagt es ausdruecklich und endet mit 1. Damit ist
    die Vermutung vom Tisch und die Zeile bleibt unerklaert; CLAUDE.md sagt
    das auch so.
    """
    klon = _klon_mit_remote(tmp_path)
    rc, ausgabe = _bash("git push origin --delete gibtesnicht", cwd=klon)
    assert rc == 1, f"Erwartet war Exit 1, gemessen {rc}:\n{ausgabe}"
    assert "remote ref does not exist" in ausgabe, (
        "Die Loeschung eines unbekannten Refs meldet das nicht mehr "
        f"ausdruecklich. Dann waere die widerlegte Erklaerung neu zu pruefen:\n{ausgabe}"
    )
    assert "Everything up-to-date" not in ausgabe, (
        "Die Loeschung eines unbekannten Refs meldet «Everything up-to-date» — "
        "dann traegt die Erklaerung doch, und der Absatz in CLAUDE.md ist zu "
        "korrigieren."
    )
