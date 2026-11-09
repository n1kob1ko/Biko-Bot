#!/usr/bin/env python3
"""
Steuer-Export: alle abgeschlossenen Trades eines Jahres als CSV (für Excel, Trennzeichen ;).

    cd /opt/biko-bot
    python3 scripts/steuer_export.py 2027                       # Echtgeld-Datenbank
    python3 scripts/steuer_export.py 2027 user_data/tradesv3.sqlite   # Testmodus (zum Ausprobieren)

Schreibt user_data/steuer/trades-<jahr>.csv und zeigt die Summe für das Jahr.

Hinweise (Österreich, keine Steuerberatung):
- Krypto-Gewinne: 27,5 % Sondersteuersatz. Kraken/Binance ziehen keine KESt ab, also selbst in der
  Steuererklärung (E1kv) angeben. Gewinne und Verluste aus Krypto eines Jahres werden verrechnet.
- Der Bot kauft und verkauft jeden Coin komplett. Hältst du DENSELBEN Coin zusätzlich privat auf
  demselben Börsenkonto, gilt der gleitende Durchschnittspreis über alles. Dann stimmt diese Liste
  nicht 1:1. Am einfachsten: ein eigenes Börsenkonto (oder Unterkonto) nur für den Bot.
- Die Gebühren sind im Gewinn schon abgezogen. Zur Kontrolle mit dem Jahres-Export der Börse vergleichen.
Nur Python-Standardbibliothek.
"""

import csv
import os
import sqlite3
import sys
from datetime import datetime

KEST = 0.275


def main():
    if len(sys.argv) < 2 or not sys.argv[1].isdigit():
        print(__doc__)
        sys.exit(1)
    year = int(sys.argv[1])
    db = sys.argv[2] if len(sys.argv) > 2 else "user_data/tradesv3.live.sqlite"
    if not os.path.exists(db):
        sys.exit(f"Datenbank {db} gibt es nicht.")

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT id, pair, open_date, close_date, amount, open_rate, close_rate,
               fee_open_cost, fee_close_cost, stake_amount, close_profit_abs, exit_reason
        FROM trades
        WHERE is_open = 0 AND close_date >= ? AND close_date < ?
        ORDER BY close_date
        """,
        (f"{year}-01-01", f"{year + 1}-01-01"),
    ).fetchall()

    out_dir = os.path.join(os.path.dirname(db) or ".", "steuer")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"trades-{year}.csv")

    def de(x, digits=2):
        return f"{x:.{digits}f}".replace(".", ",") if x is not None else ""

    total = 0.0
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow([
            "Trade", "Paar", "Kauf (UTC)", "Verkauf (UTC)", "Menge", "Kaufkurs", "Verkaufskurs",
            "Einsatz", "Gebühr Kauf", "Gebühr Verkauf", "Gewinn/Verlust nach Gebühren", "Grund",
        ])
        for r in rows:
            profit = r["close_profit_abs"] or 0.0
            total += profit
            w.writerow([
                r["id"], r["pair"], str(r["open_date"])[:19], str(r["close_date"])[:19],
                de(r["amount"], 8), de(r["open_rate"], 6), de(r["close_rate"], 6),
                de(r["stake_amount"]), de(r["fee_open_cost"], 4), de(r["fee_close_cost"], 4),
                de(profit), r["exit_reason"] or "",
            ])
        w.writerow([])
        w.writerow(["Summe", "", "", "", "", "", "", "", "", "", de(total), ""])

    print(f"{len(rows)} Trades in {year} -> {out}")
    print(f"Summe Gewinn/Verlust: {total:.2f} EUR")
    if total > 0:
        print(f"Grobe Steuer (27,5 %): {total * KEST:.2f} EUR  (keine Steuerberatung)")
    print(f"Erstellt {datetime.now():%d.%m.%Y %H:%M}")


if __name__ == "__main__":
    main()
