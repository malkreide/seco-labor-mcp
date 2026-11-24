# CLAUDE.md

## Teil 1 — Portfolio-Konventionen

### Vor der Arbeit

Klon-Aktualität prüfen — Standard-Branch ermitteln, nicht `main` annehmen:

```bash
B=$(git ls-remote --symref origin HEAD | sed -n 's|^ref: refs/heads/\([^[:space:]]*\).*|\1|p')
git fetch origin "${B:?Standard-Branch nicht ermittelbar}" &&
  git rev-list --count HEAD..FETCH_HEAD
```

Drei Server im Portfolio heissen ihren Standard-Branch `master`
(`openlex-mcp`, `swiss-courts-mcp`, `swisstopo-mcp`); dort scheitert ein fest
verdrahtetes `origin/main` mit «couldn't find remote ref main». Wer das für ein
Netzproblem hält, arbeitet weiter auf genau dem veralteten Klon, vor dem dieser
Absatz warnt. Den `:?`-Schutz nicht weglassen: Bei leerem `B` fetcht git still
den Remote-HEAD und endet mit 0.

Die Refspec gehört ebenso dazu, und nicht aus Höflichkeit: Ohne sie ist
`HEAD..FETCH_HEAD` nicht am Standard-Branch gemessen — gemessen weiter unten
unter «Und `git merge FETCH_HEAD` bringt den Standard-Branch nur mit Refspec».

Ein veralteter Klon erzeugt eine rote CI, deren Ursache nicht im Diff steht.
Am 3.8.2026 zweimal passiert — beide Male fehlten genau die Commits, die
das Gate einführten, an dem der Branch scheiterte.

Gates lokal fahren, mit der GEPINNTEN ruff-Version aus der CI. Eine andere
Version meldet Abweichungen, die niemand verursacht hat.

### Tests

Gegenprobe ist Pflicht. Ein Test, der grün bleibt, wenn man die
Implementierung entfernt, prüft nichts. Jede neue Zusicherung einzeln
neutralisieren und zeigen, dass genau die zugehörigen Tests fallen.

Zwei Fallen, die beide grün blieben:

- Eine Fake-Uhr, die nur beim Schlafen vorrückt, kann eine Zusicherung über
  echte Zeit nicht widerlegen.
- `monkeypatch.setattr(modul.asyncio, "sleep", ...)` greift ins Modul
  `asyncio` selbst und entschärft die Mechanik im ganzen Prozess. Patche
  einen Modul-Alias (`_sleep = asyncio.sleep`), nicht das fremde Modul.

**Die Gegenprobe braucht selbst eine Kontrolle.** Zweimal hat hier eine Probe
bestätigt statt gemessen, beide Male, weil sie nicht tat, was sie zu tun
schien.

Am 14.11.2026 sollte nachgestellt werden, ob `git fetch --prune origin main`
einen veralteten Tracking-Ref stehen lässt. Die Probe löschte den
Remote-Branch mit `git push origin --delete` aus demselben Klon — und das
räumt den Tracking-Ref als Nebenwirkung gleich mit auf. Gemessen wurde danach
ein Ref, der schon vor dem Fetch weg war; beide Aufrufe sahen gleich gut aus,
und der Befund galt als widerlegt. Erst die Löschung im Remote selbst
(`git update-ref -d` im Bare-Repo) stellte die Lage her.

Am 22.11.2026 sollten sieben Verfälschungen einer Tabelle zeigen, dass ein
neuer Test sie wirklich hält. Alle sieben blieben grün. Blind war nicht der
Test, sondern das Bash-Gerüst: maskierte Backticks in doppelten
Anführungszeichen, und die Ersetzung lief ins Leere. Mit einem Python-Gerüst
ohne Zitierebene fiel jeder der sieben.

Drei Handgriffe daraus:

- **Erst prüfen, dass die Probe gegriffen hat, dann ihr Ergebnis lesen.** Eine
  Ersetzung, die nichts ersetzt, ist still erfolgreich; ein
  `assert text.count(alt) == 1` davor kostet nichts.
- **Ein einheitliches Ergebnis über mehrere unabhängige Verfälschungen ist ein
  Verdacht, keine Entwarnung.** Sieben grüne Proben in Folge messen eher das
  Gerüst als die Sache — zumal dann, wenn derselbe Test eben noch richtig
  gefallen ist.
- **Eine Zitierebene weniger.** Patch-Skripte gehören in die Sprache, in der
  auch die Zusicherung steht, nicht in eine Shell-Zeile mit maskierten
  Sonderzeichen.

Die Nebenwirkung von `git push origin --delete` ist gemessen und hängt an
`tests/test_prune_doku.py`; der Absatz zum Prune-Fund weiter unten nennt
denselben Fall von seiner Seite aus.

Handgeschriebene Fixtures kodieren die Annahme des Autors und können sie
nicht widerlegen. Mindestens eine aufgezeichnete Antwort pro externem
Endpunkt, mit Aufnahmedatum.

### Wenn etwas rot ist

Roter Live-Test: erst die Quelle abfragen, dann einordnen. Nicht aus der
Fehlermeldung schliessen. Am 3.8.2026 hiess "nicht gefunden" nicht, dass der
Datensatz weg war, sondern dass die Quelle die Schreibweise ihrer Kopfzeile
gewechselt hatte — vier von sechs Datensätzen produktiv kaputt, alle
Unit-Tests grün.

**Ein 4xx ist kein Nein.** Am 29.8.2026 antwortete `past-publications` in
`swiss-procurement-mcp` auf jede Publikation mit Losen mit HTTP 400. Daraus war
geschlossen worden, die Quelle verweigere diese Auskunft; der Befund stand
datiert im Fixture-Nachweis, ein Test bestätigte ihn, alles blieb grün. Die
Spec desselben Endpunkts führt einen als *optional* deklarierten Parameter
`lotId` — für Publikationen mit Losen ist er Pflicht. Mit ihm antwortet
dieselbe Publikation mit 200. Ein Projekt trug sieben Vorgängerpublikationen,
die der Server als «Quelle nicht erreichbar» wegwarf.

