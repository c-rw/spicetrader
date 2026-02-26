"""Breakout Strategy for volatile markets."""
import logging
from collections import deque
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
from ..config_utils import require_bool, require_float, require_int

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
        self.atr_period = require_int(config, 'ATR_PERIOD')
        self.atr_multiplier = require_float(config, 'ATR_MULTIPLIER')
        self.volume_threshold = require_float(config, 'VOLUME_THRESHOLD')
        self.lookback_period = require_int(config, 'BREAKOUT_LOOKBACK')

        # Retest confirmation
        self.require_retest = require_bool(config, 'REQUIRE_RETEST')

        # Track breakout levels
        self.last_resistance = None
        self.last_support = None
        self.breakout_confirmed = False
        self.breakout_type = None  # 'bullish' or 'bearish'

        # Volume history (bounded to prevent unbounded growth)
        self.volume_history = deque(maxlen=500)

        # Fibonacci analysis settings (for profit targets)
        self.use_fibonacci = require_bool(config, 'USE_FIBONACCI')
        self.fib_lookback_period = require_int(config, 'FIB_LOOKBACK_PERIOD')

        # Profit target checking (prevents selling at a loss on noise)
        self.min_profit_target = require_float(config, 'MIN_PROFIT_TARGET')

        logger.info(f"Breakout Strategy initialized:")
        logger.info(f"  ATR Period: {self.atr_period}, Multiplier: {self.atr_multiplier}x")
        logger.info(f"  Volume Threshold: {self.volume_threshold}x average")
        logger.info(f"  Lookback: {self.lookback_period} periods")
        logger.info(f"  Require Retest: {self.require_retest}")
        logger.info(f"  Min Profit Target: {self.min_profit_target*100:.2f}%")
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

        # --- Stop-loss check (before any indicator computation) ---
        quick_price = self._peek_price(market_data)
        if quick_price is not None:
            stop = self.check_stop_loss(quick_price)
            if stop:
                self.breakout_confirmed = False
                return stop

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
            """Compare current ATR to average ATR over recent windows.

            Uses a single-pass rolling True Range sum instead of calling
            calculate_atr for every window, reducing O(lookback * period)
            to O(lookback + period).
            """
            min_len = self.atr_period + lookback + 1
            if len(prices) < self.atr_period + 2 or len(prices) < min_len:
                return False

            # Pre-compute TR series once for the range we need.
            start_idx = max(1, len(prices) - (lookback + self.atr_period))
            tr_series = []
            for i in range(start_idx, len(prices)):
                high_low = highs[i] - lows[i]
                high_close = abs(highs[i] - prices[i - 1])
                low_close = abs(lows[i] - prices[i - 1])
                tr_series.append(max(high_low, high_close, low_close))

            if len(tr_series) < self.atr_period:
                return False

            # Build ATR values using a rolling sum.
            rolling_tr = sum(tr_series[:self.atr_period])
            atr_vals = [rolling_tr / self.atr_period]
            for i in range(self.atr_period, len(tr_series)):
                rolling_tr += tr_series[i] - tr_series[i - self.atr_period]
                atr_vals.append(rolling_tr / self.atr_period)

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
                    self.entry_price = current_price
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
                # PROFIT TARGET CHECK: Don't sell at a loss unless stop-loss handles it
                if self.entry_price is not None and self.position == 'long':
                    profit_pct = (current_price - self.entry_price) / self.entry_price
                    if profit_pct < self.min_profit_target:
                        logger.debug(
                            f"⚠️ Bearish breakout SELL gated - profit too low: "
                            f"{profit_pct*100:.2f}% < {self.min_profit_target*100:.2f}%"
                        )
                        # Let stop-loss handle deep losses; skip small-loss sells
                        return None

                # FEE-AWARE BREAKEVEN CHECK: don't sell below round-trip fee cost
                if not self.is_above_breakeven(current_price):
                    logger.debug(
                        f"⚠️ Bearish breakout SELL gated - below fee-adjusted breakeven "
                        f"(round-trip fee ~{self._roundtrip_fee_pct*100:.2f}%)"
                    )
                    return None

                logger.info(f"🔻 BEARISH BREAKOUT DETECTED!")
                logger.info(f"  ✓ Price broke support ${self.last_support:,.2f}")
                logger.info(f"  ✓ Volume surge confirmed ({self.volume_threshold}x)")
                logger.info(f"  ✓ High volatility (ATR)")

                # Note: For bearish breakouts, consider inverse Fibonacci extensions
                if fib_extensions:
                    logger.info(f"  ⚠️  Consider exiting positions or setting stop losses")

                if not self.require_retest or self.breakout_confirmed:
                    self.entry_price = None
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
                    self.entry_price = current_price
                    return 'buy'

            elif self.breakout_type == 'bearish' and self.last_support:
                # Price should be near support (now resistance)
                if abs(current_price - self.last_support) / self.last_support < 0.02:
                    logger.info("✓ Retest confirmed! Price holding below old support")
                    self.breakout_confirmed = False
                    self.entry_price = None
                    return 'sell'

        # No breakout signal
        status = "Within range"
        if self.last_support and self.last_resistance and self.last_resistance != self.last_support:
            range_position = (current_price - self.last_support) / (self.last_resistance - self.last_support) * 100
            status = f"In range ({range_position:.0f}% from support to resistance)"

        logger.info(f"Status: {status} | Position: {self.position or 'None'}")
        return None

    def reset(self) -> None:
        """Reset strategy state."""
        super().reset()
        self.last_resistance = None
        self.last_support = None
        self.breakout_confirmed = False
        self.breakout_type = None
        self.volume_history.clear()
