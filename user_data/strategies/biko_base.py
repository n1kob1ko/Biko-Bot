# pragma pylint: disable=missing-docstring, invalid-name
"""
Biko Bot / BikoBase: gemeinsamer Unterbau aller Biko-Strategien (Spot, nur Long).

Hier steckt alles, was NICHT vom Signal abhängt und bei jeder Strategie gleich sein soll:
- Positionsgröße aus dem Kontorisiko (custom_stake_amount)
- Stop-Loss als Stop-Order direkt an der Börse (stoploss_on_exchange)
- Protections: CooldownPeriod, StoplossGuard, MaxDrawdown (Tageslimit -3 %)
- Kill-Switch: ab -15 % Konto-Drawdown (geschlossene Trades) keine neuen Entries mehr

Die eigentlichen Strategien (EmaTrendStrategy, BreakoutStrategy, DipBuyStrategy) erben von
BikoBase und definieren nur Indikatoren, Entry und Exit. So kann man in der Biko-App die
Strategie wechseln, ohne dass die Risikoschranken anders werden.

Über die Biko-App einstellbar (user_data/biko-settings.json, zweite --config):
Strategie, Coins (pair_whitelist), Takt (timeframe), max. Trades und Risiko pro Trade
(biko.risk_per_trade, 0,25 bis 3 %). Die Protections rechnen in Stunden und passen sich
dem Takt an. Stop-Loss und Kill-Switch bleiben fest.
"""

import logging
from datetime import datetime

from pandas import DataFrame

from freqtrade.exchange import timeframe_to_minutes
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy

logger = logging.getLogger(__name__)


class BikoBase(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "4h"
    can_short = False

    # Signale nur auf abgeschlossenen Kerzen auswerten
    process_only_new_candles = True
    # EMA200 braucht Vorlauf. Deutlich mehr als 200, weil eine EMA erst nach
    # einigen Vielfachen ihrer Länge stabil ist (prüfen mit recursive-analysis).
    # Kraken liefert max. 720 Kerzen über die API, darunter bleiben.
    startup_candle_count: int = 600

    # Standard: kein ROI-Ausstieg. Strategien können das überschreiben.
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
        # Kraken und Binance unterstützen Stop-Orders an der Börse (Spot). Greift auch,
        # wenn der Bot oder der VPS ausfällt.
        "stoploss_on_exchange": True,
        "stoploss_on_exchange_interval": 60,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    # --- Risikoparameter ------------------------------------------------------
    default_risk_per_trade = 0.01  # 1 % des Kontos pro Trade (Biko-App kann bis 3 % setzen)
    max_risk_per_trade = 0.03
    # Grober Aufschlag für Gebühren (Kauf + Verkauf) und Slippage des Market-Stops.
    # An die echten Gebühren deiner Stufe anpassen.
    cost_buffer = 0.01
    max_account_drawdown = 0.15  # Kill-Switch

    @property
    def risk_per_trade(self) -> float:
        """Risiko pro Trade aus der Biko-App (biko.risk_per_trade), begrenzt auf 0,25 bis 3 %."""
        try:
            value = float(self.config.get("biko", {}).get("risk_per_trade", self.default_risk_per_trade))
        except (TypeError, ValueError):
            value = self.default_risk_per_trade
        return min(max(value, 0.0025), self.max_risk_per_trade)

    def _candles(self, hours: float) -> int:
        """Stunden in Kerzen des aktuellen Takts umrechnen (mindestens 1)."""
        return max(1, round(hours * 60 / timeframe_to_minutes(self.timeframe)))

    @property
    def protections(self):
        # Protections stehen seit 2024.10 in der Strategie, nicht mehr in config.json.
        # In Stunden gedacht, damit sie bei jedem Takt (15m, 1h, 4h) gleich lange wirken.
        return [
            {
                # Nach einem Exit 8h kein Wiedereinstieg im selben Paar
                "method": "CooldownPeriod",
                "stop_duration_candles": self._candles(8),
            },
            {
                # 2 Stop-Losses (alle Paare) innerhalb von 2 Tagen -> 1 Tag Pause
                "method": "StoplossGuard",
                "lookback_period_candles": self._candles(48),
                "trade_limit": 2,
                "stop_duration_candles": self._candles(24),
                "only_per_pair": False,
            },
            {
                # Tageslimit: mehr als 3 % Konto-Drawdown in 24h -> 24h Pause
                "method": "MaxDrawdown",
                "calculation_mode": "equity",
                "lookback_period_candles": self._candles(24),
                "trade_limit": 1,
                "stop_duration_candles": self._candles(24),
                "max_allowed_drawdown": 0.03,
            },
        ]

    # --- Signale: definieren die Unterklassen -------------------------------------
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        raise NotImplementedError("BikoBase ist nur der Unterbau, bitte eine Biko-Strategie wählen.")

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        raise NotImplementedError("BikoBase ist nur der Unterbau, bitte eine Biko-Strategie wählen.")

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        raise NotImplementedError("BikoBase ist nur der Unterbau, bitte eine Biko-Strategie wählen.")

    # --- Positionsgröße: Kontorisiko / Stop-Abstand ---------------------------------
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
        Beispiel 500 € Konto, 1 % Risiko: 5 € / (0.05 + 0.01) ≈ 83 € Einsatz.
        Wird der Stop getroffen, gehen ca. 5 € (1 %) verloren.
        """
        account = self.wallets.get_total_stake_amount()
        risk_eur = account * self.risk_per_trade
        stake = risk_eur / (abs(self.stoploss) + self.cost_buffer)

        if min_stake is not None and stake < min_stake:
            # Lieber kein Trade als einer mit mehr Risiko als eingestellt
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