Drei Handgriffe daraus:

- **Die Parameterliste der Spec durchgehen, bevor ein Statuscode eingeordnet
  wird.** «Optional» heisst dort oft «optional für die Mehrheit».
- **Einer deterministischen Absage keinen Wiederholungsrat geben.** «Nicht
  erreichbar, bitte später erneut» ist bei einem 400 falsch und liest sich für
  das Modell wie eine Störung. Den Status mitführen und den fehlenden
  Parameter benennen — den Status, nicht den Antwortkörper.
- **Beide Antworten aufzeichnen, mit und ohne den Parameter.** Eine
  Aufzeichnung nur des Fehlschlags kann nicht zeigen, dass er vermeidbar war;
  dass nur der 400er aufgezeichnet war, ist der Grund, warum der falsche
  Befund nicht auffiel.

**Und ein 403 ist gar keine Auskunft.** Am 29.8.2026 sollten für 42 Repos die
Dependabot-Labels nachgemessen werden. Alle 13 Abfragen des ersten Stapels
kamen zurück als:

```
Failed to find label: API rate limit already exceeded for user ID 8864492.
```

Der gefährliche Teil steht vorn: Das Werkzeug verpackt eine Sperre als
Fund-Fehlschlag. Wer die Zeile überfliegt oder nur auf ein leeres Ergebnis
prüft, zählt 39 Repos als «Label fehlt» und hat seine eigene Erschöpfung
gemessen. Das Limit hängt am Konto, nicht am Repo — derselbe Vormittag hatte
es mit 42 eröffneten und 42 gemergten PRs verbraucht.

Das ist der Absatz darüber, andersherum gelesen: dort war ein 400 eine echte,
wiederholbare Antwort und galt als Störung; hier ist eine Störung als Antwort
verpackt. Entscheidend ist nie der Statuscode, sondern ob die Quelle überhaupt
geantwortet hat.

- **Positivkontrolle im selben Repo.** Ein «nicht gefunden» wird erst dadurch
  zur Messung, dass eine gleichzeitige Abfrage etwas findet.
- **Die Messung entlang der Sperre teilen.** `raw.githubusercontent.com` ist
  ein CDN und nicht die REST-API. Um 11:19:27 UTC lieferte es für
  `register-mcp` HTTP 200, während die Label-Abfrage desselben Repos in
  derselben Minute die Sperre meldete. Alle 42 `dependabot.yml` kamen so
  durch, während die Label-Hälfte stand.
- **Am Token vorbei geht es nicht.** Beide Umwege enden am Agent-Proxy, und
  jeder mit einer eigenen irreführenden Begründung. `api.github.com` ohne
  Zugangsdaten:

  ```
  GitHub access is not enabled for this session. An org admin must connect
  the Claude GitHub App for this organization.
  ```

  Das ist keine Aussage über die Organisation, sondern das, was ohne Token
  kommt. Wer ihr folgt, sucht einen Admin für ein Problem, das keiner hat.
  Die HTML-Seite `github.com/<owner>/<repo>/labels` fällt ebenfalls, aber
  anders:

  ```
  This GitHub API path is not available: sessions are bound to their
  configured repositories. Use repository-scoped endpoints
  (repos/{owner}/{repo}/...).
  ```

  Der Proxy behandelt also auch `github.com` als API-Pfad; die zweite Meldung
  klingt nach einem Scope-Problem und ist doch nur dieselbe Sackgasse. Den
  Token aus der Umgebung in einen curl-Header zu setzen, blockiert der
  Klassifikator. Ob es überhaupt hülfe, ist offen: die Sperre nennt ein
  Nutzerkonto, und ob der Token zu diesem gehört, wurde nie geprüft.
- **Die Sperre gilt nicht dem Dienst, sondern dem Zugangspfad.** Unmittelbar
  nachdem eine Abfrage der Checks eines PR sauber durchlief, meldete die
  Label-Abfrage weiter die Sperre. Von einem blockierten Werkzeug also nicht
  auf «GitHub ist zu» schliessen — und umgekehrt eine gelungene Abfrage nicht
  als Entwarnung für die gesperrte nehmen.

Wann die Sperre fällt, geben diese Beobachtungen nicht her. Die Meldung nennt
keinen Zeitpunkt, und die `X-RateLimit`-Kopfzeilen sind hinter dem Proxy nicht
zu sehen. Belegt sind drei gesperrte Zeitpunkte — 11:14, 11:16 und 11:19 UTC.
Wer daraus eine Dauer macht, hat sie erfunden.

**Dieselbe Falle bei einer Konfigurationsoption: die Vorgabe lesen, bevor man
einen Schlüssel für wirkungslos hält.** Am 29.8.2026 fielen die
`labels:`-Zeilen aus den `dependabot.yml` des Portfolios, begründet mit
«Dependabot legt Labels nicht an». Eine Messung danach zeigte, dass
`dependencies` in 36 von 42 Repos sehr wohl existiert, 35 davon mit GitHubs
Standardbeschreibung. Das las sich zuerst wie ein Beleg, dass die Aktion
falsch war.

Die Optionsreferenz kehrt es um:

```
Dependabot creates these default labels automatically, as necessary in
your repository.

If you define more than one package manager, an additional label for the
ecosystem or language is added to each pull request.

The labels specified are used instead of the default labels.
```

Ohne `labels:` vergibt Dependabot also `dependencies` — und, sobald mehr als
ein Paketmanager deklariert ist, zusätzlich ein Ökosystem-Label — und legt sie
selbst an; eine eigene Liste **ersetzt** diesen Satz, und «if any of these
labels is not defined in the repository, it is ignored». Die Zeile war nicht
wirkungslos — sie tauschte einen sich selbst pflegenden Vorgabesatz gegen eine
starre Liste.

