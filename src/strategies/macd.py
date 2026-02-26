"""MACD Strategy for moderate trending markets."""
import logging
import time
from typing import Optional, Dict, Any
from .base import TradingStrategy
from ..indicators import calculate_macd
from ..config_utils import require_bool, require_float, require_int

logger = logging.getLogger(__name__)


class MACDStrategy(TradingStrategy):
    """
    MACD (Moving Average Convergence Divergence) Strategy.

    This strategy uses MACD crossovers to identify trend changes
    and momentum shifts. Works well in moderate trending markets.

    Strategy Logic:
    - BUY: MACD line crosses above signal line + histogram positive
    - SELL: MACD line crosses below signal line + histogram negative
    - Better for medium-term trends than SMA crossover
    """

    def __init__(self, config: dict):
        """
        Initialize MACD strategy.

        Args:
            config: Strategy configuration
        """
        super().__init__(config)

        # MACD parameters
        self.fast_period = require_int(config, 'MACD_FAST')
        self.slow_period = require_int(config, 'MACD_SLOW')
        self.signal_period = require_int(config, 'MACD_SIGNAL')

        # Histogram confirmation
        self.require_histogram_confirm = require_bool(config, 'MACD_HISTOGRAM_CONFIRM')

        # Profit target checking (matches SMA Crossover behaviour)
        self.min_profit_target = require_float(config, 'MIN_PROFIT_TARGET')
        # entry_price is inherited from TradingStrategy base class
        self.entry_time = None

        # Minimum hold time (seconds) to prevent whipsaws
        self.min_hold_time = require_int(config, 'MIN_HOLD_TIME')

        # Track previous MACD values for crossover detection
        self.prev_macd_line = None
        self.prev_signal_line = None

        logger.info(f"MACD Strategy initialized:")
        logger.info(f"  Fast: {self.fast_period}, Slow: {self.slow_period}, Signal: {self.signal_period}")
        logger.info(f"  Histogram Confirmation: {self.require_histogram_confirm}")
        logger.info(f"  Min Profit Target: {self.min_profit_target*100:.2f}%")
        logger.info(f"  Min Hold Time: {self.min_hold_time}s ({self.min_hold_time/60:.1f} min)")

    def get_strategy_name(self) -> str:
        """Return strategy name."""
        return f"MACD ({self.fast_period}/{self.slow_period}/{self.signal_period})"

    def analyze(self, market_data: Dict[str, Any]) -> Optional[str]:
        """
        Analyze market data for MACD signals.

        Args:
            market_data: Market data dictionary

        Returns:
            'buy', 'sell', or None
        """
        ohlc = market_data.get('ohlc')

        # --- Stop-loss check (before any indicator computation) ---
        quick_price = self._peek_price(market_data)
        if quick_price is not None:
            stop = self.check_stop_loss(quick_price)
            if stop:
                return stop

        # Prefer committed OHLC close series for indicator correctness.
        if isinstance(ohlc, dict) and ohlc.get('closes'):
            prices = list(ohlc['closes'])
            current_price = (
                float(ohlc['latest']['close'])
                if isinstance(ohlc.get('latest'), dict) and 'close' in ohlc['latest']
                else float(prices[-1])
            )
            self.add_price(current_price)

            required = self.slow_period + self.signal_period
            if len(prices) < required:
                logger.info(f"Collecting data... ({len(prices)}/{required})")
                return None
        else:
            # Fallback: Extract current price from ticker
            ticker_data = market_data.get('ticker', {})
            pair_key = self._find_pair_key(ticker_data)

            if not pair_key:
                logger.error("Trading pair not found in ticker data")
                return None

            current_price = float(ticker_data[pair_key]['c'][0])
            self.add_price(current_price)

            required = self.slow_period + self.signal_period
            if not self.has_sufficient_data(required):
                logger.info(f"Collecting data... ({len(self.price_history)}/{required})")
                return None

            prices = self.get_prices()

        # Calculate MACD
        macd_result = calculate_macd(prices, self.fast_period, self.slow_period, self.signal_period)

        if macd_result is None:
            logger.warning("Unable to calculate MACD")
            return None

        macd_line, signal_line, histogram = macd_result

        # Log current state
        logger.info(f"Price: ${current_price:.2f} | MACD: {macd_line:.2f} | Signal: {signal_line:.2f} | Hist: {histogram:.2f}")

        # Detect crossover
        signal = None

        if self.prev_macd_line is not None and self.prev_signal_line is not None:

            # BULLISH CROSSOVER: MACD crosses above signal
            if self.prev_macd_line <= self.prev_signal_line and macd_line > signal_line:
                logger.info("🟢 BULLISH MACD CROSSOVER!")

                # Check histogram confirmation if required
                if self.require_histogram_confirm and histogram <= 0:
                    logger.info("  Waiting for histogram confirmation (currently negative)")
                else:
                    logger.info("  ✓ MACD crossed above signal")
                    if self.require_histogram_confirm:
                        logger.info("  ✓ Histogram positive")
                    signal = 'buy'

            # BEARISH CROSSOVER: MACD crosses below signal
            elif self.prev_macd_line >= self.prev_signal_line and macd_line < signal_line:
                logger.info("🔴 BEARISH MACD CROSSOVER!")

                # Check histogram confirmation if required
                if self.require_histogram_confirm and histogram >= 0:
                    logger.info("  Waiting for histogram confirmation (currently positive)")
                else:
                    logger.info("  ✓ MACD crossed below signal")
                    if self.require_histogram_confirm:
                        logger.info("  ✓ Histogram negative")
                    signal = 'sell'

        # PROFIT TARGET CHECK before selling
        if signal == 'sell' and self.entry_price is not None:
            profit_pct = (current_price - self.entry_price) / self.entry_price

            if profit_pct < self.min_profit_target:
                logger.debug(f"⚠️ SELL signal ignored - profit too low:")
                logger.debug(f"  Current profit: {profit_pct*100:.2f}% < Target: {self.min_profit_target*100:.2f}%")
                logger.debug(f"  Entry: ${self.entry_price:,.2f} → Current: ${current_price:,.2f}")
                signal = None  # Don't sell yet

        # FEE-AWARE BREAKEVEN CHECK: don't sell below round-trip fee cost
        if signal == 'sell' and not self.is_above_breakeven(current_price):
            logger.debug(
                f"⚠️ SELL signal ignored - below fee-adjusted breakeven "
                f"(round-trip fee ~{self._roundtrip_fee_pct*100:.2f}%)"
            )
            signal = None

        # MINIMUM HOLD TIME CHECK
        if signal == 'sell' and self.entry_time is not None:
            hold_time = time.time() - self.entry_time
            if hold_time < self.min_hold_time:
                logger.info(f"⚠️ SELL signal ignored - hold time too short:")
                logger.info(f"  Held for: {hold_time:.0f}s ({hold_time/60:.1f}min) < Min: {self.min_hold_time}s ({self.min_hold_time/60:.1f}min)")
                signal = None  # Don't sell yet

        # Update previous values
        self.prev_macd_line = macd_line
        self.prev_signal_line = signal_line

        # Track entry/exit price and time
        if signal == 'buy':
            self.entry_price = current_price
            self.entry_time = time.time()
            logger.info(f"📊 Entry tracked: ${self.entry_price:,.2f} at {time.strftime('%H:%M:%S', time.localtime(self.entry_time))}")
        elif signal == 'sell':
            self.entry_price = None
            self.entry_time = None

        # Log current trend if no signal
        if signal is None:
            if macd_line > signal_line:
                trend = "BULLISH"
                momentum = "Strong" if histogram > 0 else "Weakening"
            else:
                trend = "BEARISH"
                momentum = "Strong" if histogram < 0 else "Weakening"

            logger.info(f"Trend: {trend} ({momentum}) | Position: {self.position or 'None'}")

        return signal

    def reset(self) -> None:
        """Reset strategy state."""
        super().reset()
        self.prev_macd_line = None
        self.prev_signal_line = None
        # entry_price is cleared by super().reset()
        self.entry_time = None
