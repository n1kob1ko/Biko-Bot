"""
Vergleicht den letzten Backtest mit "einfach BTC halten" im selben Zeitraum, vor und nach Steuer.
Läuft im Freqtrade-Container (braucht dessen Python-Pakete), wird von scripts/backtest.sh aufgerufen.

Steuer (Österreich, grob, keine Beratung): 27,5 % auf den Gewinn. Beim Halten zahlt man sie erst
beim Verkauf am Ende, beim Bot jedes Jahr auf die realisierten Gewinne. Für den Vergleich wird
vereinfacht beides am Ende versteuert (Verluste = 0 Steuer).
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

from freqtrade.configuration import TimeRange
from freqtrade.data.btanalysis import load_backtest_stats
from freqtrade.data.history import load_pair_history

KEST = 0.275


def after_tax(ret):
    return ret * (1 - KEST) if ret > 0 else ret


def ts(value):
    value = value / 1000 if value > 1e11 else value  # ms oder s
    return datetime.fromtimestamp(value, tz=timezone.utc)


def main():
    results_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "/freqtrade/user_data/backtest_results")
    data_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "/freqtrade/user_data/data/kraken")
    btc_pair = sys.argv[3] if len(sys.argv) > 3 else "BTC/EUR"

    stats = load_backtest_stats(results_dir)
    for name, s in stats["strategy"].items():
        start, end = ts(s["backtest_start_ts"]), ts(s["backtest_end_ts"])
        tr = TimeRange("date", "date", int(start.timestamp()), int(end.timestamp()))
        candles = load_pair_history(btc_pair, s["timeframe"], data_dir, timerange=tr)
        if candles.empty:
            print(f"Keine {btc_pair}-Kerzen in {data_dir}, BTC-Vergleich nicht möglich.")
            btc = None
        else:
            btc = candles["close"].iloc[-1] / candles["open"].iloc[0] - 1

        bot = s["profit_total"]
        print()
        print(f"=== {name}  {start:%Y-%m-%d} bis {end:%Y-%m-%d}  ({s['total_trades']} Trades) ===")
        print(f"Bot (nach Gebühren):       {bot:+8.1%}   nach Steuer ca. {after_tax(bot):+8.1%}")
        if btc is not None:
            print(f"BTC halten:                {btc:+8.1%}   nach Steuer ca. {after_tax(btc):+8.1%}")
        print(f"Größter Konto-Rückgang:    {s.get('max_drawdown_account', 0):8.1%}")
        if btc is not None:
            diff = after_tax(bot) - after_tax(btc)
            verdict = "BESSER als BTC halten" if diff > 0 else "SCHLECHTER als BTC halten"
            print(f"-> {verdict} ({diff:+.1%} Punkte nach Steuer)")


if __name__ == "__main__":
    main()
