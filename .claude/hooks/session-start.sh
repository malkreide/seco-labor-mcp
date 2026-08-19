#!/usr/bin/env bash
# Klon-Aktualitaet melden — und sonst nichts.
#
# Meldet beim Sessionstart, wie viele Commits der ausgecheckte Stand hinter
# origin/<Standard-Branch> liegt. Schweigt bei 0.
#
# GRUND: Ein veralteter Klon hat am 3.8.2026 zweimal eine rote CI erzeugt,
# deren Ursache nicht im Diff stand — die fehlenden Commits waren jeweils
# genau die, die das Gate einfuehrten, an dem der Branch scheiterte. Die
# Pruefung kostet eine Sekunde und ersetzt eine Fehlersuche in den falschen
# Dateien.
#
# OBERSTE REGEL: Dieser Hook blockiert die Session nie. Kein Netz, kein
# Remote, detached HEAD, flatterndes DNS, fehlendes `timeout`, kaputtes
# .git — jeder dieser Faelle endet still mit Status 0. Ein Hook, der bei
# Netzproblemen die Arbeit anhaelt, wird nach dem zweiten Mal abgeschaltet
# und schuetzt danach gar nichts.
#
# Ausfuehrliche Begruendung: .claude/hooks/README.md

set -u

# Sekunden fuer *jeden* einzelnen Netzaufruf (Default-Branch ermitteln,
# fetch). Absichtlich klein: ein Sessionstart darf daran nicht haengen.
FRIST="${SECO_HOOK_FRIST:-5}"

# Git darf unter keinen Umstaenden nach Zugangsdaten fragen — ein
# Passwort-Prompt in einem Hook ohne Terminal ist genau das Haengen, das
# hier ausgeschlossen sein soll. Die Frist deckt das zwar ab, aber erst
# nach Ablauf; besser gar nicht erst fragen.
export GIT_TERMINAL_PROMPT=0
export GIT_ASKPASS="${GIT_ASKPASS:-true}"
export SSH_ASKPASS="${SSH_ASKPASS:-true}"
export SSH_ASKPASS_REQUIRE=never
# Nur setzen, wenn der Aufrufer nichts eigenes mitbringt: eine vorhandene
# GIT_SSH_COMMAND kann Proxy oder Schluessel tragen, die wir nicht kennen.
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o BatchMode=yes -o ConnectTimeout=5}"

# `timeout` (coreutils) ist nicht ueberall da — z.B. auf macOS ohne
# coreutils. Ohne Ersatz liefe der fetch dort unbegrenzt, also genau der
# Haenger, den die Frist verhindern soll.
mit_frist() {
    local frist="$1"
    shift
    if command -v timeout >/dev/null 2>&1; then
        timeout "$frist" "$@"
        return $?
    fi
    # Eigene Prozessgruppe, damit der Waechter unten die ganze Gruppe treffen
    # kann. Ohne das ueberlebt der ssh-Enkel den getroffenen git-Prozess und
    # haengt weiter — der Hook waere zwar durch, liesse aber bei jedem Start
    # auf schlechter Leitung einen Prozess zurueck. (`timeout` macht genau
    # das von sich aus; der Fallback muss es nachbauen.)
    if command -v setsid >/dev/null 2>&1; then
        setsid "$@" &
    else
        "$@" &
    fi
    local aufgabe=$!
    (
        sleep "$frist"
        kill -TERM -"$aufgabe" 2>/dev/null || kill -TERM "$aufgabe" 2>/dev/null
    ) &
    local waechter=$!
    wait "$aufgabe" 2>/dev/null
    local rc=$?
    kill -TERM "$waechter" 2>/dev/null
    wait "$waechter" 2>/dev/null
    return "$rc"
}

# Standard-Branch ermitteln, nicht raten. Drei Server im Portfolio heissen
# ihn `master`; die Annahme `main` hat schon einmal einen Branch 15 Commits
# alt werden lassen, weil der fetch mit «couldn't find remote ref main»
# scheiterte und das wie ein Netzproblem aussah.
standard_branch() {
    local ref
    # Erst lokal: refs/remotes/origin/HEAD kostet kein Netz. Reine
    # Abkuerzung ohne eigene Zusicherung — faellt sie weg, kommt derselbe
    # Name ueber den Netzweg, nur langsamer. Kein Test kann sie deshalb
    # widerlegen; sie steht hier fuer die Frist, nicht fuer das Ergebnis.
    ref="$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null)"
    if [ -n "$ref" ]; then
        printf '%s\n' "${ref#origin/}"
        return 0
    fi
    # Sonst fragen. Frisch geklonte Container haben origin/HEAD oft nicht.
    mit_frist "$FRIST" git ls-remote --symref origin HEAD 2>/dev/null |
        sed -n 's|^ref: refs/heads/\([^[:space:]]*\).*|\1|p' |
        head -n 1
}

pruefe() {
    local wurzel="${CLAUDE_PROJECT_DIR:-}"
    if [ -z "$wurzel" ]; then
        wurzel="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)" || return 0
    fi
    cd -- "$wurzel" 2>/dev/null || return 0

    # Kein Repo -> nichts zu melden.
    [ "$(git rev-parse --is-inside-work-tree 2>/dev/null)" = "true" ] || return 0

    # detached HEAD: «wie weit ist mein Branch zurueck» hat hier keine
    # Antwort, die eine Meldung wert waere. Still durch.
    git symbolic-ref -q HEAD >/dev/null 2>&1 || return 0

    local branch
    branch="$(standard_branch)"
    # Leerer Branch-Name ist der gefaehrliche Fall: `git fetch origin ""`
    # fetcht still den Remote-HEAD und endet mit 0. Hier abbrechen.
    [ -n "$branch" ] || return 0

    # `--no-tags`, damit der Start nicht an einem tag-schweren Remote haengt.
    mit_frist "$FRIST" git fetch --quiet --no-tags origin "$branch" 2>/dev/null || return 0

    local rueckstand
    rueckstand="$(git rev-list --count HEAD..FETCH_HEAD 2>/dev/null)" || return 0
    case "$rueckstand" in
        '' | 0 | *[!0-9]*) return 0 ;;
    esac

    local wort="Commits"
    [ "$rueckstand" = "1" ] && wort="Commit"

    cat <<MELDUNG
Klon veraltet: ${rueckstand} ${wort} hinter origin/${branch}.

    git fetch origin ${branch} && git merge FETCH_HEAD

Grund: Ein veralteter Klon hat am 3.8.2026 zweimal eine rote CI erzeugt,
deren Ursache nicht im Diff stand — die fehlenden Commits waren jeweils
genau die, die das Gate einfuehrten, an dem der Branch scheiterte.
MELDUNG
}

pruefe || true
exit 0
