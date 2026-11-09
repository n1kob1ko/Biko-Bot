# pragma pylint: disable=missing-docstring, invalid-name
"""
Biko Bot / EmaTrendStrategy: einfache Trendfolge auf 4h-Kerzen (Spot, nur Long).

Entry:  EMA20 > EMA50 und Close > EMA200   (Regime-Filter: nur Long über dem 200er)
Exit:   EMA20 < EMA50
Stop:   -5 %, als Stop-Order direkt an der Börse (stoploss_on_exchange)
Größe:  1 % Kontorisiko pro Trade, abgeleitet aus dem Stop-Abstand (custom_stake_amount)

Risikoschranken, die unabhängig vom Signal greifen:
- Protections: StoplossGuard, CooldownPeriod, MaxDrawdown (Tageslimit -3 %)
- Kill-Switch: ab -15 % Konto-Drawdown (geschlossene Trades) keine neuen Entries mehr

Bewusst wenige Parameter (3 EMA-Längen + Stop), um Overfitting klein zu halten.
"""

import logging
from datetime import datetime

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy

logger = logging.getLogger(__name__)


class EmaTrendStrategy(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "4h"
    can_short = False

    # Signale nur auf abgeschlossenen Kerzen auswerten
    process_only_new_candles = True
    # EMA200 braucht Vorlauf. Deutlich mehr als 200, weil eine EMA erst nach
    # einigen Vielfachen ihrer Länge stabil ist (prüfen mit recursive-analysis).
    startup_candle_count: int = 600

    # Kein ROI-Ausstieg: Trendfolge lässt Gewinne laufen, Exit nur per Signal oder Stop.
    minimal_roi = {"0": 100.0}

    stoploss = -0.05
    trailing_stop = False

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "emergency_exit": "market",
        "force_entry": "market",
        "force_exit": "market",
        "stoploss": "market",
        # Kraken unterstützt Stop-Orders an der Börse (Spot). Greift auch,
        # wenn der Bot oder der VPS ausfällt.
        "stoploss_on_exchange": True,
        "stoploss_on_exchange_interval": 60,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    # --- Strategieparameter (bewusst nicht hyperopt-fähig gemacht) ---------
    ema_fast = 20
    ema_slow = 50
    ema_trend = 200

    # --- Risikoparameter ------------------------------------------------------
    risk_per_trade = 0.01  # 1 % des Kontos pro Trade
    # Grober Aufschlag für Gebühren (Kauf + Verkauf) und Slippage des Market-Stops.
    # An die echten Kraken-Gebühren deiner Stufe anpassen.
    cost_buffer = 0.01
    max_account_drawdown = 0.15  # Kill-Switch

    @property
    def protections(self):
        # Protections stehen seit 2024.10 in der Strategie, nicht mehr in config.json.
        # 1 Kerze = 4h
        return [
            {
                # Nach einem Exit 2 Kerzen (8h) kein Wiedereinstieg im selben Paar
                "method": "CooldownPeriod",
                "stop_duration_candles": 2,
            },
            {
                # 2 Stop-Losses (alle Paare) innerhalb von 2 Tagen -> 1 Tag Pause
                "method": "StoplossGuard",
                "lookback_period_candles": 12,
                "trade_limit": 2,
                "stop_duration_candles": 6,
                "only_per_pair": False,
            },
            {
                # Tageslimit: mehr als 3 % Konto-Drawdown in 24h -> 24h Pause
                "method": "MaxDrawdown",
                "calculation_mode": "equity",
                "lookback_period_candles": 6,
                "trade_limit": 1,
                "stop_duration_candles": 6,
                "max_allowed_drawdown": 0.03,
            },
        ]

    # -------------------------------------------------------------------------
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

    # --- Positionsgröße: 1 % Risiko -------------------------------------------
    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        """
        Positionsgröße = (Konto * Risiko) / (Stop-Abstand + Kosten)
        Beispiel 500 € Konto: 5 € / (0.05 + 0.01) ≈ 83 € Einsatz.
        Wird der Stop getroffen, gehen ca. 5 € (1 %) verloren.
        """
        account = self.wallets.get_total_stake_amount()
        risk_eur = account * self.risk_per_trade
        stake = risk_eur / (abs(self.stoploss) + self.cost_buffer)

        if min_stake is not None and stake < min_stake:
            # Lieber kein Trade als einer mit mehr als 1 % Risiko
            logger.info(
                f"{pair}: Einsatz {stake:.2f} unter Börsen-Minimum {min_stake:.2f}, Trade übersprungen."
            )
            return 0
        return min(stake, max_stake)

    # --- Kill-Switch: -15 % Drawdown ------------------------------------------
    def _max_closed_drawdown(self) -> float:
        """Größter Drawdown der Equity-Kurve aus geschlossenen Trades (0.0 bis 1.0)."""
        start = self.wallets.get_starting_balance()
        if not start:
            return 0.0
        trades = sorted(
            Trade.get_trades_proxy(is_open=False),
            key=lambda t: t.close_date_utc,
        )
        equity = peak = start
        max_dd = 0.0
        for t in trades:
            equity += t.close_profit_abs or 0.0
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak)
        return max_dd

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> bool:
        drawdown = self._max_closed_drawdown()
        if drawdown >= self.max_account_drawdown:
            # Bewusst dauerhaft: Freigabe nur durch manuelle Prüfung
            # (z. B. max_account_drawdown ändern oder neue DB starten).
            logger.warning(
                f"KILL-SWITCH: Konto-Drawdown {drawdown:.1%} >= "
                f"{self.max_account_drawdown:.0%}. Keine neuen Entries ({pair})."
            )
            return False
        return True
