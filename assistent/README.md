# Biko Helfer: KI-Assistent fürs Handy (Deutsch und 中文)

Ein einfacher KI-Helfer, vor allem für ältere Menschen, die das Handy schon für Telefonieren,
Apple Pay oder WeChat-Sprachnachrichten nutzen, aber noch keine KI. Biko ist der gleiche gelbe Vogel
wie in der Trading-App, das Programm hier ist aber komplett getrennt vom Trading-Bot.

## Was er kann (Version 1)

| Bereich | Was passiert |
|---|---|
| **Reden / 聊天** | Fragen stellen oder einfach plaudern. Der große gelbe Knopf ist ein Mikrofon wie bei einer WeChat-Sprachnachricht: drücken, sprechen, der Satz wird von selbst abgeschickt. Tippen geht genauso. Antworten kann man sich vorlesen lassen. Biko sucht bei Bedarf im Internet (Angebote und Deals, Öffnungszeiten, Wetter). Er antwortet in der Sprache, in der man ihn anspricht. |
| **Nachricht / 消息** | Kurz sagen, an wen und was. Biko schreibt eine nette Nachricht, die man kopiert und in WeChat, WhatsApp oder SMS einfügt. |
| **Erinnern / 提醒** | Uhrzeit und Text (z. B. Tablette). Zur Uhrzeit erscheint ein großer Hinweis mit Ton, bis "Erledigt" gedrückt wird. Löschen fragt zuerst nach. |
| **Einstellen / 设置** | Für die Familie: Name, Diät-Regeln ("darf ich das essen?"), Notizen, Schriftgröße, immer vorlesen. |

Oben rechts wechselt ein kleines Menü die ganze Oberfläche zwischen Deutsch und Chinesisch. Beim ersten Öffnen
nimmt die App die Sprache des Handys. Sie folgt auch dem hellen oder dunklen Modus des Handys.

Biko selbst zeigt, was gerade passiert: er winkt zur Begrüßung, lauscht beim Sprechen, tippt beim Nachdenken
und freut sich, wenn eine Erinnerung erledigt ist. Jedes Öffnen beginnt mit dem Startbild; Biko weiß trotzdem
noch, worüber zuletzt gesprochen wurde (die letzten 30 Nachrichten, bis "Gespräch vergessen" gedrückt wird).

### Bewusste Grenzen

- **Gesundheit:** Biko erinnert und gibt Hinweise zur hinterlegten Diät, aber keine Diagnosen und keine Änderungen an Medikamenten. Bei Notfällen nennt er 144, bei Beschwerden 1450, bei Krisen die Telefonseelsorge 142.
- **Ehrlich KI:** Biko sagt, dass er eine KI ist, und ermutigt zu Kontakt mit Familie und Freunden.
- **Betrug:** Er warnt bei Enkeltrick, falscher Polizei oder Bank, Links in SMS.
- **Erinnerungen brauchen die offene App.** Version 1 kann das Handy nicht "aufwecken", wenn die Seite zu ist. Für wichtige Medikamente zusätzlich den Handy-Wecker stellen. Echte Push-Nachrichten sind der nächste Schritt.
- **Sprechen** nutzt die Spracherkennung des Browsers. Geht sie auf einem Handy nicht, funktioniert immer die Mikrofon-Taste der Tastatur.

## Installieren

Der Helfer läuft gerade auf keinem Server (der alte Hetzner-Server ist gelöscht). Er braucht nur einen Rechner
mit Docker, der immer an ist, zum Beispiel einen kleinen Linux-Server.

```bash
git clone https://github.com/n1kob1ko/biko-bot.git && cd biko-bot/assistent
cp .env.example .env
nano .env                      # ANTHROPIC_API_KEY und APP_PASSWORT eintragen
docker compose up -d --build   # läuft dann auf Port 8092
```

Den API-Schlüssel gibt es auf https://console.anthropic.com unter "API Keys". Dort unbedingt ein
**Monatslimit** setzen (z. B. 10 €), dann kann nichts teuer werden.

**Fürs Handy braucht es https**, sonst erlaubt der Browser kein Mikrofon. Zwei Wege:

- Mit Tailscale (nur eigene Geräte): `sudo tailscale serve --bg --https=8443 8092`, dann am Handy
  `https://<name-des-servers>.<tailnet>.ts.net:8443` öffnen.
- Für Handys ohne Tailscale (z. B. Verwandte): `sudo tailscale funnel --bg --https=8443 8092` macht die Seite
  öffentlich erreichbar. Dann schützt nur das Passwort (5 Fehlversuche, dann 15 Minuten Sperre), also ein langes wählen.

Am Handy Passwort eingeben und "Zum Home-Bildschirm" wählen.

## Kosten

Pro Frage ohne Internetsuche grob 1 Cent, mit Suche grob 5 bis 10 Cent (Standardmodell `claude-opus-5-5`).
Das sind Schätzungen, die echten Zahlen stehen in der Anthropic-Konsole. Wer sparen will, setzt in der `.env`
`ASSISTENT_MODELL=claude-haiku-5-5` (viel günstiger, etwas weniger schlau).

## Daten

