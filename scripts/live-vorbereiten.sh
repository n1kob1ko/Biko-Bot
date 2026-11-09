#!/usr/bin/env bash
# Arbeitet die technischen Punkte aus TODO.md (Phase A und B) am Server in einem Rutsch ab.
# Einmal am Server als root ausführen. Nach dem Update läuft der Rest im Hintergrund weiter
# (Terminal darf zu), Fortschritt: tail -f /opt/biko-bot/user_data/backtest_results/BERICHT.txt
#
#   curl -fsSL https://raw.githubusercontent.com/n1kob1ko/biko-bot/main/scripts/live-vorbereiten.sh | sudo bash
#
# Macht:
#  1. Bot-Code aktualisieren (install.sh, bleibt Testmodus, startet den Wächter)
#  2. Server härten (Updates, Firewall, fail2ban, Swap; SSH-Passwort nur aus, wenn ein Schlüssel da ist)
#  3. Kursdaten laden (Binance BTC/ETH/SOL in EUR, 4h und 1h, ab 2020). Binance-Daten, weil Kraken
#     über die API nur 720 Kerzen liefert und der Einzeltrade-Download Tage dauert. Die Kurse
#     sind praktisch gleich, gerechnet wird trotzdem mit Kraken-Kosten (0,5 % pro Seite).
#  4. Backtests aller drei Strategien, Entwicklungs-Zeitraum 2021-2023, mit Lookahead- und
#     Recursive-Prüfung, plus Vergleich mit BTC halten nach Steuer
#  5. Notaus einmal im Testmodus probieren (Pause und wieder Weiter)
#  6. Bericht nach /opt/biko-bot/user_data/backtest_results/BERICHT.txt
#
# Macht NICHT (braucht deine Konten): Telegram-Bot, Hetzner-Passwort/2FA/Backups, healthchecks.io,
# Kraken-Konto und API-Key, Validierungs- und Final-Backtest (erst wenn die Regeln feststehen).
set -uo pipefail
ZIEL="${BIKO_DIR:-/opt/biko-bot}"
[ "$(id -u)" -eq 0 ] || { echo "Bitte mit sudo starten." >&2; exit 1; }

schritt() { echo; echo "=================================================================="; echo "==> $1"; echo "=================================================================="; }
FEHLER=()

schritt "1/6 Bot-Code aktualisieren (Testmodus bleibt)"
if curl -fsSL https://raw.githubusercontent.com/n1kob1ko/biko-bot/main/install.sh | BIKO_BOERSE="${BIKO_BOERSE:-kraken}" bash; then
  echo "[OK] Update eingespielt"
else
  FEHLER+=("Update per install.sh fehlgeschlagen")
fi
cd "$ZIEL" || { echo "FEHLER: $ZIEL fehlt" >&2; exit 1; }
BERICHT_DIR="$ZIEL/user_data/backtest_results"
mkdir -p "$BERICHT_DIR"
BERICHT="$BERICHT_DIR/BERICHT.txt"

# Ab hier im Hintergrund weiterlaufen, damit ein zugeklappter Laptop oder eine abgebrochene
# SSH-Verbindung die Backtests nicht killt. Das frisch heruntergeladene Skript liegt jetzt in $ZIEL/scripts.
if [ "${1:-}" != "--vordergrund" ]; then
  : > "$BERICHT"
  setsid nohup bash "$ZIEL/scripts/live-vorbereiten.sh" --vordergrund >/dev/null 2>&1 < /dev/null &
  echo
  echo "=================================================================="
  echo "  Der Rest läuft jetzt im Hintergrund (10 bis 40 Minuten)."
  echo "  Du kannst das Terminal schließen und den Laptop zuklappen."
  echo "  Zuschauen:   tail -f $BERICHT        (beenden mit Strg+C)"
  echo "  Fertig, wenn am Ende '6/6 Zusammenfassung' steht."
  echo "=================================================================="
  exit 0
