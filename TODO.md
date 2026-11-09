# Biko Bot: Weg zum Echtgeld (To-do-Liste)

Stand: 9.11.2026. Der Bot läuft im **Testmodus** (Spielgeld) auf dem Hetzner-Server.
Ziel: mit 200–500 € echt handeln, aber nur, wenn er nachweislich **besser ist als BTC halten**, nach Gebühren und 27,5 % Steuer.

Zeichen: ✅ erledigt · 🆕 in diesem Schritt neu gebaut · 👉 musst du machen (braucht deine Konten, deinen Server oder deine Entscheidung)

---

## 1. Was im Code schon für Echtgeld gebaut ist

| | Thema | Wie gelöst |
|---|---|---|
| ✅ | Nur abgeschlossene Kerzen | `process_only_new_candles`, Freqtrade wirft die laufende Kerze weg; Ausbruch-Kanal mit `shift(1)` |
| ✅ | Stop-Loss, auch wenn der Server ausfällt | Stop-Order direkt an der Börse (`stoploss_on_exchange`), Kraken: Stop-Market |
| ✅ | Positionsgröße nach Risiko | 1 % vom Konto pro Trade, inkl. 1 % Kostenpuffer für Gebühren und Stop-Slippage |
| ✅ | Börsen-Mindestbetrag | Ist der Einsatz kleiner als das Minimum der Börse, wird der Trade **übersprungen** (nie mehr Risiko als eingestellt) |
| ✅ | Tageslimit / Drawdown-Stopp | −3 % in 24 h → 24 h Pause; −15 % → Kill-Switch, dauerhaft |
| ✅ | Neustart / Absturz | Trades stehen in der Datenbank, Freqtrade gleicht offene Orders mit der Börse ab, Container startet von selbst neu |
| ✅ | Secrets | nur in `.env` (nicht in Git), API nur auf 127.0.0.1, App nur über Tailscale |
| ✅ | Kaufen von Hand gesperrt | App kann nur pausieren, weiter, verkaufen |
| 🆕 | **Getrennte Echtgeld-Datenbank** | Live nutzt `tradesv3.live.sqlite`. Startet der Bot mit Echtgeld und der Spielgeld-Datenbank (oder umgekehrt), bricht er den Start ab. Sonst würde er versuchen, Spielgeld-Coins echt zu verkaufen. |
| 🆕 | **Echtgeld-Schalter in install.sh** | `BIKO_MODUS=live` in der `.env`. install.sh prüft dann: Keys da, Telegram an, nur dein eigener Bot (nicht der vom Cousin), und fragt beim ersten Mal "LIVE eintippen". Ein Update per install.sh schaltet einen Live-Bot nicht mehr aus Versehen in den Testmodus. |
| 🆕 | **Verkaufen füllt zuverlässig** | Verkauf jetzt zum besten Kaufgebot (`exit_pricing: other`) statt auf einen besseren Preis zu warten. Kostet etwas Spread, aber der Bot hängt in fallenden Kursen nicht mit einer unverkauften Order fest. Kaufen bleibt zum günstigeren Preis (Limit, wartet bis 15 Min., dann neuer Versuch). |
| 🆕 | **Feste Freqtrade-Version** | `freqtradeorg/freqtrade:2026.10` statt `stable`, damit kein ungeprüftes Update mitten im Echtgeld-Betrieb passiert |
| 🆕 | **Wächter** | Neuer kleiner Dienst `biko-waechter`: alle 5 Min. prüfen, ob der Bot rechnet und jeder offene Trade einen Stop an der Börse hat. Alarm per Telegram. Optional Ping an healthchecks.io (meldet, wenn der ganze Server weg ist). |
| 🆕 | **Tägliches Datenbank-Backup** | macht der Wächter nach `user_data/backups/<datum>/`, 14 Tage |
| 🆕 | **Strategiewechsel bei offenen Trades** | Im Echtgeld-Modus lehnt die App einen Wechsel von Strategie oder Takt ab, solange ein Trade offen ist |
| 🆕 | **Notaus** | `sudo /opt/biko-bot/scripts/notaus.sh`: nichts Neues kaufen + alles verkaufen (mit Rückfrage) |
| 🆕 | **Steuer-Export** | `python3 scripts/steuer_export.py 2027` → CSV mit allen Trades und Jahressumme |
| 🆕 | **Server härten** | `scripts/server-haerten.sh`: Sicherheitsupdates automatisch, Firewall, fail2ban, SSH nur mit Schlüssel, Swap |
| 🆕 | **Backtest mit echten Kosten** | `scripts/backtest.sh`: 0,5 % pro Seite (Kraken-Taker + Spread/Slippage), Protections an, danach Vergleich mit BTC halten vor und nach Steuer |
| 🆕 | Docker-Logs begrenzt | max. 30 MB pro Dienst, damit die Platte nicht vollläuft |