**Die Bedingung nicht weglassen.** Bei nur einem Paketmanager steht das
Ökosystem-Label gar nicht zu; wer es dort trotzdem erwartet, schreibt genau
den Fehlbefund auf, gegen den dieser Abschnitt geschrieben ist — der Abschnitt
liefe an sich selbst vorbei. Im Portfolio deklariert jede `dependabot.yml`
zwei (`pip` und `github-actions`), die Bedingung ist hier also überall
erfüllt; anderswo nicht unbedingt. Aufgefallen ist die fehlende Bedingung
nicht beim Schreiben, sondern durch einen Codex-Review auf
`swiss-environment-mcp` PR #113 — vierzehn Sekunden vor dem Merge desselben
PR.

Was das kostet, ist an `openlex-mcp` gemessen: zwei Ökosysteme deklariert,
also stünden `dependencies` **und** ein Ökosystem-Label zu; vorhanden ist nur
das erste, `github-actions` und `github_actions` fehlen beide (Kontrolle `bug`
vorhanden). `register-mcp` ist die Gegenprobe: dort existieren alle vier
deklarierten Namen mit handgeschriebener Beschreibung, die Liste ist gewollt
und vollständig.

**Dreimal falsch eingeordnet, in drei Richtungen.** Erst die Zeile für bloss
wirkungslos gehalten. Dann die gefundenen Labels für einen Widerspruch. Dann,
auf denselben Fund gestützt, einen richtigen PR geschlossen mit dem Argument,
das Label existiere ja — obwohl es existiert, *weil* die Vorgabe es anlegt.
Der dritte Fehler ist der teuerste, weil er wie eine Messung aussah.

Was die Messung **nicht** hergibt: wer die 36 Labels angelegt hat. Die
Referenz sagt, Dependabot tue es; die Objekt-IDs liegen aber so dicht
beieinander, dass sie eher aus einem Stapellauf stammen. Beides passt zum
Befund, keines ist belegt — die Herkunft blieb ungemessen.

Beim Aufräumen gilt deshalb dieselbe Frage wie bei `lotId`: Was ist die
*Vorgabe*, wenn man das Ding weglässt — nicht bloss, ob der aktuelle Wert
etwas bewirkt.

**`results[0]` ist nur so verlässlich wie die Zusicherung danach.** Pinnt die
Abfrage einen bekannten Datensatz, ist der erste Treffer eine Drift-Wache und
in Ordnung. Hängt die Zusicherung dagegen davon ab, *welche* Variante die
Quelle heute zuoberst hat, prüft der Test den Tag: am 25.8.2026 rot, weil die
neueste Zürcher Publikation zufällig Lose hatte, am 26.8. grün, ohne dass sich
etwas geändert hätte. Den Fall gezielt wählen und beide Zweige fahren.

PR ohne jeden Check ist selten ein Repo ohne CI, meistens ein
Merge-Konflikt: GitHub berechnet dafür keinen Merge-Commit und startet nichts.

**Bei einem blockierten PR nennt der Merge-Versuch den Blocker, jede Ableitung
rät.** `mergeable_state: blocked` bei grüner CI heisst: ein required Kontext
fehlt oder steht nicht auf grün. Welcher, sagt die Einstellung — und die sperrt
der Agent-Proxy mit HTTP 403, ein MCP-Werkzeug dafür gibt es nicht. Der Ausweg
ist nicht Indizienarbeit, sondern ein Merge-Versuch über die API:

```
PUT /repos/<owner>/<repo>/pulls/<n>/merge
405 Required status check "Codex hat diesen Head geprueft" is expected.
```

Der Name steht dort wörtlich so, wie er in der Branch Protection eingetragen
ist. Scheitert der Versuch, kostet er nichts.

Am 24./25.9.2026 über drei Repos vermessen, nachdem ein Gate-Workflow entfernt
worden war und seinen required Kontext ohne Berichterstatter zurückliess:

| Repo | eingetragener Kontext | Art |
|---|---|---|
| `register-mcp` | `Codex hat den PR angesehen` | Check-Run |
| `srgssr-mcp` | `review-abgeschlossen` | Check-Run |
| `fedlex-mcp` | `Codex hat diesen Head geprueft` | Check-Run |

**Warum Ableiten hier systematisch fehlgeht.** GitHub nimmt als Check-Run-Name
den **Job**-Namen, nicht den des Workflows. Zwei der drei Kontexte enthalten die
Zeichenfolge «codex-gate» nicht, obwohl sie aus `codex-gate.yml` stammen; wer in
den Einstellungen danach sucht, findet nichts und hält die Regel für abwesend.
Trug der Job kein `name:`, nimmt GitHub die Job-ID — daher `review-abgeschlossen`.

Zwei Fehlschlüsse sind dabei belegt, beide aus **einer** Beobachtung gezogen:

- Aus einem Commit-Status auf den required Kontext geschlossen. In `fedlex-mcp`
  stand der Status `codex-gate` auf dem Head auf `success` und blockierte
  nichts, während der fehlende Check-Run den Merge hielt. Am Kontroll-PR waren
  beide rot — dort ist nicht zu unterscheiden, welcher von beiden eingetragen
  ist. Genommen wurde der auffälligere.
- Aus einer Check-Run-Liste auf den required Kontext geschlossen. Die Liste
  zeigt, was **berichtet** wurde; eingetragen sein kann ein Name, der gerade
  gar nicht erscheint. Genau das ist der Fall, um den es geht.

**Ein Vorbehalt, der zur Methode gehört:** Die Absage nennt immer nur den
**ersten** fehlenden Kontext. Ist ein zweiter eingetragen, zeigt ihn erst der
nächste Versuch. Nach jeder Änderung an der Einstellung also erneut versuchen,
bis der Merge durchgeht oder ein neuer Name fällt.

