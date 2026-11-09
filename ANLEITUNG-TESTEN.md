# Biko Bot testen, nur mit dem Handy

Diese Anleitung ist für Leute, die den Bot **ausprobieren** wollen, ohne etwas zu installieren und ohne echtes Geld.
Der Bot läuft dabei im **Testmodus (Dry-Run)**: Er beobachtet echte Kurse von Kraken, "kauft" und "verkauft" aber nur mit
500 € Spielgeld. Es gibt keinen Börsen-Account, keinen API-Key und kein Risiko.

Es gibt zwei Wege:

| | Weg A: Zuschauen (empfohlen zum Start) | Weg B: Eigener Bot |
|---|---|---|
| Wer betreibt den Bot? | Niko, im Testmodus | Du selbst, auf deinem eigenen Server |
| Was brauchst du? | Nur Telegram am Handy | Telegram + gemieteter Server (ca. 4–6 € pro Monat) |
| Aufwand für dich | 2 Minuten | ca. 20 Minuten, alles am Handy |
| Echtes Geld später möglich? | Nein, nie | Ja, aber nur mit deinem eigenen Konto und Key |

---

## Weg A: Per Telegram zuschauen

### Was du am Handy machst

1. **Telegram** installieren (App Store / Play Store), falls du es noch nicht hast.
2. Niko schickt dir einen Einladungslink zur Gruppe **"Biko Bot Test"**. Antippen, beitreten. Fertig.
3. In der Gruppe meldet der Bot von selbst, wenn er etwas kauft oder verkauft.
4. Du kannst ihn auch fragen. Einfach in die Gruppe schreiben:

| Befehl | Was du bekommst |
|---|---|
| `/status` | Welche Trades gerade offen sind |
| `/profit` | Gewinn/Verlust insgesamt (Spielgeld) |
| `/daily` | Gewinn/Verlust pro Tag |
| `/balance` | Wie viel Spielgeld in EUR und in Coins steckt |
| `/performance` | Welche Coins bisher gut oder schlecht liefen |
| `/help` | Alle Befehle |

Wichtig zu wissen:
- Der Bot handelt auf **4-Stunden-Kerzen**. Es kann Tage dauern, bis der erste Trade kommt. Das ist normal.
- Alles ist Spielgeld. Auch wenn du aus Versehen einen Befehl wie `/forceexit` schickst, passiert mit echtem Geld nichts.

### Was Niko dafür einrichtet (einmalig)

1. **Telegram-Bot anlegen:** In Telegram `@BotFather` öffnen, `/newbot` schicken, Namen vergeben.
   Du bekommst einen **Token** (sieht aus wie `123456789:AAH...`).
2. **Gruppe anlegen:** Neue Gruppe "Biko Bot Test", den eigenen Bot und den Cousin hinzufügen.
   Einladungslink: Gruppeninfo → Mitglieder hinzufügen → Einladungslink.