---

## 2. Was du machen musst, in dieser Reihenfolge

### Phase A: jetzt, während der Testmodus läuft (ca. 1 Stunde)

- [ ] 👉 **Update einspielen:** `curl -fsSL https://raw.githubusercontent.com/n1kob1ko/biko-bot/main/install.sh | sudo bash` (bleibt Testmodus, startet den neuen Wächter)
- [ ] 👉 **Telegram einrichten:** Bot bei @BotFather anlegen, Chat-ID über @userinfobot, in `/opt/biko-bot/.env` eintragen (`FREQTRADE__TELEGRAM__ENABLED=true`, `TOKEN`, `CHAT_ID`), dann install.sh nochmal. Ohne Telegram kein Echtgeld (install.sh verweigert es).
- [ ] 👉 **SSH-Schlüssel statt Passwort:** am PC `ssh-keygen -t ed25519`, dann `ssh-copy-id root@2.31.179.96`. Testen, ob der Login ohne Passwort geht.
- [ ] 👉 **Server härten:** `sudo bash /opt/biko-bot/scripts/server-haerten.sh` (erst nach dem SSH-Schlüssel, dann schaltet es den Passwort-Login ab)
- [ ] 👉 **Hetzner-Root-Passwort ändern** (kam per E-Mail) und **2FA im Hetzner-Konto** einschalten
- [ ] 👉 **healthchecks.io** (kostenlos): Check anlegen, Takt 5 Min., Gnadenzeit 15 Min., Ping-URL als `HEALTHCHECK_URL=` in die `.env`, install.sh nochmal
- [ ] 👉 **Hetzner-Backups** für den Server einschalten (+20 % = ca. 1,56 €/Monat): Backup außerhalb des Servers
- [ ] 👉 Notaus einmal im Testmodus ausprobieren: `sudo /opt/biko-bot/scripts/notaus.sh --nur-pause`, danach in der App "Weiter handeln"

### Phase B: beweisen, dass es sich lohnt (2–3 Monate)

Backtests laufen nicht in der Cloud-Sandbox (kommt nicht an Kraken), nur auf deinem PC oder dem Server.

- [ ] 👉 **Kursdaten laden** (README, Abschnitt `download-data`; Kraken über die CSV-Variante, sonst dauert es Tage)
- [ ] 👉 **Trendfolger backtesten:** `PRUEFEN=ja scripts/backtest.sh EmaTrendStrategy entw`
  - `has_bias` muss `False` sein, recursive-analysis bei 600 Kerzen ~0 %
  - nochmal mit `FEE=0.0025`: wenn er nur mit niedrigen Gebühren gewinnt, ist er nicht gut genug
