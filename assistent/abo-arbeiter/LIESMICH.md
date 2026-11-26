# Biko-Arbeiter: Biko-Chef programmiert mit deinem Claude-Abo

Der Biko-Arbeiter läuft auf deinem PC. Er holt Code-Aufgaben von Biko-Chef ab, lässt **Claude Code mit deinem
Claude-Abo** daran arbeiten und öffnet einen PR auf GitHub. Das kostet kein API-Geld, zählt aber gegen die Grenzen
deines Abos (5-Stunden-Fenster und Wochengrenze, zusammen mit claude.ai). Gemergt wird erst, wenn du in `/chef` bei
der Frage „Soll ich ihn mergen?“ auf **Ja** tippst.

Erlaubt ist das nur für **deine eigenen Projekte**. Anthropic erlaubt, das unveränderte Claude Code mit dem eigenen
Abo auf dem eigenen Rechner zu nutzen, auch aus einem Skript. Für Kunden oder andere Leute darf das Abo nicht laufen.

## Einmal einrichten (Windows)

1. **Programme** (PowerShell):
   ```powershell
   winget install Git.Git Python.Python.3.12 GitHub.cli
   irm https://claude.ai/install.ps1 | iex
   ```
2. **Anmelden**: `claude` einmal starten und mit deinem Abo anmelden (nicht mit einem API-Schlüssel).
   Dann `gh auth login` (GitHub.com, HTTPS, im Browser bestätigen).
3. **Repo**: Gibt es den Ordner aus `repos` noch nicht, klont der Biko-Arbeiter das Repo beim ersten Auftrag selbst.
4. **Einstellungen**: `einstellungen.beispiel.json` nach `einstellungen.json` kopieren und eintragen:
   - `url`: die Adresse von Biko auf Railway
   - `token`: derselbe Wert wie `CHEF_ABO_TOKEN` in Railway
   - `repos`: welches GitHub-Repo in welchem Ordner liegt
5. **Starten**: Doppelklick auf `start.bat`. Das Fenster offen lassen, solange Biko arbeiten soll.
   In `/chef` steht dann oben „PC verbunden“.

Damit er beim Hochfahren von selbst startet: Verknüpfung zu `start.bat` in den Autostart-Ordner legen
(`Win+R`, `shell:startup`).

## Was Claude Code darf

Dateien lesen und ändern, Tests laufen lassen (python, pytest, npm, node), im Internet nachsehen, committen.
Nicht: pushen, mergen, `gh`, `curl`, Remotes ändern. Das Pushen und den PR macht der Biko-Arbeiter selbst, gemergt
wird nur nach deinem Ja. Claude arbeitet immer in einem eigenen Ordner neben deinem Repo (`.biko-arbeit`), dein
eigener Stand bleibt unberührt.

## Grenzen

- Immer nur eine Aufgabe zur selben Zeit, höchstens 45 Minuten (`max_minuten`).
- Höchstens 10 Läufe pro Tag (im Gespräch mit Biko änderbar, bis 30).
- Meldet Claude Code „Grenze erreicht“, pausiert Biko die Abo-Aufgaben und macht danach weiter.
- Ist `ANTHROPIC_API_KEY` gesetzt, nimmt der Biko-Arbeiter ihn für Claude Code weg, damit dein Abo zählt.