fi
exec > >(tee -a "$BERICHT") 2>&1
echo; echo "Bericht $(date -u '+%Y-%m-%d %H:%M UTC'), Server $(hostname)"

schritt "2/6 Server härten"
if bash scripts/server-haerten.sh; then echo "[OK] Server gehärtet"; else FEHLER+=("server-haerten.sh fehlgeschlagen"); fi
if [ -s /root/.ssh/authorized_keys ]; then
  echo "[OK] SSH-Schlüssel vorhanden"
else
  echo "[!!] Kein SSH-Schlüssel hinterlegt, Passwort-Login bleibt an (siehe TODO.md Phase A)."
fi

schritt "3/6 Kursdaten laden (Binance, EUR-Paare, 4h und 1h, ab 2020)"
if docker compose run --rm freqtrade download-data \
     --config /freqtrade/user_data/config.binance.json \
     --timeframes 4h 1h --timerange 20200101- --erase 2>&1 | tail -n 15; then
  echo "[OK] Daten in user_data/data/binance"
  ls -la user_data/data/binance 2>/dev/null | head
else
  FEHLER+=("download-data fehlgeschlagen")
fi

schritt "4/6 Backtests (Entwicklungs-Zeitraum 2021-2023, Kraken-Kosten 0,5 % pro Seite)"
for S in EmaTrendStrategy BreakoutStrategy DipBuyStrategy; do
  echo; echo "------------------ $S ------------------"
  if BOT_CONFIG=config.binance.json PRUEFEN=ja FEE=0.005 bash scripts/backtest.sh "$S" entw; then
    echo "[OK] $S fertig"
  else
    FEHLER+=("Backtest $S fehlgeschlagen")
  fi
done
echo; echo "------------------ Trendfolger nochmal mit niedriger Gebühr (0,25 %) ------------------"
BOT_CONFIG=config.binance.json FEE=0.0025 bash scripts/backtest.sh EmaTrendStrategy entw \
  || FEHLER+=("Backtest Trendfolger 0,25 % fehlgeschlagen")

schritt "5/6 Notaus im Testmodus probieren (nur Pause, dann wieder Weiter)"
if bash scripts/notaus.sh --nur-pause; then
  PORT="$(grep -E '^API_PORT=' .env | cut -d= -f2-)"; PORT="${PORT:-8080}"
  AUTH="$(grep -E '^FREQTRADE__API_SERVER__USERNAME=' .env | cut -d= -f2-):$(grep -E '^FREQTRADE__API_SERVER__PASSWORD=' .env | cut -d= -f2-)"
  sleep 2
  if curl -fsS -u "$AUTH" -X POST "http://127.0.0.1:$PORT/api/v1/start" -H 'Content-Type: application/json' -d '{}'; then
    echo; echo "[OK] Notaus (Pause) und Weiter funktionieren"
  else
    FEHLER+=("Bot nach Notaus-Test nicht wieder gestartet: in der App auf 'Weiter handeln' tippen")
  fi
else
  FEHLER+=("notaus.sh --nur-pause fehlgeschlagen")
fi

schritt "6/6 Zusammenfassung"
echo "Wächter-Log (letzte Zeilen):"
docker compose logs --tail 5 biko-waechter 2>/dev/null || true
echo
if [ "${#FEHLER[@]}" -eq 0 ]; then
  echo "Alles durchgelaufen. Bericht: $BERICHT"
else
  echo "Mit Problemen durchgelaufen:"
  for f in "${FEHLER[@]}"; do echo "  - $f"; done
  echo "Bericht: $BERICHT"
fi
echo
echo "Bitte den Bericht an Claude schicken (z. B.: cat $BERICHT), dann wird TODO.md abgehakt."
echo "Was nur du machen kannst: Telegram, Hetzner-Passwort/2FA/Backups, healthchecks.io, Kraken-Konto + API-Key."