- [ ] 👉 Wenn der Trendfolger im Entwicklungs-Zeitraum passt: `scripts/backtest.sh EmaTrendStrategy valid` (2024, erst jetzt anschauen)
- [ ] 👉 **Ausbruch und Rücksetzer** genauso testen. Erst danach in der App für Echtgeld erlauben.
- [ ] 👉 **Seitwärtsmarkt:** im Backtest mit `--breakdown month` schauen, ob die Verluste aus Seitwärtsphasen kommen (viele kleine Stops hintereinander). Wenn ja, einen Filter (z. B. ADX > 20) **als eigenen Test** ausprobieren, nicht einfach einbauen. Jeder zusätzliche Parameter erhöht die Gefahr von Überanpassung.
- [ ] 👉 **Finaler Test** (`scripts/backtest.sh EmaTrendStrategy final`) **genau einmal**, wenn die Regeln fest sind. Danach nichts mehr an den Regeln drehen.
- [ ] 👉 **Testmodus mindestens 8 Wochen** mit genau den Echtgeld-Einstellungen laufen lassen (Kraken, 4h, gleiche Coins, gleiches Risiko)
- [ ] 👉 **Testmodus mit Backtest vergleichen:** Backtest über denselben Zeitraum laufen lassen. Gleiche Trades zu ähnlichen Zeiten? Große Abweichung = Fehler im Setup, nicht Pech.
- [ ] 👉 **Kraken-Gebühren** deiner Stufe nachschauen (kraken.com/features/fee-schedule) und in `biko_base.py` `cost_buffer` bzw. im Backtest `FEE` anpassen, wenn sie anders sind

### Phase C: vor dem ersten echten Euro (1 Abend)

- [ ] 👉 **Entscheidung gegen die festen Regeln unten** (Abschnitt 3). Nicht nach Gefühl.
- [ ] 👉 **Kraken-Konto:** voll verifiziert, **2FA für Login und Auszahlung**, "Global Settings Lock" an, Auszahlungsadressen nur aus Liste
- [ ] 👉 **Am besten ein eigenes Kraken-Unterkonto nur für den Bot.** Grund: Steuer (gleitender Durchschnittspreis, siehe `steuer_export.py`) und der Bot zählt sonst dein restliches Geld mit.
- [ ] 👉 **API-Key anlegen:** nur Query Funds, Query Open/Closed Orders & Trades, Create & Modify Orders, Cancel/Close Orders. **Kein Withdraw, kein Deposit.** IP-Whitelist: **2.31.179.96**. Key nur in die `.env` am Server, nirgends sonst.
- [ ] 👉 **Klein anfangen:** 200 € einzahlen, Risiko 1 % (= ca. 33 € pro Trade). Prüfen, dass 33 € über dem Kraken-Minimum für jedes Paar liegt (in der App/Log steht "Trade übersprungen", wenn nicht).
- [ ] 👉 In der App: Strategie Trendfolger, 4 Std, BTC/ETH/SOL (das, was getestet ist)
- [ ] 👉 `.env`: `BIKO_MODUS=live`, Key und Secret eintragen, dann install.sh ausführen und `LIVE` eintippen
- [ ] 👉 Ersten echten Trade beobachten: Kauf bei Kraken sichtbar? **Stop-Order bei Kraken sichtbar?** Telegram-Meldung gekommen?

### Phase D: im Echtgeld-Betrieb

- [ ] 👉 **Jede Woche** 5 Min.: App ansehen, Telegram-Meldungen, `docker compose logs --tail 100` auf Fehler
- [ ] 👉 **Jeden Monat:** Ergebnis gegen BTC halten im selben Zeitraum vergleichen (Regeln unten)
- [ ] 👉 **Freqtrade-Updates** alle 2–3 Monate: neue Version erst im Testmodus (zweiter Bot oder Testlauf), dann in `docker-compose.yml` die Versionsnummer hochsetzen
- [ ] 👉 **Steuer jedes Jahr:** `python3 scripts/steuer_export.py <jahr>`, mit dem Jahresbericht von Kraken vergleichen, in der Steuererklärung (E1kv, 27,5 %) angeben. Kraken zieht keine KESt ab.
- [ ] 👉 Nach 3 Monaten gut: auf bis zu 500 € erhöhen, nicht mehr

