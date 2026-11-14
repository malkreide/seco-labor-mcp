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
