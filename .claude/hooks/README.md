# SessionStart-Hook: Klon-Aktualität

`session-start.sh` meldet beim Sessionstart, wie viele Commits der
ausgecheckte Stand hinter `origin/<Standard-Branch>` liegt. Bei 0 schweigt er.

## Warum

Ein veralteter Klon hat am 3.8.2026 zweimal eine rote CI erzeugt, deren
Ursache nicht im Diff stand — die fehlenden Commits waren jeweils genau die,
die das Gate einführten, an dem der Branch scheiterte. Man sucht dann in den
Dateien, die man selbst geändert hat, und findet dort nichts, weil dort nichts
ist. Die Prüfung kostet eine Sekunde und ersetzt diese Fehlersuche.

`CLAUDE.md` verlangt dieselbe Prüfung von Hand, «vor der Arbeit». Von Hand
heisst: wenn man daran denkt. Genau daran hat es zweimal gefehlt.

## Was er garantiert

**Er blockiert die Session nie.** Das ist die oberste Regel, wichtiger als die
Meldung selbst: Ein Hook, der bei Netzproblemen die Arbeit anhält, wird nach
dem zweiten Mal abgeschaltet und schützt danach gar nichts.

Still mit Status 0 durch gehen:

| Fall | Verhalten |
| --- | --- |
| Kein Git-Repo | still |
| Kein `origin` | still |
| Kein Netz, DNS flattert, Remote hängt | still, nach spätestens `SECO_HOOK_FRIST` Sekunden |
| Standard-Branch nicht ermittelbar | still |
| detached HEAD | still |
| `timeout` (coreutils) fehlt | still, eigener Wächter greift |
| Rückstand 0 | still |
| Rückstand ≥ 1 | **einzige Ausgabe** |

Jeder Netzaufruf hat eine eigene Frist (Default 5 s, via `SECO_HOOK_FRIST`
änderbar). Zusätzlich steht in `settings.json` ein `timeout` von 15 s als
zweite Schranke, falls das Skript selbst je hängen bliebe.

Git wird so aufgerufen, dass es unter keinen Umständen nach Zugangsdaten
fragt (`GIT_TERMINAL_PROMPT=0`, `BatchMode=yes`). Ein Passwort-Prompt in
einem Hook ohne Terminal ist genau das Hängen, das hier ausgeschlossen sein
soll — die Frist deckt es zwar ab, aber erst nach Ablauf.

## Der Standard-Branch wird ermittelt, nicht angenommen

Erst lokal über `refs/remotes/origin/HEAD` (kostet kein Netz), sonst über
`git ls-remote --symref origin HEAD`.

Drei Server im Portfolio heissen ihren Standard-Branch `master`
(`openlex-mcp`, `swiss-courts-mcp`, `swisstopo-mcp`). Ein fest verdrahtetes
`origin/main` scheitert dort mit «couldn't find remote ref main» — was wie ein
Netzproblem aussieht. Ein Branch wurde so 15 Commits alt.

Der leere Branch-Name ist dabei der gefährlichere Fall als der falsche:
`git fetch origin ""` fetcht still den Remote-HEAD und endet mit 0. Das
Skript bricht bei leerem Namen ab, statt zu fetchen.

## Prüfen

Der Hook wird von `tests/test_session_start_hook.py` gegen echte
Wegwerf-Repositories gefahren — je ein Fall pro Zeile der Tabelle oben.

Von Hand:

```bash
CLAUDE_PROJECT_DIR="$PWD" .claude/hooks/session-start.sh; echo "Status: $?"
```

Auf aktuellem Klon: keine Ausgabe, Status 0.
