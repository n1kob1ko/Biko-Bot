# Biko Helfer: KI-Assistent fürs Handy (Deutsch und 中文)

Ein einfacher KI-Helfer, vor allem für ältere Menschen, die das Handy schon für Telefonieren,
Apple Pay oder WeChat-Sprachnachrichten nutzen, aber noch keine KI. Biko ist der gleiche gelbe Vogel
wie in der Trading-App, das Programm hier ist aber komplett getrennt vom Trading-Bot.

## Was er kann (Version 1)

| Bereich | Was passiert |
|---|---|
| **Reden / 聊天** | Fragen stellen oder einfach plaudern. Mit Sprachdienst redet man wie am Telefon: einmal auf den großen gelben Knopf tippen, dann hört Biko durchgehend zu, antwortet mit Stimme, und man kann ihm jederzeit ins Wort fallen. Der rote Knopf legt auf. Tippen geht genauso. Antworten kann man sich vorlesen lassen, mit Sprachdienst in einer natürlichen Stimme. Biko sucht bei Bedarf im Internet (Angebote und Deals, Öffnungszeiten, Wetter). Er antwortet in der Sprache, in der man ihn anspricht. |
| **Verlauf / 记录** | Frühere Gespräche zum Nachlesen und Weiterreden, dazu der Knopf "Neues Gespräch". |
| **Einstellen / 设置** | Für die Familie: Name und Du/Sie, nachsehen und löschen, woran Biko erinnert und was er über die Person weiß, Schriftgröße, immer vorlesen. |

**Erinnerungen haben keinen eigenen Bereich und kein Formular.** Man sagt es Biko einfach im Gespräch:

- "Erinnere mich jeden Tag um 8 an die Herztablette." / "每天早上八点提醒我吃药。"
- "Erinnere mich morgen um 15 Uhr an den Arzt." oder "in 20 Minuten an den Herd."
- "Woran erinnerst du mich?" und "Vergiss die Erinnerung an die Tablette."

Biko schreibt es sich im Hintergrund selbst auf und bestätigt in einem Satz. Unter seiner Antwort steht klein
"Gemerkt" mit Tag und Uhrzeit, damit man sieht, dass es wirklich notiert ist. Zur Uhrzeit erscheint ein großer
Hinweis mit Ton, bis "Erledigt" gedrückt wird. Fehlt die Uhrzeit, fragt Biko nach. In "Einstellen" steht nur
eine Liste zum Nachsehen und Löschen (Löschen fragt zuerst nach).

**Biko merkt sich auch, was man über sich erzählt**, ohne Formular: "Ich hab Diabetes", "Mein Enkel heißt Niko",
"Ich mag keinen Fisch". Unter der Antwort steht klein "Weiß ich jetzt: ...", und ab dann denkt Biko in jedem
Gespräch daran (zum Beispiel bei "Darf ich Kuchen essen?"). "Vergiss das" streicht es wieder. Passwörter, PINs und
Kontonummern schreibt er nie auf. In "Einstellen" steht die Liste "Das weiß Biko über dich" zum Nachsehen und
Löschen. Die früheren Felder Diät und Notizen übernimmt der Server beim ersten Start einmal in diese Liste.

**Biko meldet sich von selbst: die Morgenrunde.** "Meld dich jeden Morgen um 8" (oder "每天早上八点跟我打招呼")
stellt sie ein, "Hör auf mit der Morgenrunde" stellt sie ab. Kurz vor der Zeit schreibt Biko am Server
(Hintergrund-Faden `hausmeister`) eine kurze Begrüßung mit dem Wetter in Wien, zwei, drei Nachrichten, die die Person
interessieren (aus dem, was er über sie weiß), und ihren Terminen des Tages, als eigenes Gespräch "Morgenrunde".
Dafür nimmt er das günstigere Modell mit Websuche (ein paar Cent am Tag). Zur Uhrzeit liest er sie vor: in der offenen
App, aus der Android-Blase oder nach einem Tipp auf die Mitteilung "Guten Morgen!". Antwortet man, redet man im
selben Gespräch weiter. `GET /api/morgenrunde` liefert Uhrzeit und die Runde von heute (`?jetzt` schreibt sie gleich,
falls sie fällig ist und noch fehlt). Die Android-App stellt für Erinnerungen und Morgenrunde Wecker, damit sie auch
kommen, wenn die App zu ist (siehe `android/README.md`).

