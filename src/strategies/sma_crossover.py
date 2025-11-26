"""SMA Crossover Strategy."""
import logging
import time
from typing import Optional, Dict, Any
from .base import TradingStrategy
from indicators import calculate_sma

logger = logging.getLogger(__name__)


class SMACrossoverStrategy(TradingStrategy):
    """
    Simple Moving Average Crossover Strategy.

    This strategy uses two SMAs (fast and slow) to identify trend changes.

    Strategy Logic:
    - BUY: Fast SMA crosses above Slow SMA (bullish crossover)
    - SELL: Fast SMA crosses below Slow SMA (bearish crossover)

    Safety Features:
    - Profit target checking: Only exit if profit >= MIN_PROFIT_TARGET
    - Trend alignment: Only trade WITH the detected market trend
    - Minimum hold time: Prevent whipsaw trades under MIN_HOLD_TIME
    """

    def __init__(self, config: dict):
        """
        Initialize SMA Crossover strategy.

        Args:
            config: Strategy configuration
        """
        super().__init__(config)

        self.fast_period = int(config.get('FAST_SMA_PERIOD', 50))
        self.slow_period = int(config.get('SLOW_SMA_PERIOD', 200))

        # For crossover detection
        self.prev_fast_sma = None
        self.prev_slow_sma = None

        # Profit target checking
        self.min_profit_target = float(config.get('MIN_PROFIT_TARGET', 0.006))  # 0.6% default
        self.entry_price = None
        self.entry_time = None

        # Minimum hold time (seconds) to prevent whipsaws
        self.min_hold_time = int(config.get('MIN_HOLD_TIME', 300))  # 5 minutes default

        # Trend alignment filter
        self.enable_trend_filter = config.get('ENABLE_TREND_FILTER', 'true').lower() == 'true'

        logger.info(f"SMA Crossover Strategy initialized:")
        logger.info(f"  SMAs: Fast={self.fast_period}, Slow={self.slow_period}")
        logger.info(f"  Min Profit Target: {self.min_profit_target*100:.2f}%")
        logger.info(f"  Min Hold Time: {self.min_hold_time}s ({self.min_hold_time/60:.1f} min)")
        logger.info(f"  Trend Filter: {'Enabled' if self.enable_trend_filter else 'Disabled'}")

    def get_strategy_name(self) -> str:
        """Return strategy name."""
        return f"SMA Crossover (Fast: {self.fast_period}, Slow: {self.slow_period})"

    def analyze(self, market_data: Dict[str, Any]) -> Optional[str]:
        """
        Analyze market data for SMA crossover signals.

        Args:
            market_data: Market data dictionary

        Returns:
            'buy', 'sell', or None
        """
        # Extract current price from ticker
        ticker_data = market_data.get('ticker', {})

        # Find the actual pair key
        pair_key = self._find_pair_key(ticker_data)
        if not pair_key:
            logger.error("Trading pair not found in ticker data")
            return None

        # Get current price
        current_price = float(ticker_data[pair_key]['c'][0])
        self.add_price(current_price)

        # Need enough data for slow SMA
        if not self.has_sufficient_data(self.slow_period):
            logger.info(f"Collecting data... ({len(self.price_history)}/{self.slow_period})")
            return None

        # Get price history
        prices = self.get_prices()

        # Calculate current SMAs
        fast_sma = calculate_sma(prices, self.fast_period)
        slow_sma = calculate_sma(prices, self.slow_period)

        if fast_sma is None or slow_sma is None:
            logger.warning("Unable to calculate SMAs")
            return None

        # Log current state
        logger.info(f"Price: ${current_price:.2f} | Fast SMA: ${fast_sma:.2f} | Slow SMA: ${slow_sma:.2f}")

        # Detect crossover
        signal = None
        if self.prev_fast_sma is not None and self.prev_slow_sma is not None:
            # Bullish crossover: fast crosses above slow
            if self.prev_fast_sma <= self.prev_slow_sma and fast_sma > slow_sma:
                logger.info("🟢 BULLISH CROSSOVER DETECTED!")

                # TREND ALIGNMENT CHECK - Don't buy in downtrends
                if self.enable_trend_filter and self.market_state:
                    if 'downtrend' in self.market_state.lower():
                        logger.info(f"⚠️ BUY signal ignored - market in {self.market_state}")
                        logger.info("  Trend filter: Won't go LONG during downtrend")
                        signal = None
                    else:
                        signal = 'buy'
                else:
                    signal = 'buy'

            # Bearish crossover: fast crosses below slow
            elif self.prev_fast_sma >= self.prev_slow_sma and fast_sma < slow_sma:
                logger.info("🔴 BEARISH CROSSOVER DETECTED!")

                # Initialize potential signal
                signal = 'sell'

                # TREND ALIGNMENT CHECK - In strong uptrends, be cautious about selling
                # Only sell if we have a position (spot trading - can't short)
                if self.enable_trend_filter and self.market_state:
                    if 'uptrend' in self.market_state.lower() and self.position != 'long':
                        logger.info(f"⚠️ SELL signal ignored - market in {self.market_state} with no long position")
                        logger.info("  Trend filter: Won't sell/short during uptrend without existing position")
                        signal = None

                # PROFIT TARGET CHECK before selling (if still considering sell)
                if signal == 'sell' and self.entry_price is not None:
                    profit_pct = (current_price - self.entry_price) / self.entry_price

                    if profit_pct < self.min_profit_target:
                        logger.debug(f"⚠️ SELL signal ignored - profit too low:")
                        logger.debug(f"  Current profit: {profit_pct*100:.2f}% < Target: {self.min_profit_target*100:.2f}%")
                        logger.debug(f"  Entry: ${self.entry_price:,.2f} → Current: ${current_price:,.2f}")
                        signal = None  # Don't sell yet
                    else:
                        logger.info(f"✅ Profit target met: {profit_pct*100:.2f}% >= {self.min_profit_target*100:.2f}%")

                # MINIMUM HOLD TIME CHECK
                if signal == 'sell' and self.entry_time is not None:
                    hold_time = time.time() - self.entry_time
                    if hold_time < self.min_hold_time:
                        logger.info(f"⚠️ SELL signal ignored - hold time too short:")
                        logger.info(f"  Held for: {hold_time:.0f}s ({hold_time/60:.1f}min) < Min: {self.min_hold_time}s ({self.min_hold_time/60:.1f}min)")
                        signal = None  # Don't sell yet

        # Track entry price and time when buying
        if signal == 'buy':
            self.entry_price = current_price
            self.entry_time = time.time()
            logger.info(f"📊 Entry tracked: ${self.entry_price:,.2f} at {time.strftime('%H:%M:%S', time.localtime(self.entry_time))}")

        # Reset entry tracking when selling
        if signal == 'sell':
            self.entry_price = None
            self.entry_time = None

        # Update previous SMAs
        self.prev_fast_sma = fast_sma
        self.prev_slow_sma = slow_sma

        # Log trend if no signal
        if signal is None:
            trend = "BULLISH" if fast_sma > slow_sma else "BEARISH"
            position_info = f"Position: {self.position or 'None'}"
            if self.entry_price is not None:
                profit_pct = (current_price - self.entry_price) / self.entry_price
                hold_time = time.time() - self.entry_time if self.entry_time else 0
                position_info += f" | P&L: {profit_pct*100:+.2f}% | Hold: {hold_time/60:.1f}min"
            logger.info(f"Trend: {trend} (Fast {'>' if fast_sma > slow_sma else '<'} Slow) | {position_info}")

        return signal

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

    def reset(self) -> None:
        """Reset strategy state."""
        super().reset()
        self.prev_fast_sma = None
        self.prev_slow_sma = None
        self.entry_price = None
        self.entry_time = None
