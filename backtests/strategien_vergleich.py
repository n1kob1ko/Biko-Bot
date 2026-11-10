"""
Vergleicht einfache Strategien mit "BTC halten" und "Nichtstun" auf BTC/EUR (nur Spot).

Daten: backtests/daten/BTCEUR-1h.csv.gz (Binance-Stundenkerzen, über den Workflow "Kursdaten holen").
Aufruf: python backtests/strategien_vergleich.py  -> schreibt backtests/ERGEBNIS.md

Strategien
  1. Dip kaufen (Mean Reversion): kaufen, wenn der Kurs deutlich unter seinem Schnitt liegt,
     verkaufen bei kleinem Plus oder wenn er zurück am Schnitt ist; Notbremse bei -10 %.
  3. Halten mit Notausgang: BTC halten, verkaufen wenn der Kurs unter den 200-Tage-Schnitt fällt,
     wieder kaufen wenn er darüber steigt (optional mit Puffer gegen Hin und Her).
  4. Grid-Trading: Kapital in Stücke geteilt; je ein Stück kaufen, wenn der Kurs eine Stufe fällt,
     und mit einer Stufe Plus wieder verkaufen (Limit-Orders).
  Extra: Sparplan (DCA), jede Woche gleicher Betrag.

Gebühren: Kraken Spot, kleines Konto. Market-Order 0,26 % + 0,05 % Schlupf, Limit-Order 0,16 %.
Steuer: 27,5 % KESt grob auf den Gewinn am Ende (Verluste = 0 Steuer). Keine Steuerberatung.
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
START_KAPITAL = 300.0
FEE_MARKET = 0.0026 + 0.0005
FEE_LIMIT = 0.0016
KEST = 0.275

ZEITRAEUME = [
    ("2021", "2021-01-01", "2022-01-01"),
    ("2022", "2022-01-01", "2023-01-01"),
    ("2023", "2023-01-01", "2024-01-01"),
    ("2024", "2024-01-01", "2025-01-01"),
    ("2021–2024", "2021-01-01", "2025-01-01"),
    ("2025 bis heute (neu)", "2025-01-01", "2100-01-01"),
]


def lade_kerzen():
    df = pd.read_csv(ROOT / "daten" / "BTCEUR-1h.csv.gz", header=None).iloc[:, :6]
    df.columns = ["t", "open", "high", "low", "close", "volume"]
    t = df["t"].astype("int64")
    t = np.where(t > 1e14, t // 1000, t)  # Binance ab 2025 in Mikrosekunden
    df.index = pd.to_datetime(t, unit="ms", utc=True)
    df = df[~df.index.duplicated()].sort_index().drop(columns="t")
    # 200-Tage-Schnitt aus Tagesschlusskursen, erst am Folgetag bekannt (kein Blick in die Zukunft)
    daily = df["close"].resample("1D").last()
    sma200 = daily.rolling(200).mean().shift(1)
    df["sma200d"] = sma200.reindex(df.index, method="ffill")
    return df


def auf_4h(df):
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "sma200d": "last"}
    return df.resample("4h").agg(agg).dropna()


# ---------------------------------------------------------------- Strategien
# Jede Funktion bekommt die Kerzen des Zeitraums und gibt (Kontowert-Reihe, Anzahl Trades) zurück.

def btc_halten(d):
    menge = START_KAPITAL * (1 - FEE_MARKET) / d["close"].iloc[0]
    wert = menge * d["close"]
    wert.iloc[-1] *= 1 - FEE_MARKET  # am Ende verkaufen, damit vergleichbar
    return wert, 1


def nichtstun(d):
    return pd.Series(START_KAPITAL, index=d.index), 0


def notausgang(d, puffer=0.0):
    close, sma = d["close"].to_numpy(), d["sma200d"].to_numpy()
    eur, btc, trades = START_KAPITAL, 0.0, 0
    werte = np.empty(len(close))
    for i, (c, s) in enumerate(zip(close, sma)):
        if btc == 0 and c > s * (1 + puffer):
            btc, eur, trades = eur * (1 - FEE_MARKET) / c, 0.0, trades + 1
        elif btc > 0 and c < s * (1 - puffer):
            eur, btc, trades = btc * c * (1 - FEE_MARKET), 0.0, trades + 1
        werte[i] = eur + btc * c
    werte[-1] = eur + btc * close[-1] * (1 - FEE_MARKET)
    return pd.Series(werte, index=d.index), trades


def dip_kaufen(d, fenster, abstand, ziel, stop=0.10):
    close = d["close"].to_numpy()
    sma = d["close"].rolling(fenster).mean().to_numpy()
    eur, btc, einstieg, trades = START_KAPITAL, 0.0, 0.0, 0
    werte = np.empty(len(close))
    for i, c in enumerate(close):
        s = sma[i]
        if btc == 0 and not np.isnan(s) and c < s * (1 - abstand):
            btc, eur, einstieg, trades = eur * (1 - FEE_MARKET) / c, 0.0, c, trades + 1
        elif btc > 0 and (c >= einstieg * (1 + ziel) or c >= s or c <= einstieg * (1 - stop)):
            eur, btc, trades = btc * c * (1 - FEE_MARKET), 0.0, trades + 1
        werte[i] = eur + btc * c
    werte[-1] = eur + btc * close[-1] * (1 - FEE_MARKET)
    return pd.Series(werte, index=d.index), trades


def grid(d, stufe, stuecke):
    """Gleitendes Grid: nächste Kaufstufe liegt eine Stufe unter dem letzten Kauf bzw. Verkauf."""
    high, low, close = d["high"].to_numpy(), d["low"].to_numpy(), d["close"].to_numpy()
    stueck_eur = START_KAPITAL / stuecke
    eur, offen, trades = START_KAPITAL, [], 0  # offen: Liste (Kaufkurs, Menge)
    anker = close[0]
    werte = np.empty(len(close))
    for i in range(len(close)):
        # Verkäufe: jedes offene Stück mit +1 Stufe
        rest, verkauft = [], False
        for kurs, menge in offen:
            ziel = kurs * (1 + stufe)
            if high[i] >= ziel:
                eur += menge * ziel * (1 - FEE_LIMIT)
                trades += 1
                anker = ziel
                verkauft = True
            else:
                rest.append((kurs, menge))
        offen = rest
        # Steigt der Kurs ohne offene Stücke weiter, zieht der Anker mit
        if not offen and close[i] > anker:
            anker = close[i]
        # Käufe: so viele Stufen, wie der Kurs gefallen ist
        # Vorsichtig: nach einem Verkauf in dieser Kerze erst in der nächsten wieder kaufen,
        # weil man aus Stundenkerzen nicht weiß, ob zuerst das Hoch oder das Tief kam.
        while not verkauft and len(offen) < stuecke and eur >= stueck_eur * 0.99:
            kauf = anker * (1 - stufe)
            if low[i] > kauf:
                break
            menge = min(stueck_eur, eur) * (1 - FEE_LIMIT) / kauf
            eur -= min(stueck_eur, eur)
            offen.append((kauf, menge))
            trades += 1
            anker = kauf
        werte[i] = eur + sum(m for _, m in offen) * close[i]
    werte[-1] = eur + sum(m for _, m in offen) * close[-1] * (1 - FEE_MARKET)
    return pd.Series(werte, index=d.index), trades


def sparplan(d):
    """Jede Woche gleicher Betrag, verteilt über den Zeitraum; Rest liegt als Euro."""
    wochen = d.index.tz_localize(None).to_period("W").to_numpy()
    starts = np.r_[True, wochen[1:] != wochen[:-1]]
    rate = START_KAPITAL / starts.sum()
    close = d["close"].to_numpy()
    eur, btc, trades = START_KAPITAL, 0.0, 0
    werte = np.empty(len(close))
    for i, c in enumerate(close):
        if starts[i]:
            btc += rate * (1 - FEE_MARKET) / c
            eur -= rate
            trades += 1
        werte[i] = eur + btc * c
    werte[-1] = eur + btc * close[-1] * (1 - FEE_MARKET)
    return pd.Series(werte, index=d.index), trades


STRATEGIEN = {
    "BTC halten": (btc_halten, {}),
    "Nichtstun (Euro liegen lassen)": (nichtstun, {}),
    "Sparplan wöchentlich (DCA)": (sparplan, {}),
    "Notausgang 200-Tage-Schnitt": (notausgang, {}),
    "Notausgang 200-Tage-Schnitt, 3 % Puffer": (notausgang, {"puffer": 0.03}),
    "Dip kaufen: 5 % unter Schnitt, Ziel +3 %": (dip_kaufen, {"fenster": 48, "abstand": 0.05, "ziel": 0.03}),
    "Dip kaufen: 8 % unter Schnitt, Ziel +5 %": (dip_kaufen, {"fenster": 96, "abstand": 0.08, "ziel": 0.05}),
    "Grid: Stufe 2 %, 10 Stücke": (grid, {"stufe": 0.02, "stuecke": 10}),
    "Grid: Stufe 4 %, 10 Stücke": (grid, {"stufe": 0.04, "stuecke": 10}),
}


def kennzahlen(wert):
    ret = wert.iloc[-1] / START_KAPITAL - 1
    dd = (wert / wert.cummax() - 1).min()
    nach_steuer = ret * (1 - KEST) if ret > 0 else ret
    return ret, nach_steuer, dd


def main():
    h1 = lade_kerzen()
    daten = {"1h": h1, "4h": auf_4h(h1)}
    zeilen = []
    for tf, df in daten.items():
        for zr, von, bis in ZEITRAEUME:
            d = df[(df.index >= von) & (df.index < bis)].dropna()
            if len(d) < 100:
                continue
            for name, (fn, kw) in STRATEGIEN.items():
                kw = dict(kw)
                if fn is dip_kaufen and tf == "4h":
                    kw["fenster"] = kw["fenster"] // 4  # gleiche Zeitspanne in Stunden
                wert, trades = fn(d, **kw)
                ret, steuer, dd = kennzahlen(wert)
                zeilen.append(dict(tf=tf, zeitraum=zr, strategie=name, rendite=ret,
                                   nach_steuer=steuer, max_verlust=dd, trades=trades,
                                   ende=d.index[-1].date()))
    res = pd.DataFrame(zeilen)
    res.to_csv(ROOT / "ergebnis.csv", index=False)
    schreibe_md(res)
    print((ROOT / "ERGEBNIS.md").read_text())


def pct(x):
    return f"{x * 100:+.0f} %".replace("-", "−")


def schreibe_md(res):
    out = ["# Strategien gegen BTC halten (BTC/EUR, Spot)", "",
           f"Startkapital {START_KAPITAL:.0f} €, Gebühren wie Kraken (Market 0,26 % + 0,05 % Schlupf, "
           "Limit 0,16 %). Steuer grob 27,5 % KESt auf den Gewinn am Ende. "
           "„Max. Verlust“ = tiefster Rückgang vom Höchststand des Kontos.", ""]
    ende = res["ende"].max()
    for tf in ["1h", "4h"]:
        out += [f"## Bot schaut alle {tf.replace('h', ' Stunde(n)')} nach", ""]
        r = res[res.tf == tf]
        zr = list(dict.fromkeys(r.zeitraum))
        out.append("| Strategie | " + " | ".join(zr) + " | 21–24 nach Steuer | Max. Verlust 21–24 | Trades 21–24 |")
        out.append("|---" * (len(zr) + 4) + "|")
        for s in dict.fromkeys(r.strategie):
            rs = r[r.strategie == s].set_index("zeitraum")
            zellen = [pct(rs.loc[z, "rendite"]) for z in zr]
            out.append(f"| {s} | " + " | ".join(zellen)
                       + f" | {pct(rs.loc['2021–2024', 'nach_steuer'])} | {pct(rs.loc['2021–2024', 'max_verlust'])} | {rs.loc['2021–2024', 'trades']} |")
        out.append("")
    out += [f"Neuer Zeitraum (nicht zum Einstellen benutzt) endet am {ende}.", ""]
    (ROOT / "ERGEBNIS.md").write_text("\n".join(out))


if __name__ == "__main__":
    main()