**Nachrichten für andere** gehen genauso: "Schreib Anna, dass ich am Sonntag komme." Biko schreibt den fertigen
Text und stellt ihn unter seine Antwort, mit einem Knopf "Kopieren" (und "Senden mit", wenn das Handy das kann).
Danach fügt man ihn in WeChat, WhatsApp oder SMS ein. Biko verschickt selbst nichts. "Mach sie kürzer" oder
"lieber mit Sie" ändert den Text im selben Gespräch.

**Foto von einem Brief:** Links im Eingabefeld ist ein Kamera-Knopf. Foto von einem Brief, einer Rechnung, einer
Packungsbeilage oder einem Schild machen, und Biko erklärt es: von wem, worum es geht, was zu tun ist und bis wann, und ob es
nach Betrug aussieht. Steht nichts im Eingabefeld, fragt die App von selbst "Was steht da?". Die App verkleinert das Foto
auf 1600 Pixel und schickt es wie das Bildschirmfoto der Android-App an `POST /api/bildschirm?foto`; es gilt 5 Minuten für
die nächsten Fragen ("Was muss ich tun?") und wird nicht gespeichert. Mit Foto antwortet immer das stärkere Modell.

**Einkaufsliste und Notizen:** "Schreib Milch auf die Einkaufsliste", "Was steht drauf?", "Merk dir, der Schlüssel ist bei
Frau Novak". Biko führt dafür Listen (`listen.json`, Werkzeug `liste_aendern`): "Einkaufen", "Notizen" und was die Person
sonst braucht. Was draufsteht, steht im Hinweis der App. Mit `liste_zeigen` stellt er eine Liste als Karte unter die Antwort:
große Zeilen, ein Tipp hakt ab und nimmt es weg (`POST /api/liste/weg`), dazu "Kopieren". Bleibendes über die Person selbst
bleibt im Gedächtnis, nicht auf einer Liste.

**Anrufen, WhatsApp und SMS:** "Ruf meinen Sohn an" stellt einen großen gelben Knopf "Peter anrufen" unter die Antwort
(`tel:`-Link, Werkzeug `anruf_zeigen`). Die Nummer kennt Biko aus dem, was er sich über die Person gemerkt hat; kennt er sie
nicht, fragt er und merkt sie sich. Er erfindet nie eine Nummer und ruft nie selbst an. Bei Notfällen zeigt er den Knopf für
144. Sagt die Person "auf WhatsApp" oder "als SMS", hat die Nachricht einen Knopf, der WhatsApp (`wa.me`) oder SMS mit dem
fertigen Text öffnet; man tippt dort nur noch auf Senden. In der Android-Blase gehen Telefon, WhatsApp oder SMS gleich von
selbst auf, sobald Biko ausgeredet hat. WeChat kann keinen Text vorgeben: dort bleibt Kopieren und Einfügen.

**Angebote und Links:** Bei Fragen nach Angeboten sucht Biko zuerst selbst und gründlich (mehrere Suchen, er darf
Trefferseiten auch öffnen). Adressen schreibt er nie in den Text, sondern stellt sie als großen Knopf unter die
Antwort. Findet er nichts Genaues, sagt er das in einem Satz und stellt den Link zum aktuellen Prospekt des
Geschäfts ins Gespräch, damit man selbst schauen kann. Nur `https`-Adressen werden zu einem Knopf.

**Gespräche:** Jede Sitzung ist ein eigenes Gespräch. Öffnet man die App am selben Tag wieder, steht das letzte
Gespräch wieder da und man redet einfach weiter. An einem neuen Tag begrüßt Biko von vorn, das alte Gespräch steht
dann im Bereich "Verlauf". Dort kann man jedes Gespräch wieder öffnen oder löschen (Löschen fragt zuerst nach).
"Neues Gespräch" gibt es im Verlauf und oben neben dem kleinen Biko. Es bleiben die letzten 40 Gespräche.

Grundsatz für alles Weitere: **Funktionen laufen über das Gespräch, nicht über Formulare.**

Technisch: Biko hat dafür vier Werkzeuge in `server.py`, die Claude selbst aufruft: `erinnerung_merken`,
`erinnerung_loeschen`, `nachricht_zeigen` und `link_zeigen`. Der Server prüft jede Eingabe (Uhrzeit, Datum nicht in
der Vergangenheit, höchstens 30 Erinnerungen, Links nur mit `https`). Mit jeder Antwort bekommt die App, was Biko
gerade getan hat: gemerkt, gestrichen, Nachricht geschrieben, Links. Das steht auch im gespeicherten Gespräch
(`gespraeche.json`), damit es beim Wiederöffnen wieder da ist. Zum Suchen nutzt Biko die Websuche und das Öffnen
von Seiten der Claude-API (`web_search`, `web_fetch`). Im Server-Log steht pro Antwort nur, welche Werkzeuge
benutzt wurden, nie der Inhalt.

