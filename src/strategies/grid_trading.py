"""Grid Trading Strategy for tight ranging markets."""
import logging
from typing import Optional, Dict, Any, List
from .base import TradingStrategy
from ..config_utils import optional, require_float, require_int

logger = logging.getLogger(__name__)


class GridTradingStrategy(TradingStrategy):
    """
    Grid Trading Strategy for tight ranging markets.

    This strategy places buy and sell orders at fixed price intervals
    in a ranging market, profiting from small price oscillations.

    Strategy Logic:
    - Define price grid with intervals (e.g., every $500)
    - Place buy orders below current price
    - Place sell orders above current price
    - Take profit on small movements
    - Works best in low volatility, tight ranges
    """

    def __init__(self, config: dict):
        """
        Initialize Grid Trading strategy.

        Args:
            config: Strategy configuration
        """
        super().__init__(config)

        # Grid parameters
        self.grid_size = require_int(config, 'GRID_SIZE')
        self.grid_spacing_pct = require_float(config, 'GRID_SPACING_PCT')
        self.grid_center = None  # Will be set based on current price

        # How close price must be to a grid level to trigger (default 0.3%)
        trigger_raw = optional(config, 'GRID_TRIGGER_PCT')
        self.grid_trigger_pct = float(trigger_raw) / 100.0 if trigger_raw is not None else 0.003

        # Track grid levels and orders
        self.buy_levels = []
        self.sell_levels = []
        self.filled_buys = set()
        self.filled_sells = set()

        # Grid bounds
        self.upper_bound = None
        self.lower_bound = None

        logger.info(f"Grid Trading Strategy initialized:")
        logger.info(f"  Grid Size: {self.grid_size} levels")
        logger.info(f"  Spacing: {self.grid_spacing_pct}% per level")
        logger.info(f"  Trigger Proximity: {self.grid_trigger_pct*100:.1f}%")

    def get_strategy_name(self) -> str:
        """Return strategy name."""
        return f"Grid Trading ({self.grid_size} levels)"

    def analyze(self, market_data: Dict[str, Any]) -> Optional[str]:
        """
        Analyze market data for grid trading signals.

        Args:
            market_data: Market data dictionary

        Returns:
            'buy', 'sell', or None
        """
        # Prefer OHLC close price for consistency with other strategies.
        ohlc = market_data.get('ohlc')
        if isinstance(ohlc, dict) and isinstance(ohlc.get('latest'), dict) and 'close' in ohlc['latest']:
            current_price = float(ohlc['latest']['close'])
        else:
            # Fallback: extract current price from ticker
            ticker_data = market_data.get('ticker', {})
            pair_key = self._find_pair_key(ticker_data)

            if not pair_key:
                logger.error("Trading pair not found in ticker data")
                return None

            current_price = float(ticker_data[pair_key]['c'][0])

        self.add_price(current_price)

        # --- Stop-loss check (before grid logic) ---
        stop = self.check_stop_loss(current_price)
        if stop:
            return stop

        # Need some data to establish grid center
        if not self.has_sufficient_data(10):
            logger.debug(f"Collecting data... ({len(self.price_history)}/{10})")
            return None

        # Initialize grid if not set
        if self.grid_center is None:
            self._initialize_grid(current_price)
            logger.info(f"Grid initialized at ${self.grid_center:,.2f}")
            logger.info(f"Range: ${self.lower_bound:,.2f} - ${self.upper_bound:,.2f}")
            return None

        # Check if price is out of grid bounds
        if current_price > self.upper_bound or current_price < self.lower_bound:
            logger.warning(f"Price ${current_price:,.2f} outside grid bounds!")
            logger.warning(f"Grid: ${self.lower_bound:,.2f} - ${self.upper_bound:,.2f}")
            logger.warning("Consider re-centering grid or switching strategy")
            # Re-center grid
            self._initialize_grid(current_price)
            logger.info("Grid re-centered")
            return None

        # Find nearest grid levels
        nearest_buy_level = self._find_nearest_level(current_price, self.buy_levels, below=True)
        nearest_sell_level = self._find_nearest_level(current_price, self.sell_levels, below=False)

        # Log current position in grid
        logger.info(f"Price: ${current_price:,.2f}")
        if nearest_buy_level:
            logger.info(f"Nearest Buy Level: ${nearest_buy_level:,.2f} ({(current_price/nearest_buy_level-1)*100:+.2f}%)")
        if nearest_sell_level:
            logger.info(f"Nearest Sell Level: ${nearest_sell_level:,.2f} ({(nearest_sell_level/current_price-1)*100:+.2f}%)")

        # Grid trading signals

        # BUY SIGNAL: Price near a buy level that hasn't been filled
        if nearest_buy_level and nearest_buy_level not in self.filled_buys:
            # Check if price is close enough to level
            if abs(current_price - nearest_buy_level) / nearest_buy_level < self.grid_trigger_pct:
                logger.info(f"🟢 BUY signal at grid level ${nearest_buy_level:,.2f}")
                self.filled_buys.add(nearest_buy_level)
                self.entry_price = current_price
                return 'buy'

        # SELL SIGNAL: Price near a sell level that hasn't been filled
        if nearest_sell_level and nearest_sell_level not in self.filled_sells:
            # Check if price is close enough to level
            if abs(current_price - nearest_sell_level) / nearest_sell_level < self.grid_trigger_pct:
                logger.info(f"🔴 SELL signal at grid level ${nearest_sell_level:,.2f}")
                self.filled_sells.add(nearest_sell_level)
                self.entry_price = None
                return 'sell'

        # Show grid status
        filled_buys = len(self.filled_buys)
        filled_sells = len(self.filled_sells)
        logger.info(f"Grid Status: {filled_buys} buys filled, {filled_sells} sells filled | Position: {self.position or 'None'}")

        return None

    def _initialize_grid(self, center_price: float):
        """
        Initialize the price grid.

        Args:
            center_price: Center price for the grid
        """
        self.grid_center = center_price
        self.buy_levels = []
        self.sell_levels = []
        self.filled_buys = set()
        self.filled_sells = set()

        # Calculate grid levels
        half_grid = self.grid_size // 2
        if half_grid < 1:
            logger.warning(f"Grid size {self.grid_size} too small for grid levels, using minimum of 2 levels")
            half_grid = 1

        # Buy levels (below center)
        for i in range(1, half_grid + 1):
            level = center_price * (1 - (self.grid_spacing_pct / 100) * i)
            self.buy_levels.append(level)

        # Sell levels (above center)
        for i in range(1, half_grid + 1):
            level = center_price * (1 + (self.grid_spacing_pct / 100) * i)
            self.sell_levels.append(level)

        # Set bounds
        self.lower_bound = min(self.buy_levels)
        self.upper_bound = max(self.sell_levels)

        logger.info(f"Buy Levels ({len(self.buy_levels)}): ${min(self.buy_levels):,.2f} - ${max(self.buy_levels):,.2f}")
        logger.info(f"Sell Levels ({len(self.sell_levels)}): ${min(self.sell_levels):,.2f} - ${max(self.sell_levels):,.2f}")

    def _find_nearest_level(self, price: float, levels: List[float], below: bool) -> Optional[float]:
        """
        Find nearest grid level to current price.

        Args:
            price: Current price
            levels: List of grid levels
            below: If True, find nearest level below price; if False, find nearest above

        Returns:
            Nearest level or None
        """
        if not levels:
            return None

        if below:
            # Find highest level below price
            candidates = [l for l in levels if l < price]
            return max(candidates) if candidates else None
        else:
            # Find lowest level above price
            candidates = [l for l in levels if l > price]
            return min(candidates) if candidates else None

    def reset(self) -> None:
        """Reset strategy state."""
        super().reset()
        self.grid_center = None
        self.buy_levels = []
        self.sell_levels = []
        self.filled_buys = set()
        self.filled_sells = set()
        self.upper_bound = None
        self.lower_bound = None
