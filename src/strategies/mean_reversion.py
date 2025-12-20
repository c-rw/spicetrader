"""Mean Reversion Range Trading Strategy."""
import logging
from typing import Optional, Dict, Any
from .base import TradingStrategy
from ..indicators import (
    calculate_rsi,
    calculate_bollinger_bands,
    detect_support_resistance,
    find_swing_high_low,
    calculate_fibonacci_retracement,
    get_fibonacci_signal_strength
)

logger = logging.getLogger(__name__)


class MeanReversionStrategy(TradingStrategy):
    """
    Mean Reversion Range Trading Strategy.

    This strategy is designed for range-bound markets where price oscillates
    between support and resistance levels.

    Strategy Logic:
    - BUY: Price near support + RSI oversold + Below lower Bollinger Band
    - SELL: Price near resistance + RSI overbought + Above upper Bollinger Band
    - STOP: Price breaks out of range (potential trend change)
    """

    def __init__(self, config: dict, symbol: str = None):
        """
        Initialize Mean Reversion strategy.

        Args:
            config: Strategy configuration
            symbol: Trading pair symbol (e.g., 'XBTUSD', 'ETHUSD') for per-coin config
        """
        super().__init__(config)

        self.symbol = symbol

        # Symbol-specific config prefix (e.g., 'XBTUSD_SUPPORT_LEVEL')
        prefix = f'{symbol}_' if symbol else ''

        # RSI parameters
        self.rsi_period = int(config.get('RSI_PERIOD', 14))
        self.rsi_oversold = float(config.get('RSI_OVERSOLD', 40))
        self.rsi_overbought = float(config.get('RSI_OVERBOUGHT', 60))

        # Bollinger Bands parameters
        self.bb_period = int(config.get('BB_PERIOD', 20))
        self.bb_std_dev = float(config.get('BB_STD_DEV', 2.0))

        # Range parameters - USE PER-COIN CONFIG
        # Default values based on symbol if not configured
        default_support, default_resistance, default_lower, default_upper = self._get_default_levels(symbol)

        self.support_level = float(config.get(f'{prefix}SUPPORT_LEVEL', default_support))
        self.resistance_level = float(config.get(f'{prefix}RESISTANCE_LEVEL', default_resistance))
        self.support_zone = float(config.get(f'{prefix}SUPPORT_ZONE',
                                             config.get('SUPPORT_ZONE', self.support_level * 0.03)))  # 3% default
        self.resistance_zone = float(config.get(f'{prefix}RESISTANCE_ZONE',
                                                config.get('RESISTANCE_ZONE', self.resistance_level * 0.03)))

        # Breakout detection - USE PER-COIN CONFIG
        self.breakout_lower = float(config.get(f'{prefix}BREAKOUT_LOWER', default_lower))
        self.breakout_upper = float(config.get(f'{prefix}BREAKOUT_UPPER', default_upper))

        # Dynamic support/resistance detection
        self.auto_detect_levels = config.get('AUTO_DETECT_LEVELS', 'true').lower() == 'true'

        # Fibonacci analysis settings
        self.use_fibonacci = config.get('USE_FIBONACCI', 'true').lower() == 'true'
        self.fib_lookback_period = int(config.get('FIB_LOOKBACK_PERIOD', 50))
        self.fib_tolerance = float(config.get('FIB_TOLERANCE', 1.0))

        # Profit target settings (CRITICAL FIX)
        self.min_profit_target = float(config.get(f'{prefix}MIN_PROFIT_TARGET',
                                                  config.get('MIN_PROFIT_TARGET', 0.006)))  # 0.6% default
        self.entry_price = None  # Track entry price for profit calculation

        logger.info(f"Mean Reversion Strategy initialized for {symbol or 'default'}:")
        logger.info(f"  RSI: {self.rsi_period} period, oversold < {self.rsi_oversold}, overbought > {self.rsi_overbought}")
        logger.info(f"  Bollinger Bands: {self.bb_period} period, {self.bb_std_dev} std dev")
        logger.info(f"  Support: ${self.support_level:,.2f} ± ${self.support_zone:,.2f}")
        logger.info(f"  Resistance: ${self.resistance_level:,.2f} ± ${self.resistance_zone:,.2f}")
        logger.info(f"  Breakout levels: ${self.breakout_lower:,.2f} - ${self.breakout_upper:,.2f}")
        logger.info(f"  Min Profit Target: {self.min_profit_target*100:.2f}%")
        logger.info(f"  Fibonacci: {'Enabled' if self.use_fibonacci else 'Disabled'} (lookback: {self.fib_lookback_period}, tolerance: {self.fib_tolerance}%)")

    def _get_default_levels(self, symbol: str) -> tuple:
        """
        Get sensible default support/resistance levels based on symbol.

        Returns:
            (support, resistance, breakout_lower, breakout_upper)
        """
        if not symbol:
            return (94000, 102000, 93000, 106000)

        # Coin-specific defaults based on typical price ranges
        defaults = {
            'XBTUSD': (94000, 102000, 93000, 106000),
            'ETHUSD': (3000, 3300, 2900, 3400),
            'SOLUSD': (130, 150, 120, 160),
            'XRPUSD': (2.15, 2.35, 2.05, 2.45),
        }

        return defaults.get(symbol, (94000, 102000, 93000, 106000))

    def get_strategy_name(self) -> str:
        """Return strategy name."""
        return "Mean Reversion Range Trading"

    def analyze(self, market_data: Dict[str, Any]) -> Optional[str]:
        """
        Analyze market data for mean reversion signals.

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

            required_periods = max(self.rsi_period, self.bb_period)
            if len(prices) < required_periods + 1:
                logger.info(f"Collecting data... ({len(prices)}/{required_periods + 1})")
                return None
        else:
            # Extract current price from ticker
            ticker_data = market_data.get('ticker', {})

            pair_key = self._find_pair_key(ticker_data)
            if not pair_key:
                logger.error("Trading pair not found in ticker data")
                return None

            current_price = float(ticker_data[pair_key]['c'][0])
            self.add_price(current_price)

            required_periods = max(self.rsi_period, self.bb_period)
            if not self.has_sufficient_data(required_periods + 1):
                logger.info(f"Collecting data... ({len(self.price_history)}/{required_periods + 1})")
                return None

            prices = self.get_prices()

        # Calculate indicators
        rsi = calculate_rsi(prices, self.rsi_period)
        bb = calculate_bollinger_bands(prices, self.bb_period, self.bb_std_dev)

        if rsi is None or bb is None:
            logger.warning("Unable to calculate indicators")
            return None

        upper_bb, middle_bb, lower_bb = bb

        # Update support/resistance if auto-detection enabled
        if self.auto_detect_levels and len(prices) >= 50:
            self._update_support_resistance(prices)

        # Calculate Fibonacci levels if enabled
        fib_strength = 1.0  # Default: no Fibonacci bonus
        fib_levels = None
        if self.use_fibonacci and len(prices) >= self.fib_lookback_period:
            swing_points = find_swing_high_low(prices, self.fib_lookback_period)
            if swing_points:
                swing_high, swing_low = swing_points
                fib_levels = calculate_fibonacci_retracement(swing_high, swing_low)
                fib_strength = get_fibonacci_signal_strength(
                    current_price,
                    fib_levels,
                    key_levels=['38.2%', '50.0%', '61.8%'],
                    tolerance_percent=self.fib_tolerance
                )

                # Log Fibonacci analysis
                if fib_strength > 1.0:
                    logger.info(f"📐 Fibonacci: Near key level (strength: {fib_strength:.2f}x)")
                    logger.info(f"   Swing: ${swing_low:,.2f} - ${swing_high:,.2f}")
                    logger.info(f"   61.8%: ${fib_levels['61.8%']:,.2f} | 50.0%: ${fib_levels['50.0%']:,.2f} | 38.2%: ${fib_levels['38.2%']:,.2f}")

        # Check for range breakout (exit condition)
        if current_price < self.breakout_lower:
            logger.warning(f"⚠️ BREAKOUT BELOW ${self.breakout_lower:,.0f}! Price: ${current_price:,.2f}")
            logger.warning("Range broken - consider switching to trend-following strategy")
            return None

        if current_price > self.breakout_upper:
            logger.warning(f"⚠️ BREAKOUT ABOVE ${self.breakout_upper:,.0f}! Price: ${current_price:,.2f}")
            logger.warning("Range broken - consider switching to trend-following strategy")
            return None

        # Determine position in range
        in_support_zone = (self.support_level - self.support_zone <= current_price <=
                          self.support_level + self.support_zone)
        in_resistance_zone = (self.resistance_level - self.resistance_zone <= current_price <=
                             self.resistance_level + self.resistance_zone)

        # Log current state
        logger.info(f"Price: ${current_price:,.2f} | RSI: {rsi:.1f} | BB: ${lower_bb:,.2f} - ${middle_bb:,.2f} - ${upper_bb:,.2f}")

        # BUY Signal: Near support, oversold, below lower BB
        # Fibonacci enhancement: Relax RSI requirement if near key Fib level
        rsi_buy_threshold = self.rsi_oversold
        if fib_strength > 1.15:  # Near 61.8% or exact level
            rsi_buy_threshold += 5  # Allow RSI up to 45 instead of 40

        if in_support_zone and rsi < rsi_buy_threshold and current_price < lower_bb and self.position != 'long':
            signal_confidence = "HIGH" if fib_strength > 1.15 else "MEDIUM"
            logger.info(f"🟢 BUY SIGNAL [{signal_confidence} CONFIDENCE]:")
            logger.info(f"  ✓ Near support (${self.support_level:,.0f} ± ${self.support_zone:,.0f})")
            logger.info(f"  ✓ RSI oversold ({rsi:.1f} < {rsi_buy_threshold})")
            logger.info(f"  ✓ Below lower BB (${current_price:,.2f} < ${lower_bb:,.2f})")
            if fib_strength > 1.0:
                logger.info(f"  ✓ Fibonacci confirmation ({fib_strength:.2f}x strength)")

            # Track entry price for profit target calculation
            self.entry_price = current_price
            return 'buy'

        # PROFIT-BASED EXIT: Allow selling when profit target met (regardless of resistance zone)
        # This prevents being stuck in profitable positions waiting for resistance
        if self.position == 'long' and self.entry_price is not None:
            profit_pct = (current_price - self.entry_price) / self.entry_price

            # Exit if 2%+ profit with basic confirmation
            if profit_pct >= 0.02:  # 2% profit target
                # Require basic confirmation: neutral/positive RSI and price above middle BB
                if rsi > 50 and current_price > middle_bb:
                    logger.info(f"🔴 PROFIT TARGET EXIT:")
                    logger.info(f"  ✓ Profit: {profit_pct*100:.2f}% >= 2.0%")
                    logger.info(f"  ✓ RSI neutral/bullish: {rsi:.1f} > 50")
                    logger.info(f"  ✓ Price above middle BB: ${current_price:,.2f} > ${middle_bb:,.2f}")
                    self.entry_price = None
                    return 'sell'

        # SELL Signal: Near resistance, overbought, above upper BB
        # Fibonacci enhancement: Relax RSI requirement if near key Fib level
        rsi_sell_threshold = self.rsi_overbought
        if fib_strength > 1.15:  # Near 61.8% or exact level
            rsi_sell_threshold -= 5  # Allow RSI down to 55 instead of 60

        if in_resistance_zone and rsi > rsi_sell_threshold and current_price > upper_bb and self.position == 'long':
            # Check profit target before selling
            if self.entry_price is not None:
                profit_pct = (current_price - self.entry_price) / self.entry_price

                if profit_pct < self.min_profit_target:
                    logger.debug(f"⚠️ SELL conditions met but profit too low:")
                    logger.debug(f"  Current profit: {profit_pct*100:.2f}% < Target: {self.min_profit_target*100:.2f}%")
                    logger.debug(f"  Entry: ${self.entry_price:,.2f} → Current: ${current_price:,.2f}")
                    return None  # Don't sell yet

            signal_confidence = "HIGH" if fib_strength > 1.15 else "MEDIUM"
            logger.info(f"🔴 SELL SIGNAL [{signal_confidence} CONFIDENCE]:")
            logger.info(f"  ✓ Near resistance (${self.resistance_level:,.0f} ± ${self.resistance_zone:,.0f})")
            logger.info(f"  ✓ RSI overbought ({rsi:.1f} > {rsi_sell_threshold})")
            logger.info(f"  ✓ Above upper BB (${current_price:,.2f} > ${upper_bb:,.2f})")
            if fib_strength > 1.0:
                logger.info(f"  ✓ Fibonacci confirmation ({fib_strength:.2f}x strength)")

            # Log profit if we have entry price
            if self.entry_price is not None:
                profit_pct = (current_price - self.entry_price) / self.entry_price
                logger.info(f"  ✓ Profit target met: {profit_pct*100:.2f}% (target: {self.min_profit_target*100:.2f}%)")

            # Reset entry price after selling
            self.entry_price = None
            return 'sell'

        # Log current market state
        zone = "SUPPORT ZONE" if in_support_zone else "RESISTANCE ZONE" if in_resistance_zone else "MID-RANGE"
        rsi_state = "Oversold" if rsi < self.rsi_oversold else "Overbought" if rsi > self.rsi_overbought else "Neutral"
        bb_state = "Below" if current_price < lower_bb else "Above" if current_price > upper_bb else "Within"

        logger.info(f"Status: {zone} | RSI: {rsi_state} | BB: {bb_state} | Position: {self.position or 'None'}")

        return None

    def _find_pair_key(self, ticker_data: dict) -> Optional[str]:
        """
        Find the actual trading pair key in ticker response.

        Args:
            ticker_data: Ticker data dictionary

        Returns:
            Pair key or None
        """
        # Common pair variations
        variations = ['XBTUSD', 'XXBTZUSD', 'BTCUSD', 'ETHUSD', 'XETHZUSD', 'SOLUSD', 'XRPUSD', 'XXRPZUSD']

        for variation in variations:
            if variation in ticker_data:
                return variation

        # Return first key if none match
        if ticker_data:
            return list(ticker_data.keys())[0]

        return None

    def _update_support_resistance(self, prices: list) -> None:
        """
        Dynamically update support and resistance levels.

        Args:
            prices: Price history
        """
        support_levels, resistance_levels = detect_support_resistance(prices, window=10, threshold=0.02)

        if support_levels:
            # Use the highest support level (closest to current price)
            new_support = max(support_levels)
            if abs(new_support - self.support_level) > 1000:  # Significant change
                logger.info(f"📊 Support level updated: ${self.support_level:,.0f} → ${new_support:,.0f}")
                self.support_level = new_support

        if resistance_levels:
            # Use the lowest resistance level (closest to current price)
            new_resistance = min(resistance_levels)
            if abs(new_resistance - self.resistance_level) > 1000:  # Significant change
                logger.info(f"📊 Resistance level updated: ${self.resistance_level:,.0f} → ${new_resistance:,.0f}")
                self.resistance_level = new_resistance