Die Kosten der Ableitung sind gemessen: ein Arbeitstag, an dem der PR-Text den
falschen Namen trug und in den Einstellungen nach einer Zeichenfolge gesucht
wurde, die dort nicht steht.

**«1 unpushed commit» nach einem Merge ist meistens ein veralteter Ref.** Der
Stop-Hook rechnet gegen `refs/remotes/origin/<branch>`, und dieser Ref löst
lokal weiter auf, nachdem GitHub den Branch beim Merge gelöscht hat. Er steht
dann noch auf dem gemergten Head; der Merge-Commit liegt genau einen darüber,
daher ist die Zahl immer `1`. Am 11.9., 14.9. und 13./14.11.2026 dreimal
dieselbe Meldung, jedes Mal ohne einen einzigen eigenen Commit.

- **Die Quelle ist `git ls-remote --heads origin`**, nicht der Tracking-Ref.
  Fehlt der Branch dort, gibt es nichts zu pushen — gleichgültig, was der Ref
  noch führt.
- **Der Nachweis ist `git rev-list --left-right --count origin/main...HEAD`.**
  `0 0` bei sauberem Arbeitsbaum heisst: HEAD ist genau `main`.
- **Pushen ist die falsche Reaktion.** Es belebt einen gelöschten, bereits
  gemergten Branch wieder.

**Manchmal stimmt die Zahl, und die Handlung ist trotzdem falsch.** Am
22.11.2026 meldete der Hook denselben einen Commit, und diesmal war der Ref
nicht veraltet: `git ls-remote` führte den Branch, GitHub hatte ihn beim Merge
stehen lassen. Der Vorsprung war echt — und bestand aus dem Merge-Commit des
eigenen PR, weil der lokale Branch nach dem Merge auf `main` vorgezogen worden
war, während der Remote-Branch auf dem letzten PR-Commit blieb.

Die Unterscheidung kostet eine Zeile:

```bash
git merge-base --is-ancestor HEAD origin/main
```

Geht sie durch, liegt alles, was der Branch trägt, bereits in `main`; der
«Vorsprung» ist dessen eigener Merge-Commit. Ein Push zöge nur einen
erledigten Branch auf `main` nach und brächte nichts dorthin, was fehlte.

Beide Fälle sehen in der Meldung gleich aus und trennen sich nicht daran, ob
die Zahl stimmt, sondern daran, **wogegen** sie gerechnet ist. Deshalb steht
oben `origin/main` als Bezug und nicht der Branch-Ref: Der ist im einen Fall
veraltet und im anderen gültig — und in beiden der falsche Massstab.

**Und `--prune` wirkt nur im Aufruf ohne Refspec.** `git fetch --prune origin`
räumt den Ref weg; `git fetch --prune origin main` prunt nur im Ziel dieser
Refspec und lässt ihn stehen. Daran kam die Meldung am 13./14.11. zum dritten
Mal: Der Lauf davor war der mit Refspec, sah nach Aufräumen aus und hatte den
Branch-Ref nicht angefasst. Nachgestellt mit git 2.43.0 in einem
Wegwerf-Repo — mit Refspec überlebt der Ref und die Voraus-Rechnung liest `1`,
ohne Refspec ist er weg. Danach markiert `git status -sb` den Upstream als
`[gone]`.

**Die Konfiguration ersetzt den richtigen Aufruf nicht.** Naheliegend wäre,
einmal `fetch.prune = true` zu setzen und den Aufruf danach nicht mehr zu
beachten. Das trägt nicht: Die Option entscheidet, *ob* geprunt wird, nicht
*was* der Prune abdeckt — die Refspec-Grenze gilt für sie genauso. Gemessen
im selben Wegwerf-Repo:

| | `git fetch origin main` | `git fetch origin` |
|---|---|---|
| ohne `fetch.prune` | Ref bleibt | Ref bleibt |
| `fetch.prune = true` | Ref bleibt | Ref weg |

Nutzlos ist sie damit nicht — sie macht aus einem gewöhnlichen Fetch einen,
der aufräumt, und erspart den Schalter. Nur den Aufruf mit Refspec rettet sie
nicht, und genau der war das Problem.

Die erste Nachstellung zeigte das Gegenteil, und zwar aus einem Fehler der
Probe: Sie löschte den Remote-Branch mit `git push origin --delete` aus
demselben Klon, und das räumt den Tracking-Ref als Nebenwirkung gleich mit
auf. Geprüft wurde so ein Ref, der schon vor dem Fetch weg war — die Probe
konnte nur bestätigen. Erst die Löschung im Remote selbst (`git update-ref -d`
im Bare-Repo) stellt her, was GitHub beim Merge hinterlässt.

**Und `git merge FETCH_HEAD` bringt den Standard-Branch nur mit Refspec.** Am
22.11.2026 wurde der Klon mit
`git fetch --prune origin && git merge --ff-only FETCH_HEAD` nachgezogen — der
Prune-Aufruf aus dem Absatz davor, zusammengezogen mit dem Merge aus dem
Hook-Vorschlag. Der Merge meldete «Already up to date.» und endete mit 0. Der
Klon blieb einen Commit hinter `main`: genau der Zustand, vor dem der erste
Abschnitt dieser Datei warnt, hergestellt von einem Befehl, der Erfolg meldet.
Nachgestellt mit git 2.43.0, serverseitige Löschung per `git update-ref -d`:

| Zweig beim Merge gelöscht | Aufruf | `for-merge`-Zeilen | `git merge --ff-only FETCH_HEAD` | danach hinter `main` |
|---|---|---|---|---|
| ja | ohne Refspec | 0 | «Already up to date.» | 1 |
| ja | mit Refspec `main` | 1 | «Updating …» | 0 |
| nein | ohne Refspec | 1 | «Already up to date.» | 1 |
| nein | mit Refspec `main` | 1 | «Updating …» | 0 |

