#!/usr/bin/env bash
# Backtest wie für Echtgeld gedacht: realistische Kosten, Protections an, Vergleich mit BTC halten.
#
#   scripts/backtest.sh                           # Trendfolger, Entwicklungs-Zeitraum, Kraken-Kosten
#   scripts/backtest.sh BreakoutStrategy valid    # andere Strategie, Validierungs-Zeitraum
#   PRUEFEN=ja scripts/backtest.sh                # zusätzlich lookahead- und recursive-analysis
#
# Zeiträume (Out-of-Sample, siehe README): entw = 2021-2023, valid = 2024, final = ab 2025.
# "final" nur EINMAL laufen lassen, wenn die Regeln feststehen. Danach nichts mehr an den Regeln drehen.
#
# Kosten: FEE=0.005 pro Seite = Kraken-Taker 0,40 % + 0,10 % für Spread und Slippage (Stop-Loss im
# Crash, Market-Orders). Zum Vergleich mit FEE=0.0025 (nur Maker) laufen lassen. Wenn die Strategie
# nur mit kleinen Gebühren gewinnt, ist sie für Echtgeld nicht gut genug.
# Daten: vorher einmal laden (siehe README, Kraken braucht die CSV-Variante).
set -euo pipefail
cd "$(dirname "$0")/.."

STRATEGIE="${1:-EmaTrendStrategy}"
PHASE="${2:-entw}"
FEE="${FEE:-0.005}"
TAKT="${TAKT:-4h}"
CONFIG="${BOT_CONFIG:-config.json}"
case "$PHASE" in
  entw)  ZEIT="20210101-20231231" ;;
  valid) ZEIT="20240101-20241231" ;;
  final) ZEIT="20250101-" ;;
  *)     ZEIT="$PHASE" ;;   # eigener Zeitraum, z. B. 20220101-20221231
esac
BOERSE="kraken"; [ "$CONFIG" = "config.binance.json" ] && BOERSE="binance"

FT=(docker compose run --rm freqtrade)
CFG=(--config "/freqtrade/user_data/$CONFIG")

echo "==> Backtest $STRATEGIE, $ZEIT, Takt $TAKT, Gebühr $FEE pro Seite ($BOERSE)"
"${FT[@]}" backtesting "${CFG[@]}" --strategy "$STRATEGIE" --timeframe "$TAKT" \
  --timerange "$ZEIT" --fee "$FEE" --enable-protections --breakdown month --export trades

echo "==> Vergleich mit BTC halten (vor und nach 27,5 % Steuer)"
docker compose run --rm -v "$(pwd)/scripts:/scripts:ro" --entrypoint python freqtrade \
  /scripts/vergleich.py /freqtrade/user_data/backtest_results "/freqtrade/user_data/data/$BOERSE" BTC/EUR

if [ "${PRUEFEN:-}" = "ja" ]; then
  echo "==> lookahead-analysis (has_bias muss False sein)"
  "${FT[@]}" lookahead-analysis "${CFG[@]}" --strategy "$STRATEGIE" --timeframe "$TAKT" --timerange "$ZEIT"
  echo "==> recursive-analysis (Abweichung bei 600 Kerzen sollte ~0 % sein)"
  "${FT[@]}" recursive-analysis "${CFG[@]}" --strategy "$STRATEGIE" --timeframe "$TAKT" \
    --timerange "$ZEIT" --startup-candle 200 400 600 1000
fi
