"""Strategy selector based on market conditions."""
import logging
from typing import Dict, Any

from ..strategies import (
    TradingStrategy,
    MeanReversionStrategy,
    SMACrossoverStrategy,
    BreakoutStrategy,
    MACDStrategy,
    GridTradingStrategy
)
from .market_condition import MarketCondition, MarketState

logger = logging.getLogger(__name__)


class StrategySelector:
    """
    Selects the optimal trading strategy based on market conditions.

    This class maps market states to appropriate trading strategies,
    ensuring the bot uses the right approach for current conditions.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize strategy selector.

        Args:
            config: Configuration dictionary for strategies
        """
        self.config = config

        logger.info("StrategySelector initialized")

    def select_strategy(self, market_condition: MarketCondition, symbol: str = None) -> TradingStrategy:
        """
        Select best strategy for given market condition.

        Args:
            market_condition: Current market condition
            symbol: Trading pair symbol (e.g., 'XBTUSD')

        Returns:
            Trading strategy instance
        """
        # Get recommended strategy name from market condition
        strategy_name = market_condition.get_recommended_strategy()

        logger.info(f"Market state: {market_condition.state.value}")
        logger.info(f"Recommended strategy: {strategy_name}")
        logger.info(f"Confidence: {market_condition.confidence*100:.0f}%")

        # Create strategy instance for this coin
        strategy = self._get_strategy_instance(strategy_name, market_condition, symbol)

        return strategy

    def _get_strategy_instance(
        self,
        strategy_name: str,
        market_condition: MarketCondition,
        symbol: str = None
    ) -> TradingStrategy:
        """
        Create strategy instance for a specific coin.

        Args:
            strategy_name: Name of strategy to create
            market_condition: Current market condition
            symbol: Trading pair symbol (e.g., 'XBTUSD')

        Returns:
            Strategy instance
        """
        # Always create new instance per coin (no caching)
        logger.info(f"Creating new {strategy_name} strategy for {symbol or 'default'}")

        if strategy_name == 'mean_reversion':
            strategy = MeanReversionStrategy(self.config, symbol=symbol)

        elif strategy_name == 'sma_crossover':
            strategy = SMACrossoverStrategy(self.config)

        elif strategy_name == 'breakout':
            strategy = BreakoutStrategy(self.config)

        elif strategy_name == 'macd':
            strategy = MACDStrategy(self.config)

        elif strategy_name == 'grid':
            strategy = GridTradingStrategy(self.config)

        else:
            logger.warning(f"Unknown strategy '{strategy_name}', defaulting to mean_reversion")
            strategy = MeanReversionStrategy(self.config, symbol=symbol)

        return strategy

    def get_strategy_for_state(self, state: MarketState) -> str:
        """
        Get strategy name for a given market state.

        Args:
            state: Market state

        Returns:
            Strategy name
        """
        # This mapping defines which strategy to use for each market state
        strategy_map = {
            MarketState.STRONG_UPTREND: 'sma_crossover',      # Fast trend following
            MarketState.STRONG_DOWNTREND: 'sma_crossover',    # Fast trend following
            MarketState.MODERATE_TREND: 'macd',               # MACD for medium trends
            MarketState.RANGE_BOUND: 'mean_reversion',        # Mean reversion in ranges
            MarketState.VOLATILE_BREAKOUT: 'breakout',        # Breakout strategy
            MarketState.CHOPPY: 'mean_reversion',             # Conservative in chop
            MarketState.LOW_VOLATILITY: 'grid',               # Grid for tight ranges
            MarketState.UNKNOWN: 'mean_reversion'             # Conservative default
        }

        return strategy_map.get(state, 'mean_reversion')