Oben rechts wechselt ein kleines Menü die ganze Oberfläche zwischen Deutsch und Chinesisch. Beim ersten Öffnen
nimmt die App die Sprache des Handys. Sie folgt auch dem hellen oder dunklen Modus des Handys.

Biko selbst zeigt, was gerade passiert: er winkt zur Begrüßung, lauscht beim Sprechen, tippt beim Nachdenken
und freut sich, wenn eine Erinnerung erledigt ist. Bei jeder Antwort liest er die letzten 30 Nachrichten des
offenen Gesprächs mit.

### Bewusste Grenzen

- **Gesundheit:** Biko erinnert und gibt Hinweise zur Diät, die er sich im Gespräch gemerkt hat, aber keine Diagnosen und keine Änderungen an Medikamenten. Bei Notfällen nennt er 144, bei Beschwerden 1450, bei Krisen die Telefonseelsorge 142.
- **Ehrlich KI:** Biko sagt, dass er eine KI ist, und ermutigt zu Kontakt mit Familie und Freunden.
- **Betrug:** Er warnt bei Enkeltrick, falscher Polizei oder Bank, Links in SMS.
- **Erinnerungen brauchen die offene App.** Version 1 kann das Handy nicht "aufwecken", wenn die Seite zu ist. Für wichtige Medikamente zusätzlich den Handy-Wecker stellen. Echte Push-Nachrichten sind der nächste Schritt.
- **Stimme und Zuhören ohne Sprachdienst** (siehe unten) nutzen das, was der Browser am Handy mitbringt: die Stimme klingt dann künstlich, und verstanden wird nur die Sprache, die in der App eingestellt ist. Geht das Zuhören auf einem Handy gar nicht, funktioniert immer die Mikrofon-Taste der Tastatur.

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

## Stimme und Zuhören: der Sprachdienst

