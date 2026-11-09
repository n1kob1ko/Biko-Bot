# pragma pylint: disable=missing-docstring, invalid-name
"""
Biko Bot / EmaTrendStrategy ("Trendfolger"): einfache Trendfolge (Spot, nur Long).

Entry:  EMA20 > EMA50 und Close > EMA200   (Regime-Filter: nur Long über dem 200er)
Exit:   EMA20 < EMA50
Stop:   -5 %, als Stop-Order direkt an der Börse (siehe BikoBase)

Risiko, Positionsgröße, Protections und Kill-Switch kommen aus BikoBase.
Bewusst wenige Parameter (3 EMA-Längen + Stop), um Overfitting klein zu halten.
Getestet wurde diese Strategie mit 4h-Kerzen und BTC/ETH/SOL.
"""

import talib.abstract as ta
from pandas import DataFrame

from biko_base import BikoBase


class EmaTrendStrategy(BikoBase):
    INTERFACE_VERSION = 3

    # Kein ROI-Ausstieg: Trendfolge lässt Gewinne laufen, Exit nur per Signal oder Stop.
    minimal_roi = {"0": 100.0}
    stoploss = -0.05

    # --- Strategieparameter (bewusst nicht hyperopt-fähig gemacht) ---------
    ema_fast = 20
    ema_slow = 50
    ema_trend = 200

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.ema_fast)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=self.ema_slow)
        dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=self.ema_trend)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["ema_fast"] > dataframe["ema_slow"])
            & (dataframe["close"] > dataframe["ema_trend"])
            & (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"],
        ] = (1, "ema_trend")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["ema_fast"] < dataframe["ema_slow"]) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"],
        ] = (1, "ema_cross_down")
        return dataframe
