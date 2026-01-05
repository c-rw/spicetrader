"""MACD Strategy for moderate trending markets."""
import logging
from typing import Optional, Dict, Any
from .base import TradingStrategy
from ..indicators import calculate_macd
from ..config_utils import require_bool, require_int

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

        # Track previous MACD values for crossover detection
        self.prev_macd_line = None
        self.prev_signal_line = None

        logger.info(f"MACD Strategy initialized:")
        logger.info(f"  Fast: {self.fast_period}, Slow: {self.slow_period}, Signal: {self.signal_period}")
        logger.info(f"  Histogram Confirmation: {self.require_histogram_confirm}")

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

        # Update previous values
        self.prev_macd_line = macd_line
        self.prev_signal_line = signal_line

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

    def _find_pair_key(self, ticker_data: dict) -> Optional[str]:
        """Find the actual trading pair key in ticker response."""
        # Try common variations
        variations = ['XBTUSD', 'XXBTZUSD', 'BTCUSD', 'ETHUSD', 'XETHZUSD', 'SOLUSD', 'XRPUSD', 'XXRPZUSD']

        for variation in variations:
            if variation in ticker_data:
                return variation

        # Return first key if none match
        if ticker_data:
            return list(ticker_data.keys())[0]

        return None

    def reset(self) -> None:
        """Reset strategy state."""
        super().reset()
        self.prev_macd_line = None
        self.prev_signal_line = None
