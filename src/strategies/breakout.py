"""Breakout Strategy for volatile markets."""
import logging
from typing import Optional, Dict, Any
from .base import TradingStrategy
from ..indicators import (
    calculate_atr,
    calculate_volume_surge,
    detect_support_resistance,
    find_swing_high_low,
    calculate_fibonacci_extensions,
    is_near_fibonacci_level
)

logger = logging.getLogger(__name__)


class BreakoutStrategy(TradingStrategy):
    """
    Breakout Strategy for volatile markets.

    This strategy identifies when price breaks out of established ranges
    with strong volume, indicating a potential new trend.

    Strategy Logic:
    - BUY: Price breaks above resistance + volume surge + ATR high
    - SELL: Price breaks below support + volume surge + ATR high
    - EXIT: Price returns to range or hits stop loss
    """

    def __init__(self, config: dict):
        """
        Initialize Breakout strategy.

        Args:
            config: Strategy configuration
        """
        super().__init__(config)

        # Breakout parameters
        self.atr_period = int(config.get('ATR_PERIOD', 14))
        self.atr_multiplier = float(config.get('ATR_MULTIPLIER', 1.5))
        self.volume_threshold = float(config.get('VOLUME_THRESHOLD', 1.5))
        self.lookback_period = int(config.get('BREAKOUT_LOOKBACK', 20))

        # Retest confirmation
        self.require_retest = config.get('REQUIRE_RETEST', 'false').lower() == 'true'

        # Track breakout levels
        self.last_resistance = None
        self.last_support = None
        self.breakout_confirmed = False
        self.breakout_type = None  # 'bullish' or 'bearish'

        # Volume history
        self.volume_history = []

        # Fibonacci analysis settings (for profit targets)
        self.use_fibonacci = config.get('USE_FIBONACCI', 'true').lower() == 'true'
        self.fib_lookback_period = int(config.get('FIB_LOOKBACK_PERIOD', 50))

        logger.info(f"Breakout Strategy initialized:")
        logger.info(f"  ATR Period: {self.atr_period}, Multiplier: {self.atr_multiplier}x")
        logger.info(f"  Volume Threshold: {self.volume_threshold}x average")
        logger.info(f"  Lookback: {self.lookback_period} periods")
        logger.info(f"  Require Retest: {self.require_retest}")
        logger.info(f"  Fibonacci: {'Enabled' if self.use_fibonacci else 'Disabled'} (lookback: {self.fib_lookback_period})")

    def get_strategy_name(self) -> str:
        """Return strategy name."""
        return "Breakout"

    def analyze(self, market_data: Dict[str, Any]) -> Optional[str]:
        """
        Analyze market data for breakout signals.

        Args:
            market_data: Market data dictionary

        Returns:
            'buy', 'sell', or None
        """
        ohlc = market_data.get('ohlc')

        # Prefer committed OHLC candles for correctness (high/low/volume per candle).
        if isinstance(ohlc, dict) and ohlc.get('closes') and ohlc.get('highs') and ohlc.get('lows'):
            closes = list(ohlc['closes'])
            highs = list(ohlc['highs'])
            lows = list(ohlc['lows'])
            volumes = list(ohlc.get('volumes') or [])
            current_price = float(ohlc['latest']['close']) if isinstance(ohlc.get('latest'), dict) else float(closes[-1])

            # Keep internal history in sync for any base-class helpers.
            self.add_price(current_price)
            if volumes:
                self.volume_history = volumes[-self.price_history.maxlen:]

            # Need enough data across indicators.
            required = max(self.lookback_period + 1, self.atr_period + 1, 21)
            if len(closes) < required:
                logger.info(f"Collecting data... ({len(closes)}/{required})")
                return None

            prices = closes
        else:
            # Fallback: use ticker (less accurate for ATR/volume).
            ticker_data = market_data.get('ticker', {})
            pair_key = self._find_pair_key(ticker_data)

            if not pair_key:
                logger.error("Trading pair not found in ticker data")
                return None

            ticker = ticker_data[pair_key]
            current_price = float(ticker['c'][0])
            current_volume = float(ticker['v'][1])  # 24h volume (fallback only)

            self.add_price(current_price)
            self.volume_history.append(current_volume)

            required = max(self.atr_period, self.lookback_period)
            if not self.has_sufficient_data(required):
                logger.info(f"Collecting data... ({len(self.price_history)}/{required})")
                return None

            prices = self.get_prices()

            highs = [p * 1.005 for p in prices]
            lows = [p * 0.995 for p in prices]

        # Detect support and resistance levels
        support_levels, resistance_levels = detect_support_resistance(
            prices,
            window=10,
            threshold=0.02
        )

        if not support_levels or not resistance_levels:
            logger.info("No clear support/resistance detected yet")
            return None

        # Get nearest levels
        self.last_resistance = min([r for r in resistance_levels if r > current_price], default=None)
        self.last_support = max([s for s in support_levels if s < current_price], default=None)

        # Calculate Fibonacci extension levels if enabled (for profit targets)
        fib_extensions = None
        if self.use_fibonacci and len(prices) >= self.fib_lookback_period:
            swing_points = find_swing_high_low(prices, self.fib_lookback_period)
            if swing_points:
                swing_high, swing_low = swing_points
                fib_extensions = calculate_fibonacci_extensions(swing_high, swing_low)

                # Log Fibonacci extension targets
                logger.info(f"📐 Fibonacci Extension Targets:")
                logger.info(f"   127.2%: ${fib_extensions['127.2%']:,.0f} | 161.8%: ${fib_extensions['161.8%']:,.0f} | 261.8%: ${fib_extensions['261.8%']:,.0f}")

        # Calculate ATR for volatility confirmation
        atr = calculate_atr(highs, lows, prices, self.atr_period)

        if atr is None:
            return None

        # Check for volume surge (prefer per-candle volumes; fallback uses 24h volume history)
        volume_series = self.volume_history
        if isinstance(ohlc, dict) and ohlc.get('volumes'):
            volume_series = list(ohlc['volumes'])

        volume_surge = calculate_volume_surge(volume_series, period=20, threshold=self.volume_threshold)

        # Log current state
        logger.info(f"Price: ${current_price:,.2f} | ATR: ${atr:.2f} | Vol Surge: {volume_surge}")
        if self.last_resistance:
            logger.info(f"Resistance: ${self.last_resistance:,.2f} ({current_price/self.last_resistance*100-100:+.1f}%)")
        if self.last_support:
            logger.info(f"Support: ${self.last_support:,.2f} ({current_price/self.last_support*100-100:+.1f}%)")

        # Detect breakout conditions

        def atr_is_high(lookback: int = 20) -> bool:
            # Compare current ATR to average ATR over recent windows.
            if len(prices) < self.atr_period + 2:
                return False
            start = max(self.atr_period + 1, len(prices) - (lookback + self.atr_period))
            atr_vals = []
            for end in range(start, len(prices) + 1):
                window_highs = highs[max(0, end - (self.atr_period + 1)):end]
                window_lows = lows[max(0, end - (self.atr_period + 1)):end]
                window_closes = prices[max(0, end - (self.atr_period + 1)):end]
                v = calculate_atr(window_highs, window_lows, window_closes, self.atr_period)
                if v is not None:
                    atr_vals.append(v)
            if len(atr_vals) < 3:
                return False
            avg_atr = sum(atr_vals[:-1]) / max(1, (len(atr_vals) - 1))
            return avg_atr > 0 and atr >= avg_atr

        # BULLISH BREAKOUT: Breaking above resistance
        if self.last_resistance and current_price > self.last_resistance:
            # Check confirmations
            atr_high = atr_is_high()

            if volume_surge and atr_high:
                logger.info(f"🚀 BULLISH BREAKOUT DETECTED!")
                logger.info(f"  ✓ Price broke resistance ${self.last_resistance:,.2f}")
                logger.info(f"  ✓ Volume surge confirmed ({self.volume_threshold}x)")
                logger.info(f"  ✓ High volatility (ATR)")

                # Log Fibonacci profit targets if available
                if fib_extensions:
                    logger.info(f"  📊 Profit Targets (Fibonacci Extensions):")
                    logger.info(f"     Target 1: ${fib_extensions['127.2%']:,.0f} (127.2%)")
                    logger.info(f"     Target 2: ${fib_extensions['161.8%']:,.0f} (161.8% - Golden Ratio)")
                    logger.info(f"     Target 3: ${fib_extensions['261.8%']:,.0f} (261.8%)")

                if not self.require_retest or self.breakout_confirmed:
                    return 'buy'
                else:
                    self.breakout_confirmed = True
                    self.breakout_type = 'bullish'
                    logger.info("  Waiting for retest confirmation...")
                    return None

        # BEARISH BREAKOUT: Breaking below support
        elif self.last_support and current_price < self.last_support:
            atr_high = atr_is_high()

            if volume_surge and atr_high:
                logger.info(f"🔻 BEARISH BREAKOUT DETECTED!")
                logger.info(f"  ✓ Price broke support ${self.last_support:,.2f}")
                logger.info(f"  ✓ Volume surge confirmed ({self.volume_threshold}x)")
                logger.info(f"  ✓ High volatility (ATR)")

                # Note: For bearish breakouts, consider inverse Fibonacci extensions
                if fib_extensions:
                    logger.info(f"  ⚠️  Consider exiting positions or setting stop losses")

                if not self.require_retest or self.breakout_confirmed:
                    return 'sell'
                else:
                    self.breakout_confirmed = True
                    self.breakout_type = 'bearish'
                    logger.info("  Waiting for retest confirmation...")
                    return None

        # Check for retest if breakout was detected
        if self.breakout_confirmed:
            if self.breakout_type == 'bullish' and self.last_resistance:
                # Price should be near resistance (now support)
                if abs(current_price - self.last_resistance) / self.last_resistance < 0.02:
                    logger.info("✓ Retest confirmed! Price holding above old resistance")
                    self.breakout_confirmed = False
                    return 'buy'

            elif self.breakout_type == 'bearish' and self.last_support:
                # Price should be near support (now resistance)
                if abs(current_price - self.last_support) / self.last_support < 0.02:
                    logger.info("✓ Retest confirmed! Price holding below old support")
                    self.breakout_confirmed = False
                    return 'sell'

        # No breakout signal
        status = "Within range"
        if self.last_support and self.last_resistance:
            range_position = (current_price - self.last_support) / (self.last_resistance - self.last_support) * 100
            status = f"In range ({range_position:.0f}% from support to resistance)"

        logger.info(f"Status: {status} | Position: {self.position or 'None'}")
        return None

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
        self.last_resistance = None
        self.last_support = None
        self.breakout_confirmed = False
        self.breakout_type = None
        self.volume_history.clear()