Damit Biko natürlich klingt und Deutsch und Chinesisch versteht, ohne dass man etwas umstellt, nutzt er
[ElevenLabs](https://elevenlabs.io). Dafür braucht es einen zweiten Schlüssel:

1. Bei ElevenLabs ein Konto anlegen und unter "API Keys" einen Schlüssel erstellen.
2. Den Schlüssel am Server als `ELEVENLABS_API_KEY` eintragen (`.env` oder die Variablen des Hosters), neu starten.

Mehr ist nicht nötig. Solange kein Schlüssel eingetragen ist, läuft alles wie bisher mit der Stimme und der
Spracherkennung des Browsers.

| Variable | Bedeutung |
|---|---|
| `ELEVENLABS_API_KEY` | schaltet den Sprachdienst ein |
| `SPRACH_STIMME` | optional: die "Voice ID" einer bestimmten Stimme aus dem ElevenLabs-Konto. Leer: die erste Stimme des Kontos. Für Deutsch und Chinesisch am besten eine Stimme wählen, die beides gut spricht, und sie in "My Voices" speichern. |
| `SPRACH_MODELL` | optional: Standard `eleven_v4_turbo` (schnell und günstig). `eleven_v4` klingt noch natürlicher, kostet das Doppelte und braucht länger. |

So läuft das **Reden wie am Telefon** ab (seit November 2026):

1. Einmal aufs Mikrofon tippen. Die App holt sich beim eigenen Server einen Zugang für 15 Minuten
   (`POST /api/live-zugang`) und schickt das Mikrofon damit direkt an das Live-Zuhören von ElevenLabs
   (`scribe_v2_realtime`). Der Schlüssel selbst bleibt am Server.
2. Was man sagt, steht schon beim Sprechen im Eingabefeld. Nach einer Sekunde Pause ist der Satz fertig und geht
   von selbst ab. Wer kurz absetzt und gleich weiterredet, wird nicht abgeschnitten. Deutsch und Chinesisch
   erkennt der Dienst selbst.
3. Bikos Antwort kommt stückweise (`POST /api/chat` mit `"strom": true`). Sobald der erste Satz fertig ist, spricht
   Biko ihn (`POST /api/stimme`, der Ton kommt roh und spielt sofort, Satz für Satz lückenlos hintereinander).
   Am Telefon antwortet Biko kürzer und ohne Listen. Muss er suchen, sagt er vorher "Moment, ich schau kurz nach".
4. Redet man dazwischen, hört Biko sofort auf und hört zu. Seine eigene Stimme aus dem Lautsprecher zählt dabei
   nicht (das Mikrofon filtert sie, und Wörter, die er gerade selbst sagt, werden nicht als Unterbrechung gewertet).
5. Der rote Knopf legt auf. Nach 90 Sekunden Stille oder wenn man die App weglegt, legt Biko selbst auf.
   Reißt die Verbindung ab, verbindet die App still neu.

Geht das Live-Zuhören an einem Handy nicht, nimmt Biko wie früher Satz für Satz auf (siehe unten).

Beim **Vorlesen** schickt die App den Text an den eigenen Server (`POST /api/vorlesen`), der holt
den Ton bei ElevenLabs und gibt ihn als MP3 zurück. Dieselbe Antwort gleich nochmal anhören kostet nichts, der Ton
der letzten Antworten bleibt in der offenen App im Speicher. Beim **Sprechen** nimmt das Handy auf, bis man fertig ist (eine Pause von
knapp zwei Sekunden reicht, oder nochmal auf den Knopf tippen, spätestens nach einer Minute; wer 8 Sekunden lang
nichts sagt, bekommt einen Hinweis), die Aufnahme geht
über den Server (`POST /api/zuhoeren`) an ElevenLabs und kommt als Text zurück. Der Dienst erkennt die Sprache
selbst. Fällt er aus, liest die Stimme des Browsers vor, statt dass es still bleibt. Der Schlüssel bleibt am
Server, das Handy sieht ihn nie.

Noch nicht am echten Gerät geprüft: Safari am iPhone (Ton nach dem Sprechen, Aufnahme als mp4, Lautstärke und
Echo beim Reden wie am Telefon über den Lautsprecher).

## Kosten

Biko wählt das Modell pro Frage selbst (`modell_fuer` in `server.py`): Plaudern und einfache Fragen gehen an
`claude-sonnet-5-5` (halb so teuer, antwortet schneller), Wichtiges an `claude-opus-5-5`. Wichtig heißt: ein
Bildschirmfoto ist dabei, die Frage ist lang (über 400 Zeichen) oder es geht um Briefe, Ämter, Geld, Betrug oder
Gesundheit (Wortliste `WICHTIG`, Deutsch und Chinesisch). Im Railway-Log steht pro Antwort, welches Modell es war.
Ändern lassen sich beide über `ASSISTENT_MODELL` (stark) und `ASSISTENT_MODELL_EINFACH` (günstig), etwa
`ASSISTENT_MODELL_EINFACH=claude-haiku-5-5` für noch weniger Kosten.

**Zwischenspeicher (Prompt Caching):** Was bei jeder Frage gleich bleibt, kommt aus dem Zwischenspeicher von
Anthropic und kostet dann nur einen Bruchteil (Sonnet 0,10 $, Opus 0,20 $ pro Million statt 2 bzw. 4 $):
- Die Anleitung (`SYSTEM`) bleibt Wort für Wort gleich. Was sich ändert (Uhrzeit, Erinnerungen, Wissen, "redet wie am
  Telefon", Bildschirmfoto), steht im Hinweis der App (`hinweis()`) direkt vor der Frage und wird nicht gespeichert.
- Das Ende des bisherigen Gesprächs ist markiert, das obere `cache_control` nimmt Suchergebnisse und Werkzeug-Runden
  innerhalb einer Antwort mit. Der Anfang eines langen Gesprächs rückt in Zehnerschritten weiter (29 bis 38 Nachrichten),
  damit er gleich bleibt.
- Ein Bildschirmfoto geht nur bei der ersten Frage danach mit und steht dann im Verlauf. Solange es gilt (5 Minuten),
  sieht Biko es weiter, es kommt aber aus dem Zwischenspeicher.
- Kurze Sätze am Anfang einer Antwort ("Moment, ich schau kurz nach.") merkt sich der Server als fertigen Ton
  (die letzten 100) und spricht sie beim nächsten Mal ohne ElevenLabs.

**Echte Zahlen:** Im Railway-Log steht nach jeder Antwort eine Zeile wie
`Claude (claude-sonnet-5-5): 1 Anfragen, ... | Eingabe 5500 Tokens (davon 4000 aus dem Zwischenspeicher, ...), Ausgabe 200,
Suchen 1, Kosten 1.57 US-Cent, heute bisher 23.4 US-Cent bei 17 Antworten`. Die Tagessummen (KI in Dollar, Zahl der
Antworten, vorgelesene Zeichen) stehen in `kosten.json` am Volume. Die Preise stehen in `PREISE` in `server.py`; die
Abrechnung in der Anthropic-Konsole ist die verbindliche Zahl.

Der Sprachdienst kostet extra (Stand November 2026, laut Preisliste von ElevenLabs): Vorlesen etwa 0,04 $ pro
1.000 Zeichen, eine Antwort mit 300 Zeichen also grob 1 Cent. Zuhören etwa 0,22 $ pro Stunde Aufnahme, das fällt
kaum ins Gewicht. Beim Reden wie am Telefon zählt die ganze Zeit, in der das Gespräch offen ist (das Live-Zuhören
wird nach Dauer abgerechnet), deshalb legt Biko nach 90 Sekunden Stille selbst auf. Im kostenlosen Tarif sind rund 10.000 Zeichen im Monat dabei, das reicht zum Ausprobieren.
"Antworten immer laut vorlesen" in den Einstellungen liest jede Antwort vor und kostet entsprechend mehr.

## Daten

Alles liegt im Datenordner des Servers (`DATA_DIR`, mit Docker `assistent/daten/`): `profil.json`,
`erinnerungen.json`, `wissen.json`, `listen.json`, `morgenrunde.json`, `kosten.json`, `gespraeche.json` (die letzten 40 Gespräche). Der eine Verlauf der ersten Version
(`verlauf.json`) wird beim ersten Start als ein Gespräch übernommen. Die Texte gehen zum Beantworten an die
Claude-API von Anthropic. Mit Sprachdienst gehen außerdem die vorgelesenen Texte und die Aufnahmen aus dem
Mikrofon an ElevenLabs. Am eigenen Server wird kein Ton gespeichert. "Alle Gespräche vergessen" in den Einstellungen löscht den ganzen
Verlauf, einzelne Gespräche löscht man im Bereich "Verlauf". Das Server-Log enthält keine Inhalte.

## Eine Person pro Installation

Es gibt ein Profil und einen gemeinsamen Verlauf. Für eine zweite Person den Ordner kopieren und mit anderem Port
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

Die Browser-Tests starten den echten Server mit einer falschen KI und einem falschen Sprachdienst
(`tests/falscher_server.py`) und bedienen die App wie auf einem iPhone, mit einem falschen Mikrofon. Playwright einmalig: `npm install --no-save playwright && npx playwright install chromium`.

### Aufbau der Oberfläche (`web/`, kein Build-Schritt)

| Datei | Inhalt |
|---|---|
| `index.html` | Seitenaufbau und die Icons (Phosphor, MIT) als eingebettete Sammlung |
| `style.css` | Aussehen, hell und dunkel, alle Maße und Farben als Variablen |
| `texte.js` | alle Texte auf Deutsch und Chinesisch |
| `logik.js` | reine Logik ohne Browser (fällige Erinnerung, "wann" in Worten, weiterreden oder neu beginnen, sichere Links, Knopfart, wann eine Aufnahme zu Ende ist, Gummiband, Flugbogen) |
| `bewegung.js` | alle Bewegungen an einer Stelle |
| `app.js` | Verhalten: Sprache, Reden (mit "Gemerkt", Nachricht zum Kopieren und Links unter der Antwort), Vorlesen und Aufnehmen, Verlauf, fällige Erinnerung, Einstellungen |
| `biko.js`, `biko.css` | das Maskottchen aus der Trading-App, dazu die Stimmungen "hört zu" und "ist da" |
| `stille.mp3` | eine Viertelsekunde Stille: damit "weckt" die App beim ersten Antippen den Ton am iPhone |
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
| 11 | Auf geht es vom Auslöser aus | Sprachmenü am Knopf |
| 12 | Zu geht es zum Auslöser zurück | dieselbe Bewegung rückwärts |
| 13 | Nichts federt | keine Kurven mit Überschwingen |
| 14 | Solange der Finger hält, wird nichts nachgezogen | Schalter "immer vorlesen" folgt beim Ziehen direkt (`schalterZiehen`) |
| 15 | Ausgänge sind 20 % kürzer | `--t-aus`, `ausgang()` |
| 16 | Alt und Neu überlappen kurz | Bereichswechsel, Vorschläge beim ersten Senden (`geist`) |
| 17 | Masken für Aufdecken und Farbwechsel | Nachricht, die Biko ins Gespräch stellt (`aufdecken`), Schriftgröße (`clip-path`) |
| 18 | Symbole blenden mit Unschärfe über | `.wechsel` (Mikrofon, Senden, Stopp, Haken) |
| 19 | Gummiband über die Grenze hinaus | Schalter über sein Ende hinaus ziehen (`gummiband`) |
| 20 | Dasselbe Element wandert, statt zwei zu tauschen | ein Kissen in der Leiste, ein Biko im Reden-Bereich |

Bei "Bewegung reduzieren" am Handy bleibt von allem nur das Ein- und Ausblenden.
