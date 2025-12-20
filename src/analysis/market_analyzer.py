"""Market analyzer for detecting market conditions."""
import logging
import time
from typing import List, Dict, Any, Optional, Tuple

from ..indicators import (
    calculate_adx,
    calculate_atr,
    calculate_choppiness_index,
    calculate_linear_regression_slope,
    calculate_range_percent
)
from .market_condition import MarketCondition, MarketState

logger = logging.getLogger(__name__)


class MarketAnalyzer:
    """
    Analyzes market data to determine current market state.

    This class examines price action using multiple technical indicators
    to classify the market into one of several states (trending, ranging, etc.)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize market analyzer.

        Args:
            config: Configuration dictionary
        """
        self.config = config or {}

        # Thresholds for market state detection
        self.adx_strong_trend = float(self.config.get('ADX_STRONG_TREND', 25))
        self.adx_weak_trend = float(self.config.get('ADX_WEAK_TREND', 20))
        self.choppiness_choppy = float(self.config.get('CHOPPINESS_CHOPPY', 61.8))
        self.choppiness_trending = float(self.config.get('CHOPPINESS_TRENDING', 38.2))
        self.range_tight = float(self.config.get('RANGE_TIGHT', 5))
        self.range_moderate = float(self.config.get('RANGE_MODERATE', 15))

        # Indicator periods
        self.adx_period = int(self.config.get('ADX_PERIOD', 14))
        self.atr_period = int(self.config.get('ATR_PERIOD', 14))
        self.chop_period = int(self.config.get('CHOP_PERIOD', 14))
        self.slope_period = int(self.config.get('SLOPE_PERIOD', 14))
        self.range_period = int(self.config.get('RANGE_PERIOD', 50))

        # Caching for analysis results (per-symbol)
        self._analysis_cache: Dict[str, Tuple[MarketCondition, float]] = {}  # symbol -> (condition, timestamp)
        self.cache_ttl = int(self.config.get('ANALYSIS_CACHE_TTL', 30))  # Cache for 30 seconds

        logger.info("MarketAnalyzer initialized with thresholds:")
        logger.info(f"  ADX: Strong>{self.adx_strong_trend}, Weak<{self.adx_weak_trend}")
        logger.info(f"  Choppiness: Choppy>{self.choppiness_choppy}, Trending<{self.choppiness_trending}")
        logger.info(f"  Range%: Tight<{self.range_tight}%, Moderate<{self.range_moderate}%")
        logger.info(f"  Cache TTL: {self.cache_ttl}s")

    def get_required_data_points(self) -> int:
        """
        Get minimum number of data points required for market analysis.

        Returns:
            Minimum number of candles/prices needed
        """
        return max(self.adx_period * 2, self.range_period)

    def _get_cache_key(self, prices: List[float]) -> str:
        """Get cache key from most recent price."""
        return f"price_{prices[-1] if prices else 0}" if prices else "empty"

    def _is_cache_valid(self, symbol: Optional[str] = None) -> bool:
        """Check if cache entry exists and is still valid."""
        if not symbol or symbol not in self._analysis_cache:
            return False
        condition, timestamp = self._analysis_cache[symbol]
        return time.time() - timestamp < self.cache_ttl

    def analyze(
        self,
        prices: List[float],
        highs: Optional[List[float]] = None,
        lows: Optional[List[float]] = None,
        symbol: Optional[str] = None
    ) -> MarketCondition:
        """
        Analyze market data and return market condition.

        Args:
            prices: List of closing prices (most recent last)
            highs: Optional list of high prices
            lows: Optional list of low prices
            symbol: Optional symbol for caching results

        Returns:
            MarketCondition object describing current market state
        """
        # Check cache first if symbol provided
        if symbol and self._is_cache_valid(symbol):
            condition, _ = self._analysis_cache[symbol]
            logger.debug(f"[{symbol}] Using cached market condition (TTL: {self.cache_ttl}s)")
            return condition

        # If highs/lows not provided, use closing prices as approximation
        if highs is None:
            highs = prices
        if lows is None:
            lows = prices

        # Check minimum data requirement
        min_required = self.get_required_data_points()
        if len(prices) < min_required:
            logger.warning(f"Insufficient data for analysis: {len(prices)}/{min_required}")
            return MarketCondition(
                state=MarketState.UNKNOWN,
                confidence=0.0,
                description=f"Need {min_required} data points, have {len(prices)}"
            )

        # Calculate all indicators
        adx = calculate_adx(highs, lows, prices, self.adx_period)
        atr = calculate_atr(highs, lows, prices, self.atr_period)
        choppiness = calculate_choppiness_index(highs, lows, prices, self.chop_period)
        slope = calculate_linear_regression_slope(prices, self.slope_period)
        range_pct = calculate_range_percent(prices, self.range_period)

        # Detect market state using decision tree
        state, confidence = self._determine_state(adx, atr, choppiness, slope, range_pct, prices)

        # Create description
        description = self._create_description(state, adx, range_pct, choppiness, slope)

        condition = MarketCondition(
            state=state,
            adx=adx,
            atr=atr,
            range_percent=range_pct,
            choppiness=choppiness,
            slope=slope,
            confidence=confidence,
            description=description
        )

        # Cache result if symbol provided
        if symbol:
            self._analysis_cache[symbol] = (condition, time.time())

        return condition

    def _determine_state(
        self,
        adx: Optional[float],
        atr: Optional[float],
        choppiness: Optional[float],
        slope: Optional[float],
        range_pct: Optional[float],
        prices: List[float]
    ) -> Tuple[MarketState, float]:
        """
        Determine market state using decision tree logic.

        Returns:
            Tuple of (MarketState, confidence)
        """
        if adx is None or range_pct is None:
            return (MarketState.UNKNOWN, 0.0)

        confidence = 0.7  # Base confidence

        # Decision tree implementation

        # Path 1: Strong trending market (ADX > 25)
        if adx > self.adx_strong_trend:
            confidence = 0.8
            if slope and slope > 0:
                return (MarketState.STRONG_UPTREND, confidence)
            elif slope and slope < 0:
                return (MarketState.STRONG_DOWNTREND, confidence)
            else:
                return (MarketState.MODERATE_TREND, confidence)

        # Path 2: Weak trend / ranging market (ADX < 20)
        elif adx < self.adx_weak_trend:

            # Sub-path 2a: Range-bound (moderate range, not too choppy)
            if range_pct < self.range_moderate:
                confidence = 0.75

                # Very tight range
                if range_pct < self.range_tight:
                    return (MarketState.LOW_VOLATILITY, 0.8)

                # Check choppiness
                if choppiness and choppiness < self.choppiness_choppy:
                    return (MarketState.RANGE_BOUND, confidence)
                else:
                    return (MarketState.CHOPPY, 0.6)

            # Sub-path 2b: Wide range with weak trend = volatile/choppy
            else:
                if atr and choppiness and choppiness > self.choppiness_choppy:
                    return (MarketState.CHOPPY, 0.7)
                else:
                    # Might be start of breakout
                    return (MarketState.VOLATILE_BREAKOUT, 0.6)

        # Path 3: Moderate ADX (20-25) - transitioning
        else:
            confidence = 0.65

            # Check if it's becoming a trend
            if choppiness and choppiness < self.choppiness_trending:
                return (MarketState.MODERATE_TREND, confidence)
            else:
                # Still ranging but might trend soon
                return (MarketState.RANGE_BOUND, 0.6)

    def _create_description(
        self,
        state: MarketState,
        adx: Optional[float],
        range_pct: Optional[float],
        choppiness: Optional[float],
        slope: Optional[float]
    ) -> str:
        """
        Create human-readable description of market state.

        Args:
            state: Detected market state
            adx: ADX value
            range_pct: Range percentage
            choppiness: Choppiness index
            slope: Linear regression slope

        Returns:
            Description string
        """
        # Handle None values with defaults for display
        adx_str = f"{adx:.1f}" if adx is not None else "N/A"
        range_str = f"{range_pct:.1f}" if range_pct is not None else "N/A"
        chop_str = f"{choppiness:.1f}" if choppiness is not None else "N/A"

        descriptions = {
            MarketState.STRONG_UPTREND: f"Strong uptrend detected (ADX {adx_str}, positive momentum)",
            MarketState.STRONG_DOWNTREND: f"Strong downtrend detected (ADX {adx_str}, negative momentum)",
            MarketState.MODERATE_TREND: f"Moderate trend (ADX {adx_str}, developing direction)",
            MarketState.RANGE_BOUND: f"Range-bound market (ADX {adx_str}, {range_str}% range)",
            MarketState.VOLATILE_BREAKOUT: f"Volatile breakout condition (wide range {range_str}%)",
            MarketState.CHOPPY: f"Choppy market (choppiness {chop_str}, no clear direction)",
            MarketState.LOW_VOLATILITY: f"Low volatility ({range_str}% range, tight consolidation)",
            MarketState.UNKNOWN: "Insufficient data for analysis"
        }

        return descriptions.get(state, "Unknown market condition")

    def get_required_data_points(self) -> int:
        """
        Get minimum number of data points required for analysis.

        Returns:
            Minimum data points needed
        """
        return max(self.adx_period * 2, self.range_period)