Hinter demselben Satz stehen zwei verschiedene Gründe. Ist der Zweig gelöscht,
trägt FETCH_HEAD keine einzige `for-merge`-Zeile — `git merge` nimmt nur diese,
hat also kein Ziel und endet zufrieden. Existiert er, ist die `for-merge`-Zeile
der *Zweig* und nicht `main`; gemergt wird dann etwas, das HEAD schon enthält.

**Beim Zählen greift eine andere Regel, mit demselben Ausgang.**
`HEAD..FETCH_HEAD` löst FETCH_HEAD über die *erste Zeile* der Datei auf, nicht
über die `for-merge`-Zeilen. Ohne Refspec ist das der Upstream des aktuellen
Zweigs, solange er existiert — die Zahl liest dann `0`, während `main` einen
Commit voraus ist. Ist der Zweig gelöscht, ist es der Ref, der zufällig
zuoberst steht; im Wegwerf-Repo mit einem dritten Zweig war das
`aaa-anderer`, und die Zahl stimmte bloss zufällig. Der Befund ist deshalb
nicht «die Zahl ist falsch», sondern das Unangenehmere: Sie ist nicht an `main`
verankert.

**Die beiden richtigen Verhaltensweisen ziehen auseinander.** Ohne Refspec wird
der veraltete Tracking-Ref geräumt, aber FETCH_HEAD taugt weder zum Mergen noch
zum Zählen; mit Refspec taugt es für beides, und der Ref bleibt stehen — das
ist der Absatz davor. Wer beides zusammenzieht, erwischt aus jedem Aufruf die
falsche Hälfte. Gemessen tut beides dieser Aufruf:

```bash
git fetch --prune origin && git merge --ff-only origin/main
```

Der Unterschied ist, dass `origin/main` den Branch beim Namen nennt, statt sich
darauf zu verlassen, was der Fetch als mergewürdig markiert oder in welcher
Reihenfolge er die Zeilen schreibt. Dieselbe Lehre wie im Absatz davor, eine
Ebene weiter: nicht der Schalter entscheidet, sondern wogegen gerechnet wird.

Die Kontrolle steckt in der Tabelle selbst: Dieselbe Probe lässt den Merge in
den Refspec-Zeilen wirklich vorrücken («Updating a..b», danach `0`). Sie kann
beide Ergebnisse zeigen — die zwei «Already up to date.» sind gemessen und
nicht das Ergebnis einer Probe, die nichts tat.

### Wenn Codex erst nach dem Merge urteilt

Am 23.9.2026 nahm Commit `3371e72` den Codex-Abschnitt aus dieser Datei, mit
der Begründung, das Repo trage keinen `codex-gate`-Workflow. Für den *Gate*
stimmt das und bleibt so. Für den *Review-Bot* nicht: Der läuft hier weiter,
zuletzt gemessen am 13.11.2026 auf PR #92 — Statuskommentar des
`chatgpt-codex-connector[bot]`, Auslöser «Draft marked ready», Commit
`66db6f1`. Was hier steht, ist deshalb nicht der alte Abschnitt, sondern das,
was seither an ihm gemessen wurde.

