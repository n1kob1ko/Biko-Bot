#!/usr/bin/env bash
# Zweiter Testlauf (9.11.2026): alle Strategien OHNE Kill-Switch über die vollen 3 Jahre, plus die zwei
# vorher festgelegten Trendfolger-Varianten (ADX-Filter, weiter Stop). Läuft im Hintergrund.
#
#   curl -fsSL https://raw.githubusercontent.com/n1kob1ko/biko-bot/main/scripts/varianten-testen.sh | sudo bash
#
# Ergebnis (kompakt, zum Reinkopieren): /opt/biko-bot/user_data/backtest_results/VARIANTEN.txt
set -uo pipefail
ZIEL="${BIKO_DIR:-/opt/biko-bot}"
[ "$(id -u)" -eq 0 ] || { echo "Bitte mit sudo starten." >&2; exit 1; }
if [ -z "${BASH_SOURCE[0]:-}" ] || [ ! -f "${BASH_SOURCE[0]}" ]; then
  SELBST="$(mktemp /tmp/varianten-testen.XXXXXX.sh)"
  curl -fsSL "https://raw.githubusercontent.com/n1kob1ko/biko-bot/main/scripts/varianten-testen.sh" -o "$SELBST" || exit 1
  exec bash "$SELBST" "$@"
fi
cd "$ZIEL" || exit 1
KURZ="$ZIEL/user_data/backtest_results/VARIANTEN.txt"
LANG_="$ZIEL/user_data/backtest_results/VARIANTEN-lang.txt"

if [ "${1:-}" != "--vordergrund" ]; then
  echo "==> Bot-Code aktualisieren (holt die neuen Versuchs-Strategien)"
  curl -fsSL https://raw.githubusercontent.com/n1kob1ko/biko-bot/main/install.sh | BIKO_BOERSE="${BIKO_BOERSE:-kraken}" bash || exit 1
  : > "$KURZ"; : > "$LANG_"
  setsid nohup bash "$ZIEL/scripts/varianten-testen.sh" --vordergrund >/dev/null 2>&1 < /dev/null &
  echo
  echo "=================================================================="
  echo "  Läuft im Hintergrund (ca. 10 Minuten). Terminal darf zu."
  echo "  Fertig, wenn in $KURZ 'FERTIG' steht. Dann:"
  echo "  cat $KURZ"
  echo "=================================================================="
  exit 0
fi

exec > >(tee -a "$LANG_") 2>&1
kurz() { echo "$@" | tee -a "$KURZ"; }
kurz "Varianten-Test $(date -u '+%Y-%m-%d %H:%M UTC'), 2021-2023, Binance-Kurse, 0,5 % pro Seite, Kill-Switch aus"
kurz "Kursdaten: $(ls user_data/data/binance/*-4h.feather 2>/dev/null | wc -l) Paare (4h)"
for S in EmaTrendStrategy VersuchTrendAdx VersuchTrendWeiterStop BreakoutStrategy DipBuyStrategy; do
  echo; echo "------------------ $S ------------------"
  if BOT_CONFIG=config.binance.json FEE=0.005 KILLSWITCH=aus bash scripts/backtest.sh "$S" entw > "/tmp/bt-$S.txt" 2>&1; then
    cat "/tmp/bt-$S.txt"
    grep -E "^=== |^Bot \(|^BTC halten|^Größter|^Gewinnquote|^Ausstiege|^Pro Jahr|^-> " "/tmp/bt-$S.txt" | tee -a "$KURZ"
    kurz ""
  else
    cat "/tmp/bt-$S.txt"
    kurz "FEHLER bei $S (Details in $LANG_)"
  fi
done
kurz "FERTIG"