---

## 3. Feste Regeln (vorher festlegen, nicht im Nachhinein)

**Live gehen nur, wenn ALLES erfüllt ist:**
1. lookahead-analysis ohne Bias, recursive-analysis stabil
2. Backtest 2021–2023 **und** 2024 mit 0,5 % Gebühr pro Seite: nach Steuer besser als BTC halten, oder höchstens leicht schlechter bei deutlich kleinerem Rückgang (dann bewusst entscheiden, ob dir das reicht)
3. Größter Konto-Rückgang im Backtest unter 15 % und mindestens 30 Trades (weniger ist Zufall)
4. Finaler Test ab 2025 nicht schlechter als der Rest
5. Mindestens 8 Wochen Testmodus, Trades passen zum Backtest, kein Wächter-Alarm offen, kein Trade ohne Stop

**Zurück in den Testmodus (oder ganz aufhören), wenn:**
- der Kill-Switch auslöst (−15 %), automatisch, keine neuen Trades; Freigabe nur nach Analyse
- nach 3 Monaten mehr als 10 Prozentpunkte schlechter als BTC halten
- ein Trade passiert, den du dir nicht erklären kannst → sofort Notaus, dann suchen
- Wächter meldet "Trade ohne Stop-Loss" und es klärt sich nicht in einer Stunde
- die Börse die Regeln ändert (MiCA, Gebühren, API)

---

## 4. Laufende Kosten (pro Monat)

| Posten | Kosten |
|---|---|
| Hetzner CPX02 | 7,79 € |
| Hetzner-Backups (optional, empfohlen) | ca. 1,56 € |
| Telegram, Tailscale, healthchecks.io | 0 € |
| **Summe** | **ca. 9,35 €** |

Achtung: Bei 500 € Kapital sind das ca. **22 % im Jahr nur für den Server**. Der Bot muss das zusätzlich zu BTC halten verdienen. Ehrlich gesagt: mit 200–500 € ist das vor allem ein Lernprojekt. Lohnend wird es erst mit mehr Kapital, und das erst, wenn es sich klein bewährt hat.

---

## 5. Bekannte Grenzen (nicht lösbar, nur im Blick behalten)

- **Stop-Loss im Crash:** Der Stop ist eine Market-Order. Bei einem plötzlichen Absturz kann er deutlich unter −5 % füllen. Der Kostenpuffer (1 %) deckt normale Fälle. Bei einem Kurs-Sprung über Nacht hilft nichts.
- **Binance:** dort gibt es im Spot nur Stop-Limit. Bei einem schnellen Absturz kann der Stop ungefüllt bleiben. Für Echtgeld darum Kraken (auch wegen MiCA).
- **Kill-Switch** zählt nur verkaufte Trades. Offene Verluste begrenzt der Stop (ca. 1 % pro Trade).
- **Kauf verpasst:** Kauf-Limit wartet bis 15 Min. und wird dann neu gesetzt. Läuft der Kurs schnell weg, kommt der Trade später oder gar nicht. Bei 4h-Trendfolge kein Problem.
- **Signal beim Neustart:** Nach einem Neustart mitten in einer 4h-Kerze kann der Bot noch auf das Signal der letzten Kerze kaufen (bis zu 4 Std. spät). So verhält sich auch der Backtest nicht ganz, darum der Vergleich Testmodus ↔ Backtest.
- **Strategiewechsel:** im Testmodus sofort auch für offene Trades, im Echtgeld-Modus erst, wenn nichts offen ist.
- **Cousin:** Sein Bot auf deinem Server bleibt immer Testmodus (install.sh verweigert Echtgeld für andere Bots). Echtgeld nur auf seinem eigenen Server mit seinem eigenen Konto.

Keine Anlage- oder Steuerberatung.
