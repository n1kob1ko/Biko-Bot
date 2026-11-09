# pragma pylint: disable=missing-docstring, invalid-name
"""
VERSUCH (nicht in der App wählbar): Trendfolger + Seitwärts-Filter.

Wie EmaTrendStrategy, aber Entry nur, wenn ADX(14) > 20, also wenn der Markt überhaupt
einen Trend hat. Idee: Im Seitwärts- und Bärenmarkt 2022 lief der Trendfolger 50-mal in den
-5-%-Stop. Der Filter soll diese Fehlsignale wegnehmen.
Vorher festgelegt, einmal getestet (scripts/varianten-testen.sh). Nicht nachträglich drehen.
"""

import talib.abstract as ta
from pandas import DataFrame

from EmaTrendStrategy import EmaTrendStrategy


class VersuchTrendAdx(EmaTrendStrategy):
    adx_period = 14
    adx_min = 20

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=self.adx_period)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        dataframe.loc[dataframe["adx"] <= self.adx_min, ["enter_long", "enter_tag"]] = (0, None)
        return dataframe