**Die Befundlos-Meldung ist weg, die Statustabelle nicht.** Einen Lauf ohne
Befund meldete Codex früher als gewöhnlichen Issue-Kommentar («Codex Review:
Didn't find any major issues»). Auf den neun befundlosen Läufen dieses Repos,
die gemessen wurden, steht kein solcher Kommentar — nur die Tabelle
*Review | Status | Commit | Review trigger* hinter dem Marker
`<!-- codex-pull-request-review-summary -->`, auf «✅ Completed»:

| PR | Datum | Commit | `get_reviews` | Befundlos-Kommentar |
|---|---|---|---|---|
| #74 | 9.9.2026 | `4f29cbc` | leer | keiner |
| #75 | 14.9.2026 | `943f676` | leer | keiner |
| #85 | 14.10.2026 | `5c82cc5` | leer | keiner |
| #91 | 13.11.2026 | `6c0c7f4` | leer | keiner |
| #92 | 13.11.2026 | `66db6f1` | leer | keiner |
| #97 | 22.11.2026 | `63182a2` | leer | keiner |
| #98 | 22.11.2026 | `8bf12af` | leer | keiner |
| #99 | 22.11.2026 | `d87669e` | leer | keiner |
| #100 | 22.11.2026 | `f279973` | leer | keiner |

Wer «geprüft und sauber» am Befundlos-Kommentar festmacht, findet ihn hier
über zehn Wochen nicht und bucht jeden sauberen Lauf als ausgefallenen.
Belastbar ist das Paar: Tabelle auf «Completed» **und** `get_reviews` leer.
«Completed» allein sagt nur, dass ein Lauf stattfand — auf PR #73 stand es
zur selben Minute wie ein P2-Befund im Review-Objekt.

**Ein Lauf, der nicht stattfindet, meldet sich als gewöhnlicher Kommentar.** Am
22.11.2026 um 18:42:35 UTC stand auf PR #100 statt des Statuskommentars dies,
acht Sekunden nach dem Eröffnen des Entwurfs:

```
To use Codex here, [create an environment for this repo](...).
```

Kein `codex-pull-request-review-summary`, kein `codex-review-state:v1`, keine
Statustabelle — und `get_reviews` leer. Es hat kein Lauf stattgefunden. Sieben
Minuten vorher, auf #99, war derselbe Bot normal durchgelaufen.

Das trifft die Regel darüber an ihrer schwächsten Stelle. `get_reviews` ist
hier **leer wie bei allen neun befundlosen Läufen**; wer «sauber» an diesem
einen Signal festmacht, bucht einen PR als geprüft, den niemand angesehen hat.
Das Paar trägt, weil es die Tabelle verlangt — aber nur, wenn man deren Fehlen
auch bemerkt. Fehlt sie, ist das Fehlen die Auskunft: **Kein Statuskommentar
heisst nicht befundlos, sondern ungeprüft.**

Dieselbe Klasse wie der 403, der sich als «Label nicht gefunden» ausgab: eine
Störung, verpackt als Auskunft. Nur steckt die Verpackung hier nicht im
Antworttext, sondern in dem, was gar nicht da ist.

**Siebzehn Minuten später lief derselbe Bot auf demselben Head.** #100 wurde um
18:59:29 auf «ready» gesetzt; der Lauf startete um 18:59:38, der
Statuskommentar erschien um 18:59:43, und um 19:00:38 stand das Urteil —
befundlos, Commit `f279973`, derselbe wie bei der Absage.

**Was diese Messung hergibt, und was nicht.** Sie zeigt, dass der Head um
18:59 prüfbar war. Sie zeigt *nicht*, warum es um 18:42 nicht ging. Hier stand
zuerst, die zweite Lesart — in den sieben Minuten dazwischen habe sich an der
Codex-Einrichtung etwas geändert — sei damit widerlegt, und an den
Einstellungen sei nichts kaputt gewesen. Das war überdehnt: Die Einstellungen
liegen ausserhalb des Repos und sind veränderlich. Zwischen den beiden
Zeitpunkten kann eine Umgebung angelegt worden sein, oder ein vorübergehender
Zustand kann sich aufgelöst haben — beides passt zu derselben Beobachtung.
Offen bleiben damit drei Lesarten: der Auslöser, eine Änderung an den
Einstellungen, oder ein Zustand, der von selbst ging.

Für den **Auslöser** spricht, dass #98 und #99 als Entwurf gar keinen
Kommentar bekamen, #100 aber acht Sekunden nach dem Eröffnen einen. Das ist
ein Indiz und kein Beweis; es trennt die drei Lesarten nicht.

Aufgefallen ist die Überdehnung nicht beim Schreiben, sondern durch einen
Codex-Review auf PR #101 — eingereicht 1 min 26 s **nach** dem Merge desselben
PR, also genau in der Reihenfolge, die der Abschnitt darunter vermisst. Der
Satz stand zu diesem Zeitpunkt schon in `main`.

Ungemessen bleibt, **warum** das Eröffnen eines Entwurfs überhaupt eine Absage
auslöst, wo #98 und #99 als Entwurf gar keinen Kommentar bekamen. Dass die
Meldung eine Umgebung verlangt, die der Review offenbar nicht braucht, legt
zwei verschiedene Mechanismen nahe; belegt ist das nicht. Die Einstellungen
liegen nicht in diesem Repo, und dem Link in der Meldung zu folgen wäre eine
Änderung daran, keine Messung.

**Die Lehre wird dadurch nicht kleiner, sondern genauer.** Um 18:42 war dieser
PR wirklich ungeprüft, und das einzige Zeichen dafür war der fehlende
Statuskommentar: `get_reviews` leer wie bei jedem befundlosen Lauf, CI grün,
kein Konflikt. Wer in diesem Fenster gemergt hätte, hätte sich auf ein Signal
gestützt, das nichts sagt. Dass siebzehn Minuten später doch ein Lauf kam,
entlastet nicht — es macht den Fall häufiger, weil die Absage kein Dauerzustand
ist, sondern ein Fenster, das sich wieder schliesst.

**Seit dem 13.11.2026 sagt es ein Marker direkt.** Der Statuskommentar auf
#91 trägt neben dem bekannten `codex-pull-request-review-summary` einen
zweiten, maschinenlesbaren:

```
<!-- codex-review-state:v1 {"code_review":{"commit_sha":"6c0c7f4…",
     "has_any_findings":false,"has_unresolved_findings":false,
     "status":"completed"},"security_review":{…}} -->
```

Damit steht «kein Befund» als Feld da und nicht länger als abwesender
Kommentar. Der Marker ist **nicht rückwirkend**: Derselbe Kommentar auf #85,
am 13.11. erneut abgefragt, führt ihn nach wie vor nicht — er wird beim
Schreiben gesetzt, nicht beim Ausliefern. Wer ihn erwartet, muss also mit
Kommentaren ohne ihn rechnen; das Paar oben bleibt der Rückfall.

Mitgewandert ist die Darstellung: Der Kommentar steckt jetzt in einem
`<details>` mit der Zusammenfassung «Codex Review Summary: ✅ Completed».
Zweimal hat die Form damit in zwei Monaten gewechselt. Wer seine Prüfung an
einen Text bindet statt an ein Feld, baut sie jedes Mal neu.

Was die neun Messungen **nicht** hergeben: dass der Kommentar abgeschafft
wäre. Neun Läufe aus einem Repo sind kein Produktentscheid. Taucht er wieder
auf, ist das kein Widerspruch, sondern das Ende der Spanne.

**Die Laufzeit taugt nicht als Wartezeit.** Derselbe Statuskommentar, von
`created_at` bis `updated_at` — also vom Erscheinen bis zum Umschlagen auf
«Completed»:

| PR | Datum | Start (UTC) | Ende (UTC) | Dauer |
|---|---|---|---|---|
| #73 | 9.9.2026 | 03:53:11 | 03:56:22 | 3 min 11 s |
| #75 | 14.9.2026 | 12:45:11 | 12:45:58 | 47 s |
| #85 | 14.10.2026 | 06:52:58 | 06:53:56 | 58 s |
| #91 | 13.11.2026 | 14:01:54 | 14:02:53 | 59 s |
| #92 | 13.11.2026 | 16:26:07 | 16:27:03 | 56 s |
| #97 | 22.11.2026 | 09:44:13 | 09:45:14 | 1 min 01 s |
| #98 | 22.11.2026 | 18:13:36 | 18:14:28 | 52 s |
| #99 | 22.11.2026 | 18:34:42 | 18:35:41 | 59 s |
| #100 | 22.11.2026 | 18:59:43 | 19:00:38 | 55 s |
| #101 | 24.11.2026 | 03:44:51 | 03:46:11 | 1 min 20 s |

Faktor vier zwischen dem längsten und dem kürzesten, ohne dass sich am Repo
etwas geändert hätte. Acht der zehn Läufe liegen dabei zwischen 47 s und
1 min 01 s; darüber liegen nur #101 mit 1 min 20 s und #73 mit 3 min 11 s.
Diese Häufung ist keine Zusage, sondern die Versuchung: Gerade weil so viele
Messungen so eng beieinanderliegen, liest sich die nächste wie eine Regel —
und #73 zeigt, dass es keine ist. Eine Regel wie «vier Minuten warten, dann
ist es sicher» ist daraus nicht zu bauen; gelesen wird der Status, nicht die
Uhr.

Dass die Tabelle **in place** aktualisiert wird, macht beide Messungen erst
möglich und eine einzelne Abfrage zugleich wertlos: `created_at` bleibt
stehen, nur `updated_at` springt. Wer einmal abfragt, sieht einen Zustand und
weiss nicht, welchen. Auf #92 ist der Wechsel einmal im Lauf mitverfolgt: Im
Marker stand um 16:26:07 noch `"status":"running"` mit
`has_any_findings: null`, um 16:27:03 dann `"completed"` mit `false` — gleiche
Kommentar-ID, unverändertes `created_at`.

**Und zehnmal urteilte Codex erst nach dem Merge.** Gegenübergestellt der
Merge-Zeitpunkt aus `merged_at` und derselbe Statuskommentar, von seinem
Erscheinen bis zum Urteil:

| PR | Merge | Kommentar erscheint | Urteil steht | Merge vor dem Urteil um |
|---|---|---|---|---|
| #73 | 03:54:34 | 03:53:11 | 03:56:22 | 1 min 48 s |
| #75 | 12:45:05 | 12:45:11 | 12:45:58 | 53 s |
| #85 | 06:52:49 | 06:52:58 | 06:53:56 | 1 min 07 s |
| #91 | 14:01:45 | 14:01:54 | 14:02:53 | 1 min 08 s |
| #92 | 16:25:55 | 16:26:07 | 16:27:03 | 1 min 08 s |
| #97 | 09:44:11 | 09:44:13 | 09:45:14 | 1 min 03 s |
| #98 | 18:13:30 | 18:13:36 | 18:14:28 | 58 s |
| #99 | 18:34:39 | 18:34:42 | 18:35:41 | 1 min 02 s |
| #100 | 18:59:31 | 18:59:43 | 19:00:38 | 1 min 07 s |
| #101 | 03:44:43 | 03:44:51 | 03:46:11 | 1 min 28 s |

Zwei Formen: Auf #73 stand die Tabelle sichtbar auf «Running», als gemergt
wurde. In den anderen neun Fällen war der Kommentar zum Merge-Zeitpunkt noch
gar nicht da — #75, #85, #91, #92, #97, #98, #99, #100 und #101 fehlten ihm
zwischen zwei und zwölf Sekunden. Auf #92, #99, #100 und #101 lag der Merge
sogar vor dem *Start* des Laufs — sieben, eine, sieben und fünf Sekunden: Es
gab zum Merge-Zeitpunkt nichts anzusehen, auch nicht für den, der hinsieht.

Was das kostet, ist zweimal belegt. Auf #73 reichte Codex um 03:56:18 ein
Review-Objekt mit einem P2-Befund ein, 1 min 44 s nach dem Merge. Der Befund
war echt und traf genau die Lücke, die der gemergte PR schliessen sollte: Ein
DNS-Ausfall flog an der neuen Ausfall-Erkennung vorbei und hätte weiter das
falsche Issue erzeugt. Behoben wurde er in einem Folge-PR; ohne den Blick in
den geschlossenen PR wäre er in `main` liegengeblieben.

Der zweite Fall ist #101, am 24.11.2026: ein P2-Befund um 03:46:09, 1 min 26 s
nach dem Merge, auf den Absatz weiter oben über die Absage von #100. Er traf
zu — der Schluss «derselbe Head lief später, also war an den Einstellungen
nichts kaputt» ist überdehnt, weil die Einstellungen ausserhalb des Repos
liegen und sich dazwischen geändert haben können. Der Satz war zum Zeitpunkt
des Befunds schon in `main`; korrigiert wurde er im Folge-PR. Zweimal also,
und beide Male traf der nachgereichte Befund genau die Stelle, die der
gemergte PR gerade behandelte.

Für die anderen acht ist **nicht** bekannt, ob es etwas zu finden gab; alle
blieben befundlos. Das ist Glück, keine Entwarnung — die Reihenfolge war
dieselbe. Befunde gab es bisher auf #73 und #101, und beide kamen nach dem
Merge.

Vier Handgriffe daraus:

- **Vor dem Merge auf den Status sehen, nicht auf die Uhr.** Dieselbe Regel
  wie oben, mit dem Zusatz, dass sie vorher gilt und nicht nachher: Eine
  Tabelle auf «Running» ist eine Aufforderung zu warten.
- **Der Status muss dafür erst existieren.** Auf #99 lagen zwischen «ready»
  und Merge zwei Sekunden, und der Statuskommentar erschien drei Sekunden
  *nach* dem Merge. Der Handgriff darüber ist in diesem Ablauf also nicht
  anwendbar — wer den Draft auf «ready» setzt und gleich mergt, hat nichts,
  worauf er sehen könnte; die Aufforderung zu warten kommt zu spät, um
  gelesen zu werden. Zwei Wege wären denkbar: zwischen «ready» und Merge eine
  Minute verstreichen lassen, oder den Review mit `@codex review` auf dem
  offenen PR anstossen, statt ihn am Umschalten hängen zu lassen. Gemessen ist
  keiner von beiden — welcher trägt, ist offen.
- **Wer zum Warten rät, liest vorher `merged_at`.** Am 22.11. und am
  24.11.2026 wurde hier zweimal zum Warten geraten, als der Merge längst
  erfolgt war — beide Male gestützt auf ein leeres `get_comments`. Dessen
  Abwesenheit ist kein Status: Sie sagt, dass gerade kein Kommentar da ist,
  nicht, dass noch Zeit ist. Auf #101 lag der Merge eine Sekunde nach «ready»
  und zwei Sekunden vor der Abfrage, die nichts fand. Der Rat war damit selbst
  der Fehler, vor dem der Abschnitt warnt — eine Ebene höher, weil nicht die
  Uhr gelesen wurde, sondern eine Leerstelle für eine Auskunft genommen.
- **Ein geschlossener PR ist kein Grund, nicht mehr hinzusehen.** Der Lauf
  läuft nach dem Merge weiter und reicht sein Ergebnis auch dann noch ein.

### Wenn zwei Agenten dasselbe tun

Vor dem Anlegen eines Branches mit vorgegebenem Namen prüfen, ob es ihn schon
gibt:

```bash
git ls-remote --heads origin claude/<name> | wc -l
```

Steht dort `1`, arbeitet jemand anderes daran — mit Schreibrecht auf denselben
Ref.

Ein PR mit leerem Diff wird geschlossen, nicht gemergt. Der Test ist
`get_files` auf dem PR: kommt `[]` zurück, ändert er nichts. Ein grüner Check
sagt dazu nichts — die CI prüft den Head, nicht die Differenz zur Basis.

Am 21.8.2026 liefen zwei Sessions dieselbe Aufgabe über 45 Repos, auf den
Branches `claude/codex-review-audit-templates-9sn6mx` und
`claude/codex-review-audit-7ioh56`. Wo die eine zuerst nach `main` kam, wurde
`main` in den Branch der anderen gemergt und der add/add-Konflikt zugunsten
von `main` aufgelöst. Übrig blieben 14 PRs, die durch sämtliche Gates grün
liefen und nichts enthielten; sie wurden gemergt und hinterliessen leere
Merge-Commits. Mit den zwei Folge-PRs, die aus demselben Grund gegenstandslos
waren, waren 16 der 59 PRs jenes Tages reine Reibung.

Dieselbe Klasse wie der handgeschriebene Stub, der denselben Feldnamen annahm
wie der Code: Nichts ist rot, weil nichts geprüft wird, worauf es ankommt.

## Teil 2 — Dieses Repo

### ruff — genau eine Quelle

Der Pin steht in `pyproject.toml`,
`[project.optional-dependencies].dev`, und sonst nirgends — die Version dort
nachlesen, nicht hier: `tests/test_ruff_pin_doku.py` hält sie aus dieser
Datei draussen.
`pip install -e ".[dev]"` liefert damit die Version, mit der die CI lintet;
Anheben genügt an dieser einen Stelle. Eine `.pre-commit-config.yaml` gibt
es nicht.

**Keine zweite Version in die Workflows schreiben.** `ci.yml` hatte einen
Schritt `pip install ruff==0.16.1` nach dem dev-Install — der gewinnt gegen
pyproject, ohne dass etwas rot wird. `tests/test_werkzeug_versionen.py`
fällt, wenn hier wieder eine Spanne steht oder ein Workflow eine zweite
Version setzt.

Die `0.16.1` in diesem Absatz ist ein **Zitat aus der Vergangenheit** und
wird beim Anheben des Pins nicht mitgezogen. Sie nennt, was damals wirklich
in `ci.yml` stand; die Historie gibt für diesen Schritt keine andere Zahl her.
Am 30.8.2026 ist sie trotzdem mitgewandert — Commit `1ae7b94` hob den Pin auf
0.16.3 und ersetzte sie gleich mit, womit der Absatz eine Behauptung über
`ci.yml` aufstellte, die nie zutraf. Ein Suchen-und-Ersetzen über diese Datei
trifft also zwei verschiedene Arten von Zahl: die beiden oben, die den
aktuellen Pin wiedergeben, und diese eine, die es nicht tut.

Vor dem Lauf `ruff --version` prüfen: ein älteres ruff früher im `PATH`
schlägt den Pin, ohne dass der Install etwas meldet.

### Gate-Befehle (wörtlich aus `ci.yml`)

```
python scripts/check_ruff_pin.py
ruff check src/ tests/ scripts/
ruff format --check src/ tests/ scripts/
PYTHONPATH=src pytest tests/ -m "not live" -v
python scripts/check_version_sync.py
```

Matrix: Python 3.11 / 3.12 / 3.13. Alle vier laufen in einem Job auf allen
drei Feldern — keine `if: matrix.python-version`-Ausnahme, kein zweiter
lint-Job. Ein grünes 3.13 heisst hier also wirklich, dass alles auf 3.13 lief.
(Im Portfolio nicht selbstverständlich: `swiss-food-safety-mcp` gated zwei
Gates auf 3.11, `swiss-housing-mcp` und `bakom-mcp` fahren ihre ruff-Gates in
einem eigenen 3.11-Job.)

Ein `fail-fast: false` steht **nicht** da: Eine rote 3.11 bricht 3.12 und 3.13
ab, bevor sie etwas sagen. Ein einzelnes rotes Feld heisst dann «der Rest kam
nicht dazu», nicht «nur dort kaputt».

### Live-Tests — geplant, DRIFT-005 erfüllt

`.github/workflows/live.yml` läuft per cron `17 3 * * *` (UTC) plus
`workflow_dispatch`; `ci.yml` schliesst dieselben Tests mit `-m "not live"`
aus. Live-Tests sind hier also nicht bloss ausgeschlossen, sondern haben
einen eigenen geplanten Lauf.

```
PYTHONPATH=src pytest tests/ -m live --run-live -v
```
