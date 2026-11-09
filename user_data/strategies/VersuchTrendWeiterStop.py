# pragma pylint: disable=missing-docstring, invalid-name
"""
VERSUCH (nicht in der App wählbar): Trendfolger mit weitem Stop.

Wie EmaTrendStrategy, aber Stop-Loss -10 % statt -5 %. Die Positionsgröße aus BikoBase
halbiert sich dadurch automatisch (Risiko pro Trade bleibt 1 % vom Konto).
Idee: 4-Stunden-Kerzen bei Krypto schwanken oft mehr als 5 %, der enge Stop wirft einen
aus Trends, die danach weiterlaufen. Dafür sind einzelne Verluste größer (in Euro gleich).
Vorher festgelegt, einmal getestet (scripts/varianten-testen.sh). Nicht nachträglich drehen.
"""

from EmaTrendStrategy import EmaTrendStrategy


class VersuchTrendWeiterStop(EmaTrendStrategy):
    stoploss = -0.10
