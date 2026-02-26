"""Base strategy class for trading strategies."""
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from collections import deque

from ..config_utils import optional, require_int

logger = logging.getLogger(__name__)


class TradingStrategy(ABC):
    """Abstract base class for trading strategies."""

    def __init__(self, config: dict):
        """
        Initialize strategy with configuration.

        Args:
            config: Strategy configuration dictionary
        """
        self.config = config
        self.price_history: deque = deque(maxlen=require_int(config, 'HISTORY_SIZE'))
        self.position = None  # None, 'long', or 'short'
        self.last_signal = None
        self.market_state = None  # Current market state (e.g., 'strong_uptrend', 'strong_downtrend')

        # Stop-loss protection (shared across all strategies)
        # Reads STOP_LOSS_PERCENTAGE from config (e.g. 2.0 means 2%).
        # A value of 0 or missing disables the stop-loss.
        stop_loss_raw = optional(config, 'STOP_LOSS_PERCENTAGE')
        self.stop_loss_pct = float(stop_loss_raw) / 100.0 if stop_loss_raw is not None else 0.0

        # Entry price tracking for stop-loss / profit calculations.
        # Subclasses that already track entry_price will share this attribute.
        self.entry_price: Optional[float] = None

        # Fee-aware breakeven threshold.
        # Round-trip cost = 2 * taker_fee (buy + sell).
        taker_fee_raw = optional(config, 'TAKER_FEE')
        self._roundtrip_fee_pct = 2.0 * float(taker_fee_raw) if taker_fee_raw is not None else 0.0

    @abstractmethod
    def analyze(self, market_data: Dict[str, Any]) -> Optional[str]:
        """
        Analyze market data and return trading signal.

        Args:
            market_data: Dictionary containing ticker, order_book, etc.

        Returns:
            'buy', 'sell', or None
        """
        pass

    @abstractmethod
    def get_strategy_name(self) -> str:
        """Return the strategy name."""
        pass

    def add_price(self, price: float) -> None:
        """
        Add a price to the history.

        Args:
            price: Price to add
        """
        self.price_history.append(price)

    def get_prices(self) -> List[float]:
        """
        Get price history as a list.

        Returns:
            List of prices
        """
        return list(self.price_history)

    def has_sufficient_data(self, required_periods: int) -> bool:
        """
        Check if we have enough price data.

        Args:
            required_periods: Minimum number of periods required

        Returns:
            True if sufficient data available
        """
        return len(self.price_history) >= required_periods

    def _peek_price(self, market_data: Dict[str, Any]) -> Optional[float]:
        """
        Extract the current price from market_data without side effects.

        Used by check_stop_loss() at the top of analyze() to bail early
        before running expensive indicator calculations.

        Args:
            market_data: Market data dictionary

        Returns:
            Current price as float, or None if unavailable
        """
        # Try OHLC first
        ohlc = market_data.get('ohlc')
        if isinstance(ohlc, dict):
            if isinstance(ohlc.get('latest'), dict) and 'close' in ohlc['latest']:
                return float(ohlc['latest']['close'])
            closes = ohlc.get('closes')
            if closes:
                return float(closes[-1])

        # Fall back to ticker
        ticker_data = market_data.get('ticker', {})
        if ticker_data:
            pair_key = next(iter(ticker_data), None)
            if pair_key and isinstance(ticker_data[pair_key], dict):
                c = ticker_data[pair_key].get('c')
                if c:
                    return float(c[0])

        return None

    def update_position(self, position: Optional[str]) -> None:
        """
        Update current position.

        Args:
            position: 'long', 'short', or None
        """
        self.position = position

    def update_signal(self, signal: Optional[str]) -> None:
        """
        Update last signal.

        Args:
            signal: 'buy', 'sell', or None
        """
        self.last_signal = signal

    def update_market_state(self, market_state: Optional[str]) -> None:
        """
        Update current market state.

        Args:
            market_state: Market state string (e.g., 'strong_uptrend', 'range_bound')
        """
        self.market_state = market_state

    def set_entry_price(self, price: float) -> None:
        """
        Record the entry price for stop-loss / profit tracking.

        Args:
            price: Entry price
        """
        self.entry_price = price

    def clear_entry_price(self) -> None:
        """Clear entry price after exiting a position."""
        self.entry_price = None

    def check_stop_loss(self, current_price: float) -> Optional[str]:
        """
        Check if the stop-loss threshold has been breached.

        Should be called early in analyze() — if it returns 'sell',
        the strategy should exit immediately regardless of other signals.

        Args:
            current_price: Current market price

        Returns:
            'sell' if stop-loss triggered, None otherwise
        """
        if (
            self.stop_loss_pct > 0
            and self.entry_price is not None
            and self.position == 'long'
            and current_price > 0
        ):
            loss_pct = (self.entry_price - current_price) / self.entry_price
            if loss_pct >= self.stop_loss_pct:
                logger.warning(
                    f"🛑 STOP-LOSS TRIGGERED: "
                    f"Entry ${self.entry_price:,.2f} → Current ${current_price:,.2f} "
                    f"(loss: {loss_pct*100:.2f}% >= {self.stop_loss_pct*100:.1f}%)"
                )
                self.entry_price = None
                return 'sell'

        return None

    def is_above_breakeven(self, current_price: float) -> bool:
        """
        Check whether the current price exceeds the fee-adjusted breakeven.

        Strategies can call this before emitting a sell signal to ensure the
        trade is at least break-even after Kraken taker fees on both legs.

        Args:
            current_price: Current market price

        Returns:
            True if the gross profit exceeds round-trip fees (or if no entry
            price is tracked), False otherwise.
        """
        if self.entry_price is None or self.entry_price <= 0 or current_price <= 0:
            return True  # No position tracked; allow signal through

        gross_pct = (current_price - self.entry_price) / self.entry_price
        return gross_pct >= self._roundtrip_fee_pct

    def reset(self) -> None:
        """Reset strategy state."""
        self.price_history.clear()
        self.position = None
        self.last_signal = None
        self.market_state = None
        self.entry_price = None

    def _find_pair_key(self, ticker_data: dict) -> Optional[str]:
        """
        Find the actual trading pair key in ticker response.

        Prefers the subclass ``symbol`` attribute (if set), then falls back
        to the first key in the ticker dict.

        Args:
            ticker_data: Ticker data dictionary

        Returns:
            Pair key or None
        """
        symbol = getattr(self, 'symbol', None)
        if symbol and symbol in ticker_data:
            return symbol

        if isinstance(ticker_data, dict) and ticker_data:
            return next(iter(ticker_data))

        return None