Alles liegt in `assistent/daten/` am eigenen Server: `profil.json`, `erinnerungen.json`, `verlauf.json`
(die letzten 30 Nachrichten). Die Texte gehen zum Beantworten an die Claude-API von Anthropic, sonst nirgends hin.
"Gespräch vergessen" in den Einstellungen löscht den Verlauf. Das Server-Log enthält keine Inhalte.

## Eine Person pro Installation

Version 1 hat ein Profil und ein Gespräch. Für eine zweite Person den Ordner kopieren und mit anderem Port
starten (`HELFER_PORT=8093` in der `.env`, anderer `container_name`). Mehrere Personen in einer Installation
sind ein möglicher nächster Schritt.

## Entwickeln und testen

```bash
cd assistent
pip install -r requirements.txt
python -m unittest test_server                                        # Server, ohne echte KI
node --test tests/logik.test.js                                       # Logik der Oberfläche
node --test --test-concurrency=1 tests/e2e.test.js                    # Oberfläche im Browser (braucht Playwright)
DATA_DIR=./daten APP_PASSWORT=test ANTHROPIC_API_KEY=... python server.py   # http://127.0.0.1:8092
```

Die Browser-Tests starten den echten Server mit einer falschen KI (`tests/falscher_server.py`) und bedienen die
App wie auf einem iPhone. Playwright einmalig: `npm install --no-save playwright && npx playwright install chromium`.

### Aufbau der Oberfläche (`web/`, kein Build-Schritt)

| Datei | Inhalt |
|---|---|
| `index.html` | Seitenaufbau und die Icons (Phosphor, MIT) als eingebettete Sammlung |
| `style.css` | Aussehen, hell und dunkel, alle Maße und Farben als Variablen |
| `texte.js` | alle Texte auf Deutsch und Chinesisch |
| `logik.js` | reine Logik ohne Browser (fällige Erinnerung, Knopfart, Gummiband, Flugbogen) |
| `bewegung.js` | alle Bewegungen an einer Stelle |
| `app.js` | Verhalten: Sprache, Reden, Nachricht, Erinnerungen, Einstellungen |
| `biko.js`, `biko.css` | das Maskottchen aus der Trading-App, dazu die Stimmungen "hört zu" und "ist da" |
| `fonts/` | Atkinson Hyperlegible Next (für schwache Augen gezeichnet, OFL). Chinesisch nutzt die Schrift des Handys. |

Zielgruppe, Ton und Gestaltungsregeln stehen in [PRODUCT.md](PRODUCT.md).

### Bewegungsregeln

Die Oberfläche folgt 20 festen Regeln. Wer etwas ändert, hält sie bitte ein:

| Nr. | Regel | Wo |
|---|---|---|
| 1 | Eingänge bremsen ab (ease-out) | `--ease-out` in `style.css`, `AB` in `bewegung.js` |
| 2 | Aufklappmenüs in 150 bis 250 ms | Sprachmenü: 200 ms auf, 160 ms zu |
| 3 | Listenzeilen kommen je 30 ms versetzt | `.kommt .reihe` mit `--i` |
| 4 | Drücken verkleinert auf 0,97 | `.druck` und alle anderen Tippflächen |
| 5 | Wandernde Knöpfe dehnen sich um 12 % | Schalter-Knauf und Kissen der Leiste (`dehnung`) |
| 6 | Details setzen sich versetzt danach | `.kommt .detail` |
| 7 | Dinge fliegen auf einem Bogen | Frage fliegt vom Feld oder Vorschlag in den Verlauf (`flug`, `bogen`) |
| 8 | Erfolg pulsiert einmal | Kopiert, Gespeichert, Erledigt (`puls`) |
| 9 | Wege auf dem Bildschirm laufen ease-in-out | Kissen, Knauf, Flug, Biko groß nach klein |
| 10 | Aufklappendes beginnt bei 0,95 | Sprachmenü |
| 11 | Auf geht es vom Auslöser aus | Sprachmenü am Knopf, Blatt aus dem Plus-Knopf |
| 12 | Zu geht es zum Auslöser zurück | dieselben Bewegungen rückwärts |
| 13 | Nichts federt | keine Kurven mit Überschwingen |
| 14 | Solange der Finger hält, wird nichts nachgezogen | Blatt folgt beim Ziehen direkt |
| 15 | Ausgänge sind 20 % kürzer | `--t-aus`, `ausgang()` |
| 16 | Alt und Neu überlappen kurz | Bereichswechsel, Vorschläge beim ersten Senden (`geist`) |
| 17 | Masken für Aufdecken und Farbwechsel | fertige Nachricht (`aufdecken`), Schriftgröße (`clip-path`) |
| 18 | Symbole blenden mit Unschärfe über | `.wechsel` (Mikrofon, Senden, Stopp, Haken) |
| 19 | Gummiband über die Grenze hinaus | Blatt nach oben ziehen (`gummiband`) |
| 20 | Dasselbe Element wandert, statt zwei zu tauschen | ein Kissen in der Leiste, ein Biko im Reden-Bereich |

Bei "Bewegung reduzieren" am Handy bleibt von allem nur das Ein- und Ausblenden.
