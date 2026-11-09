# pragma pylint: disable=missing-docstring, invalid-name
"""
Biko Bot / BreakoutStrategy ("Ausbruch"): Donchian-Ausbruch (Spot, nur Long).

Idee: Wenn der Kurs über das Hoch der letzten 20 Kerzen steigt, beginnt oft eine
neue Bewegung. Der Bot kauft den Ausbruch und steigt aus, wenn der Kurs unter das
Tief der letzten 10 Kerzen fällt. Klassisches "Turtle"-Prinzip, stark vereinfacht.

Entry:  Close > höchstes Hoch der letzten 20 Kerzen (ohne die aktuelle) und Close > EMA200
Exit:   Close < tiefstes Tief der letzten 10 Kerzen (ohne die aktuelle)
Stop:   -5 %, als Stop-Order direkt an der Börse (siehe BikoBase)

Risiko, Positionsgröße, Protections und Kill-Switch kommen aus BikoBase.
Die Kanal-Werte sind um eine Kerze verschoben (shift), damit die Strategie nicht
in die aktuelle Kerze "hineinschaut" (prüfen mit lookahead-analysis).
Noch nicht im Backtest geprüft: vor Echtgeld erst Testmodus und Backtest.
"""

import talib.abstract as ta
from pandas import DataFrame

from biko_base import BikoBase


class BreakoutStrategy(BikoBase):
    INTERFACE_VERSION = 3

    minimal_roi = {"0": 100.0}
    stoploss = -0.05

    # --- Strategieparameter ---------------------------------------------------
    channel_entry = 20  # Ausbruch über das 20-Kerzen-Hoch
    channel_exit = 10   # Ausstieg unter das 10-Kerzen-Tief
    ema_trend = 200

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=self.ema_trend)
        # Kanal aus den VORHERIGEN Kerzen: shift(1), sonst wäre das aktuelle Hoch immer dabei.
        dataframe["dc_high"] = dataframe["high"].rolling(self.channel_entry).max().shift(1)
        dataframe["dc_low"] = dataframe["low"].rolling(self.channel_exit).min().shift(1)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] > dataframe["dc_high"])
            & (dataframe["close"] > dataframe["ema_trend"])
            & (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"],
        ] = (1, "breakout")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] < dataframe["dc_low"]) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"],
        ] = (1, "channel_low")
        return dataframe
