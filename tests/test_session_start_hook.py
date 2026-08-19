"""Der SessionStart-Hook meldet Rueckstand — und blockiert dabei nie.

Der Hook loest ein Problem, das nicht im Diff steht: Ein veralteter Klon hat
am 3.8.2026 zweimal eine rote CI erzeugt, deren Ursache in Dateien lag, die
niemand angefasst hatte. `CLAUDE.md` verlangt die Pruefung von Hand; von Hand
heisst, wenn man daran denkt.

Die wichtigere Zusicherung ist aber nicht die Meldung, sondern ihr
Ausbleiben: Ein Hook, der bei Netzproblemen den Sessionstart anhaelt, wird
abgeschaltet und schuetzt danach gar nichts. Jeder Fall unten faehrt das
Skript deshalb gegen ein echtes Wegwerf-Repository — kein Mock, der die
Annahme des Autors bestaetigt statt sie zu widerlegen.

Ein Test mit einem gemockten git haette hier nichts geprueft: Der Hook
besteht praktisch nur aus git-Aufrufen, deren Randverhalten (leerer
Branch-Name, detached HEAD, fehlendes origin) genau die Stelle ist, an der
er falsch sein koennte.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import time

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_HOOK = _ROOT / ".claude" / "hooks" / "session-start.sh"
_SETTINGS = _ROOT / ".claude" / "settings.json"


def _git(cwd: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
        },
    )


def _commit(repo: pathlib.Path, text: str) -> None:
    (repo / "datei.txt").write_text(text, encoding="utf-8")
    _git(repo, "add", "datei.txt")
    _git(repo, "commit", "-m", text)


def _hook(repo: pathlib.Path, **umgebung: str) -> subprocess.CompletedProcess:
    """Faehrt den Hook so, wie Claude Code ihn faehrt: ohne Terminal."""
    return subprocess.run(
        ["bash", str(_HOOK)],
        cwd=repo,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=60,
        env={
            **os.environ,
            "CLAUDE_PROJECT_DIR": str(repo),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            **umgebung,
        },
    )


def _loesche_origin_head(repo: pathlib.Path) -> None:
    """Entfernt `refs/remotes/origin/HEAD` — den Symref, nicht sein Ziel.

    `git update-ref -d refs/remotes/origin/HEAD` dereferenziert und loescht
    `origin/master`; der Symref bleibt stehen und `git symbolic-ref --short`
    liefert weiter «origin/master», auch wenn dort nichts mehr liegt. Die
    erste Fassung dieser Tests glaubte damit, den Netzweg zu pruefen, und
    lief in Wahrheit weiter ueber den lokalen Kurzweg.
    """
    _git(repo, "symbolic-ref", "-d", "refs/remotes/origin/HEAD")
    assert not (repo / ".git" / "refs" / "remotes" / "origin" / "HEAD").exists()


def _stummer_remote(klon: pathlib.Path, tmp_path: pathlib.Path) -> pathlib.Path:
    """Verlegt `origin` auf ein ssh://-Ziel, das Verbindungen nie beantwortet.

    Ein toter Remote (Verbindung abgelehnt) faellt sofort durch und pruefte
    die Frist nicht — nur ein Ziel, das annimmt und schweigt, tut das.
    """
    haenger = tmp_path / "haenger.sh"
    haenger.write_text("#!/bin/sh\nsleep 120\n", encoding="utf-8")
    haenger.chmod(0o755)
    _git(klon, "remote", "set-url", "origin", "ssh://stumm.invalid/repo.git")
    # Der lokale origin/HEAD wuerde den Netzweg fuer die Branch-Ermittlung
    # ueberspringen; hier soll beides ueber den haengenden Remote laufen.
    _loesche_origin_head(klon)
    return haenger


@pytest.fixture
def upstream(tmp_path: pathlib.Path) -> pathlib.Path:
    """Ein Remote, dessen Standard-Branch absichtlich nicht `main` heisst."""
    quelle = tmp_path / "upstream"
    quelle.mkdir()
    _git(quelle, "init", "--initial-branch=master", "--quiet")
    _commit(quelle, "eins")
    return quelle


@pytest.fixture
def klon(tmp_path: pathlib.Path, upstream: pathlib.Path) -> pathlib.Path:
    ziel = tmp_path / "klon"
    subprocess.run(
        ["git", "clone", "--quiet", str(upstream), str(ziel)],
        check=True,
        capture_output=True,
    )
    return ziel


# --- Die Meldung -----------------------------------------------------------


def test_meldet_rueckstand_und_nennt_den_ermittelten_branch(
    klon: pathlib.Path, upstream: pathlib.Path
) -> None:
    _commit(upstream, "zwei")
    _commit(upstream, "drei")

    ergebnis = _hook(klon)

    assert ergebnis.returncode == 0
    assert "2 Commits hinter origin/master" in ergebnis.stdout


def test_ein_commit_wird_nicht_als_commits_gemeldet(
    klon: pathlib.Path, upstream: pathlib.Path
) -> None:
    _commit(upstream, "zwei")

    assert "1 Commit hinter origin/master" in _hook(klon).stdout


def test_meldung_nennt_den_grund(klon: pathlib.Path, upstream: pathlib.Path) -> None:
    """Ohne Grund ist die Meldung nur Laerm, den man wegklickt."""
    _commit(upstream, "zwei")

    ausgabe = _hook(klon).stdout
    assert "3.8.2026" in ausgabe
    assert "rote CI" in ausgabe


def test_meldung_nennt_den_befehl_der_sie_behebt(
    klon: pathlib.Path, upstream: pathlib.Path
) -> None:
    _commit(upstream, "zwei")

    assert "git fetch origin master" in _hook(klon).stdout


def test_der_standard_branch_wird_ermittelt_nicht_angenommen(
    klon: pathlib.Path, upstream: pathlib.Path
) -> None:
    """Kein `main` im Upstream — ein fest verdrahtetes `main` waere hier still.

    Genau diese Annahme hat im Portfolio einen Branch 15 Commits alt werden
    lassen: `git fetch origin main` scheitert auf einem `master`-Remote mit
    «couldn't find remote ref main», was wie ein Netzproblem aussieht.
    """
    _commit(upstream, "zwei")
    assert _git(klon, "branch", "-r").stdout.count("origin/main") == 0, (
        "Aufbau kaputt: der Upstream soll keinen main-Branch haben"
    )

    assert "hinter origin/master" in _hook(klon).stdout


def test_ohne_origin_head_wird_der_remote_gefragt(
    klon: pathlib.Path, upstream: pathlib.Path
) -> None:
    """Frisch bereitgestellte Container haben `origin/HEAD` oft nicht."""
    _commit(upstream, "zwei")
    _loesche_origin_head(klon)

    assert "hinter origin/master" in _hook(klon).stdout


# --- Das Schweigen ---------------------------------------------------------


def test_schweigt_bei_aktuellem_klon(klon: pathlib.Path) -> None:
    ergebnis = _hook(klon)

    assert ergebnis.returncode == 0
    assert ergebnis.stdout == ""


def test_eigene_commits_voraus_sind_kein_rueckstand(klon: pathlib.Path) -> None:
    """`HEAD..FETCH_HEAD` zaehlt nur, was fehlt — nicht, was dazugekommen ist."""
    _commit(klon, "eigene arbeit")

    assert _hook(klon).stdout == ""


def test_schweigt_bei_detached_head(klon: pathlib.Path, upstream: pathlib.Path) -> None:
    _commit(upstream, "zwei")
    _git(klon, "checkout", "--quiet", "--detach", "HEAD")

    ergebnis = _hook(klon)

    assert ergebnis.returncode == 0
    assert ergebnis.stdout == ""


def test_schweigt_ohne_origin(klon: pathlib.Path, upstream: pathlib.Path) -> None:
    _commit(upstream, "zwei")
    _git(klon, "remote", "remove", "origin")

    ergebnis = _hook(klon)

    assert ergebnis.returncode == 0
    assert ergebnis.stdout == ""


def test_schweigt_ausserhalb_eines_repos(tmp_path: pathlib.Path) -> None:
    leer = tmp_path / "kein-repo"
    leer.mkdir()

    ergebnis = _hook(leer)

    assert ergebnis.returncode == 0
    assert ergebnis.stdout == ""


def test_schweigt_wenn_der_remote_verschwunden_ist(
    klon: pathlib.Path, upstream: pathlib.Path
) -> None:
    """Der haeufigste Netzfehler in Ruhe: das Ziel ist einfach nicht da."""
    _commit(upstream, "zwei")
    _loesche_origin_head(klon)
    shutil.rmtree(upstream)

    ergebnis = _hook(klon)

    assert ergebnis.returncode == 0
    assert ergebnis.stdout == ""
    assert ergebnis.stderr == ""


def test_schweigt_wenn_der_remote_keinen_standard_branch_nennt(
    tmp_path: pathlib.Path,
) -> None:
    """Der leere Branch-Name ist gefaehrlicher als der falsche.

    `git fetch origin ""` scheitert nicht — es fetcht still den Remote-HEAD
    und endet mit 0. Ohne Abbruch bei leerem Namen meldete der Hook damit
    einen Rueckstand «hinter origin/» und benennt einen Branch, den es nicht
    gibt; der Befehl in der Meldung waere dann ebenfalls unbrauchbar.

    Aufgebaut wird der Fall ueber ein Remote mit nicht-symbolischem HEAD:
    `ls-remote --symref` liefert dort keine `ref:`-Zeile, und der lokale
    `origin/HEAD` fehlt.
    """
    quelle = tmp_path / "quelle"
    quelle.mkdir()
    _git(quelle, "init", "--initial-branch=master", "--quiet")
    _commit(quelle, "eins")

    fern = tmp_path / "fern.git"
    subprocess.run(
        ["git", "clone", "--quiet", "--bare", str(quelle), str(fern)],
        check=True,
        capture_output=True,
    )
    ziel = tmp_path / "klon"
    subprocess.run(
        ["git", "clone", "--quiet", str(fern), str(ziel)],
        check=True,
        capture_output=True,
    )

    _commit(quelle, "zwei")
    _git(fern, "fetch", "--quiet", "origin", "refs/heads/*:refs/heads/*")
    # HEAD nicht-symbolisch machen: ab hier nennt der Remote keinen Branch.
    _git(fern, "update-ref", "--no-deref", "HEAD", _git(fern, "rev-parse", "HEAD").stdout.strip())
    _loesche_origin_head(ziel)

    # Gegenprobe zum Aufbau: der Remote nennt wirklich keinen Branch mehr,
    # und ein fetch mit leerem Namen laeuft trotzdem durch.
    symref = _git(ziel, "ls-remote", "--symref", "origin", "HEAD").stdout
    assert "ref:" not in symref, "Aufbau kaputt: der Remote nennt doch einen Branch"

    ergebnis = _hook(ziel)

    assert ergebnis.returncode == 0
    assert ergebnis.stdout == ""


# --- Die oberste Regel: nie blockieren -------------------------------------


def test_haengender_remote_haelt_den_start_nicht_auf(
    klon: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """Der Fall, der den Hook sonst zur Abschaltung verurteilt.

    Ein Remote, der Verbindungen annimmt und dann nichts sagt, ist genau das
    flatternde DNS aus der Anforderung — ohne Frist wartet git hier ewig.
    Gemessen wird echte Zeit: Eine Fake-Uhr, die nur beim Schlafen vorrueckt,
    koennte eine Zusicherung ueber echte Wartezeit nicht widerlegen.
    """
    haenger = _stummer_remote(klon, tmp_path)

    beginn = time.monotonic()
    ergebnis = _hook(klon, SECO_HOOK_FRIST="2", GIT_SSH_COMMAND=str(haenger))
    dauer = time.monotonic() - beginn

    assert ergebnis.returncode == 0
    assert dauer < 30, f"Hook brauchte {dauer:.1f}s — der Sessionstart haengt"


def test_frist_greift_auch_ohne_coreutils_timeout(
    klon: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """Ohne `timeout` im PATH muss der eigene Waechter uebernehmen.

    Der erste Entwurf verliess sich auf `timeout`; auf macOS ohne coreutils
    gibt es das nicht, und die Frist waere dort wirkungslos gewesen, ohne
    dass irgendetwas rot geworden waere.
    """
    haenger = _stummer_remote(klon, tmp_path)

    # Ein PATH mit git, aber ohne timeout.
    huelle = tmp_path / "bin"
    huelle.mkdir()
    for werkzeug in ("git", "bash", "sh", "sed", "head", "sleep", "kill", "ssh"):
        pfad = shutil.which(werkzeug)
        if pfad:
            (huelle / werkzeug).symlink_to(pfad)
    assert shutil.which("timeout", path=str(huelle)) is None

    beginn = time.monotonic()
    ergebnis = _hook(
        klon,
        PATH=str(huelle),
        SECO_HOOK_FRIST="2",
        GIT_SSH_COMMAND=str(haenger),
    )
    dauer = time.monotonic() - beginn

    assert ergebnis.returncode == 0
    assert dauer < 30, f"Hook brauchte {dauer:.1f}s ohne coreutils-timeout"


def test_hook_fragt_nie_nach_zugangsdaten(klon: pathlib.Path) -> None:
    """Ein Passwort-Prompt ohne Terminal ist der Haenger in Reinform."""
    inhalt = _HOOK.read_text(encoding="utf-8")

    assert "GIT_TERMINAL_PROMPT=0" in inhalt
    assert "BatchMode=yes" in inhalt


# --- Die Registrierung -----------------------------------------------------


def test_hook_ist_ausfuehrbar() -> None:
    """Ohne x-Bit startet der Hook nicht — und meldet das auch nicht."""
    assert _HOOK.exists()
    assert os.access(_HOOK, os.X_OK)


def test_settings_registriert_genau_diesen_hook() -> None:
    import json

    einstellungen = json.loads(_SETTINGS.read_text(encoding="utf-8"))
    befehle = [
        h["command"] for eintrag in einstellungen["hooks"]["SessionStart"] for h in eintrag["hooks"]
    ]

    assert any("session-start.sh" in b for b in befehle)
    assert any("$CLAUDE_PROJECT_DIR" in b for b in befehle), (
        "Ohne $CLAUDE_PROJECT_DIR haengt der Hook am Arbeitsverzeichnis"
    )
