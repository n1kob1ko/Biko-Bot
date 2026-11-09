#!/usr/bin/env bash
# Notaus: nichts Neues mehr kaufen und ALLE offenen Trades sofort zum Marktpreis verkaufen.
#   sudo /opt/biko-bot/scripts/notaus.sh            (fragt nach)
#   sudo /opt/biko-bot/scripts/notaus.sh --nur-pause (nur nichts Neues kaufen, nichts verkaufen)
# Danach läuft der Bot weiter, kauft aber nichts. Wieder starten: in der App "Weiter handeln".
# Geht auch übers Handy: Telegram /stopentry und /forceexit all, oder in der App.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "FEHLER: keine .env in $(pwd)" >&2; exit 1; }
wert() { grep -E "^$1=" .env | tail -n1 | cut -d= -f2-; }
PORT="$(wert API_PORT)"; PORT="${PORT:-8080}"
AUTH="$(wert FREQTRADE__API_SERVER__USERNAME):$(wert FREQTRADE__API_SERVER__PASSWORD)"
api() {
  local body="${2:-}"; [ -n "$body" ] || body='{}'
  curl -fsS -u "$AUTH" -X POST -H 'Content-Type: application/json' "http://127.0.0.1:$PORT/api/v1/$1" -d "$body"; echo
}

echo "==> Pause: keine neuen Käufe"
api stopentry
[ "${1:-}" = "--nur-pause" ] && exit 0

if [ "${1:-}" != "--ja" ]; then
  read -r -p "ALLE offenen Trades jetzt zum Marktpreis verkaufen? (ja/N): " a </dev/tty || a=""
  [ "$a" = "ja" ] || { echo "Nur pausiert, nichts verkauft."; exit 0; }
fi
echo "==> Alle offenen Trades verkaufen"
api forceexit '{"tradeid": "all", "ordertype": "market"}'
echo "Fertig. Bitte in der App oder bei der Börse prüfen, ob alles verkauft ist."
