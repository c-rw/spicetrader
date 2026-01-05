"""Base strategy class for trading strategies."""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from collections import deque

from ..config_utils import require_int


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

    def reset(self) -> None:
        """Reset strategy state."""
        self.price_history.clear()
        self.position = None
        self.last_signal = None
        self.market_state = None
