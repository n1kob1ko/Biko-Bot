# Backtests: andere Strategien gegen BTC halten

Stand 10.11.2026. Ergebnisse in [ERGEBNIS.md](ERGEBNIS.md), Rohzahlen in `ergebnis.csv`.

Neu rechnen: `python backtests/strategien_vergleich.py` (braucht nur pandas und numpy).
Kursdaten erneuern: GitHub Actions > „Kursdaten holen“ > Run workflow
(lädt BTC/EUR-Stundenkerzen von data.binance.vision nach `backtests/daten/`).

## Fazit

- **Über 2021–2024 schlägt keine Strategie einfaches Halten** (+277 %). Am nächsten kommt
  „Notausgang 200-Tage-Schnitt mit 3 % Puffer“ (+266 %, nur 15 Trades), mit deutlich kleinerem
  Absturz zwischendurch (−54 % statt −74 %). Ohne Puffer springt er hunderte Male rein und raus
  und verliert viel an Gebühren.
- **Dip kaufen verliert** in allen Varianten über 2021–2024 (−25 % bis −57 %): in Abwärtsphasen
  fängt es „fallende Messer“, in Aufwärtsphasen verkauft es zu früh.
- **Grid** bringt rund +90 bis +100 % und hält die Schwankung kleiner (−40 %), verpasst aber den
  Großteil der starken Anstiege. In seitwärts/abwärts laufenden Zeiten (2025 bis heute) steht es
  besser da als Halten.
- **Sparplan (DCA)** hat den kleinsten Absturz (−33 %) bei +178 %, ganz ohne Bot.
- Ob der Bot jede Stunde oder alle 4 Stunden schaut, ändert wenig; beim Notausgang ohne Puffer
  ist 4 Stunden besser (weniger Fehlsignale).

Vereinfachungen: Steuer grob am Ende (in Wahrheit fällt sie bei Trades jährlich an), Gebühren
wie Kraken für kleine Konten, Grid ohne Füllungen innerhalb derselben Kerze nach einem Verkauf.
Vergangene Kurse sagen nichts Sicheres über die Zukunft.
