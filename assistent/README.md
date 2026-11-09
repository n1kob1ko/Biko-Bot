# Biko Helfer: KI-Assistent fürs Handy (Deutsch und 中文)

Ein einfacher KI-Helfer, vor allem für ältere Menschen, die das Handy schon für Telefonieren,
Apple Pay oder WeChat-Sprachnachrichten nutzen, aber noch keine KI. Biko ist der gleiche gelbe Vogel
wie in der Trading-App, das Programm hier ist aber komplett getrennt vom Trading-Bot.

## Was er kann (Version 1)

| Bereich | Was passiert |
|---|---|
| **Reden / 聊天** | Fragen stellen oder einfach plaudern. Tippen oder auf "Sprechen" drücken, Antworten kann man sich vorlesen lassen. Biko sucht bei Bedarf im Internet (Angebote und Deals, Öffnungszeiten, Wetter). Er antwortet in der Sprache, in der man ihn anspricht. |
| **Nachricht / 消息** | Kurz sagen, an wen und was. Biko schreibt eine nette Nachricht, die man kopiert und in WeChat, WhatsApp oder SMS einfügt. |
| **Erinnern / 提醒** | Uhrzeit und Text (z. B. Tablette). Zur Uhrzeit erscheint ein großer Hinweis mit Ton, bis "Erledigt" gedrückt wird. |
| **Einstellen / 设置** | Für die Familie: Name, Diät-Regeln ("darf ich das essen?"), Notizen, Schriftgröße, immer vorlesen. |

Oben rechts wechselt ein Knopf die ganze Oberfläche zwischen Deutsch und Chinesisch.

### Bewusste Grenzen

- **Gesundheit:** Biko erinnert und gibt Hinweise zur hinterlegten Diät, aber keine Diagnosen und keine Änderungen an Medikamenten. Bei Notfällen nennt er 144, bei Beschwerden 1450, bei Krisen die Telefonseelsorge 142.
- **Ehrlich KI:** Biko sagt, dass er eine KI ist, und ermutigt zu Kontakt mit Familie und Freunden.
- **Betrug:** Er warnt bei Enkeltrick, falscher Polizei oder Bank, Links in SMS.
- **Erinnerungen brauchen die offene App.** Version 1 kann das Handy nicht "aufwecken", wenn die Seite zu ist. Für wichtige Medikamente zusätzlich den Handy-Wecker stellen. Echte Push-Nachrichten sind der nächste Schritt.
- **Sprechen** nutzt die Spracherkennung des Browsers. Geht sie auf einem Handy nicht, funktioniert immer die Mikrofon-Taste der Tastatur.

## Installieren (auf dem Hetzner-Server)

```bash
cd /opt/biko-bot && git pull
cd assistent
cp .env.example .env
nano .env                      # ANTHROPIC_API_KEY und APP_PASSWORT eintragen
docker compose up -d --build
```

Den API-Schlüssel gibt es auf https://console.anthropic.com unter "API Keys". Dort unbedingt ein
**Monatslimit** setzen (z. B. 10 €), dann kann nichts teuer werden.

Fürs Handy freigeben, wie bei der Trading-App über Tailscale (eigener Port, damit sich nichts überschneidet):

```bash
sudo tailscale serve --bg --https=8443 8092
```

Dann am Handy `https://biko.taile8ab7a.ts.net:8443` öffnen, Passwort eingeben und "Zum Home-Bildschirm" wählen.

**Für Handys ohne Tailscale** (z. B. Verwandte): `sudo tailscale funnel --bg --https=8443 8092` macht die Seite
öffentlich erreichbar. Dann schützt nur das Passwort (5 Fehlversuche, dann 15 Minuten Sperre), also ein langes wählen.

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
python -m unittest test_server                                        # Tests ohne echte KI
DATA_DIR=./daten APP_PASSWORT=test ANTHROPIC_API_KEY=... python server.py   # http://127.0.0.1:8092
```