3. **Chat-ID der Gruppe holen:** In der Gruppe irgendeine Nachricht wie `/status` schicken. Dann im Browser öffnen:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`. Dort steht `"chat":{"id":-100...`. Diese Zahl **mit Minus** ist die Chat-ID.
4. **In `.env` eintragen:**
   ```
   FREQTRADE__TELEGRAM__ENABLED=true
   FREQTRADE__TELEGRAM__TOKEN=123456789:AAH...
   FREQTRADE__TELEGRAM__CHAT_ID=-100...
   ```
5. **Im erzwungenen Testmodus starten:**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.testmodus.yml up -d
   ```
   `docker-compose.testmodus.yml` setzt `dry_run` fest auf `true` und leert die Börsen-Keys, egal was in `.env` steht.
   So kann der Zuschau-Bot nie aus Versehen echt handeln.

Der Bot muss rund um die Uhr laufen. Läuft er auf Nikos PC und der PC ist aus, ist auch der Bot aus.
Für einen längeren Test daher besser auf dem VPS starten (siehe Weg B, das Skript funktioniert für Niko genauso).

---

## Weg B: Eigener Bot auf deinem eigenen Server

Für den Fall, dass du den Bot später **selbst** betreiben willst. Du mietest einen kleinen Server bei einem Anbieter,
und alles läuft dort. Du brauchst keinen PC, das Handy reicht.

### 1. Server mieten

Zum Beispiel bei **Hetzner Cloud** (hetzner.com/cloud), es geht aber jeder Anbieter mit Ubuntu.

1. Konto anlegen (Ausweis/Zahlungsmittel nötig).
2. **Server erstellen:**
   - Standort: Deutschland oder Finnland
   - Image: **Ubuntu 24.04**
   - Typ: der kleinste (2 vCPU, 4 GB RAM reicht locker)
   - Ein Root-Passwort per E-Mail anfordern bzw. setzen
3. Nach einer Minute ist der Server da. Du siehst seine **IP-Adresse** (z. B. `203.0.113.10`).

### 2. Mit dem Handy verbinden

Am einfachsten mit der App **Termius** (kostenlos, iPhone und Android):

1. "New Host" → bei Address die IP eintragen, Username `root`, Passwort aus Schritt 1.
2. Verbinden. Jetzt siehst du ein schwarzes Fenster mit Text. Das ist der Server.

(Alternativ hat Hetzner im Browser eine "Konsole". Dort funktioniert Einfügen aber oft nicht, darum Termius.)

### 3. Telegram-Bot anlegen

Wie oben bei Weg A, Schritt 1 und 3, aber mit **deinem eigenen** Bot. Statt einer Gruppe reicht der direkte Chat mit
deinem Bot: Schreib ihm `/start`, dann die `getUpdates`-Adresse öffnen, die Chat-ID ist dort eine Zahl ohne Minus.
Token und Chat-ID kurz in die Zwischenablage oder Notizen legen.

### 4. Installieren: eine Zeile

Diese Zeile in Termius einfügen und Enter drücken:

```bash
curl -fsSL https://raw.githubusercontent.com/n1kob1ko/biko-bot/main/install.sh | bash
```

Das Skript
- installiert Docker,
- lädt den Bot nach `/opt/biko-bot`,
- fragt nach Telegram-Token und Chat-ID (einfügen, Enter),
- erzeugt zufällige Passwörter,
- startet den Bot **im Testmodus mit Spielgeld**.

Am Ende steht **"Läuft!"**. Dein Bot schreibt dir in Telegram eine Startnachricht. Ab jetzt läuft er rund um die Uhr,
auch wenn du Termius schließt. Danach brauchst du nur noch Telegram (Befehle wie bei Weg A).

### Später: stoppen, aktualisieren, Probleme

In Termius verbinden und eintippen:

| Was | Befehl |
|---|---|
| Stoppen | `cd /opt/biko-bot && docker compose down` |
| Wieder starten / auf neue Version aktualisieren | die Installationszeile von oben nochmal ausführen |
| Letzte Meldungen anzeigen (bei Problemen an Niko schicken) | `cd /opt/biko-bot && docker compose logs --tail 100` |
| Server ganz loswerden | beim Anbieter den Server löschen (dann kostet er nichts mehr) |

Hinweis: Die Biko-App (Port 8081, einfache Ansicht mit Maskottchen) und FreqUI (Port 8080) sind aus Sicherheitsgründen nicht offen im Internet.
Am Handy öffnest du die Biko-App privat über Tailscale (siehe unten). Bedienen (stoppen usw.) geht über Telegram.

### Biko-App am Handy (Tailscale)

Tailscale verbindet dein Handy und deinen Server zu einem kleinen privaten Netz. Nur deine eigenen Geräte sehen die App, sonst niemand. Kostenlos für private Nutzung.

1. **Handy:** App "Tailscale" aus dem App Store / Play Store installieren, öffnen und anmelden (z. B. mit Google oder Apple). Verbindung einschalten.
2. **Server:** Die Installationszeile von oben nochmal ausführen (oder beim ersten Mal gleich so beantworten).
   Bei "Biko-App am Handy über Tailscale einrichten? (j/N)" mit `j` antworten.
3. Es erscheint ein Link (`https://login.tailscale.com/...`). Den Link am Handy öffnen und mit **demselben Konto** wie in Schritt 1 bestätigen.
4. Falls noch ein Link zum Aktivieren von HTTPS erscheint: ebenfalls öffnen und bestätigen.
5. Am Ende zeigt das Skript die Adresse, z. B. `https://biko.tail1234.ts.net`. Am Handy im Browser öffnen
   (Tailscale-App muss an sein) und mit Benutzer und Passwort aus `ZUGANGSDATEN.txt` anmelden.
6. Tipp: Im Browser-Menü "Zum Home-Bildschirm" wählen. Dann ist Biko wie eine App mit eigenem Symbol da.

Die App kann nur anzeigen, nichts kaufen oder verkaufen.

---

## Rechtliches, kurz

- **Testmodus (Weg A und B):** Es wird kein Geld verwaltet, nur Spielgeld simuliert. Unproblematisch.
- **Echtes Geld:** Nur auf deinem **eigenen** Server, mit deinem **eigenen** Kraken-Konto und **deinem eigenen** API-Key,
  den nur du kennst. Niko darf keinen Zugriff auf dein Konto oder deinen Server haben und nichts daran verdienen.
  Wer für andere Krypto-Portfolios verwaltet, braucht in Österreich ggf. eine Lizenz (MiCAR).
  Das Installationsskript schaltet echtes Handeln deshalb absichtlich **nicht** ein.
- Keine Anlageberatung. Der Bot ist ein Lernprojekt und kann Geld verlieren.
