# pragma pylint: disable=missing-docstring, invalid-name
"""
Biko Bot / DipBuyStrategy ("Rücksetzer"): Rücksetzer im Aufwärtstrend kaufen (Spot, nur Long).

Idee: Ein Coin, der insgesamt steigt (über EMA200), wird nach einem kurzen Durchhänger
(RSI unter 35) gekauft. Verkauft wird, sobald sich der Kurs erholt hat (RSI über 65)
oder 8 % Gewinn erreicht sind. Mean Reversion, aber nur mit dem Trend.

Entry:  Close > EMA200 und RSI(14) < 35
Exit:   RSI(14) > 65, oder +8 % Gewinn (minimal_roi)
Stop:   -5 %, als Stop-Order direkt an der Börse (siehe BikoBase)

Risiko, Positionsgröße, Protections und Kill-Switch kommen aus BikoBase.
Noch nicht im Backtest geprüft: vor Echtgeld erst Testmodus und Backtest.
"""

import talib.abstract as ta
from pandas import DataFrame

from biko_base import BikoBase


class DipBuyStrategy(BikoBase):
    INTERFACE_VERSION = 3

    # Gewinn mitnehmen: ab +8 % wird verkauft, egal was der RSI sagt.
    minimal_roi = {"0": 0.08}
    stoploss = -0.05

    # --- Strategieparameter ---------------------------------------------------
    rsi_period = 14
    rsi_entry = 35  # "Durchhänger": RSI darunter
    rsi_exit = 65   # "erholt": RSI darüber
    ema_trend = 200

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=self.ema_trend)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=self.rsi_period)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] > dataframe["ema_trend"])
            & (dataframe["rsi"] < self.rsi_entry)
            & (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"],
        ] = (1, "dip")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["rsi"] > self.rsi_exit) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"],
        ] = (1, "rsi_recovered")
        return dataframe
