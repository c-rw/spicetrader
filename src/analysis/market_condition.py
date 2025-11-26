"""Market condition data structures."""
from enum import Enum
from dataclasses import dataclass
from typing import Optional


class MarketState(Enum):
    """Possible market states."""
    STRONG_UPTREND = "strong_uptrend"
    STRONG_DOWNTREND = "strong_downtrend"
    MODERATE_TREND = "moderate_trend"
    RANGE_BOUND = "range_bound"
    VOLATILE_BREAKOUT = "volatile_breakout"
    CHOPPY = "choppy"
    LOW_VOLATILITY = "low_volatility"
    UNKNOWN = "unknown"


@dataclass
class MarketCondition:
    """
    Data class representing current market conditions.

    Attributes:
        state: The detected market state
        adx: Average Directional Index (trend strength)
        atr: Average True Range (volatility)
        range_percent: Price range as percentage
        choppiness: Choppiness Index
        slope: Linear regression slope
        confidence: Confidence in state detection (0-1)
        description: Human-readable description
    """
    state: MarketState
    adx: Optional[float] = None
    atr: Optional[float] = None
    range_percent: Optional[float] = None
    choppiness: Optional[float] = None
    slope: Optional[float] = None
    confidence: float = 0.0
    description: str = ""

    def __str__(self) -> str:
        """String representation of market condition."""
        parts = [f"State: {self.state.value}"]

        if self.adx is not None:
            parts.append(f"ADX: {self.adx:.1f}")
        if self.atr is not None:
            parts.append(f"ATR: ${self.atr:.2f}")
        if self.range_percent is not None:
            parts.append(f"Range: {self.range_percent:.1f}%")
        if self.choppiness is not None:
            parts.append(f"Chop: {self.choppiness:.1f}")
        if self.slope is not None:
            direction = "↗" if self.slope > 0 else "↘" if self.slope < 0 else "→"
            parts.append(f"Slope: {direction} {abs(self.slope):.2f}")

        parts.append(f"Confidence: {self.confidence*100:.0f}%")

        return " | ".join(parts)

    def is_trending(self) -> bool:
        """Check if market is in a trending state."""
        return self.state in [
            MarketState.STRONG_UPTREND,
            MarketState.STRONG_DOWNTREND,
            MarketState.MODERATE_TREND
        ]

    def is_ranging(self) -> bool:
        """Check if market is in a ranging state."""
        return self.state == MarketState.RANGE_BOUND

    def is_volatile(self) -> bool:
        """Check if market is in a volatile state."""
        return self.state in [
            MarketState.VOLATILE_BREAKOUT,
            MarketState.CHOPPY
        ]

    def get_recommended_strategy(self) -> str:
        """
        Get recommended strategy name for this market state.

        Returns:
            Strategy name ('mean_reversion', 'sma_crossover', etc.)
        """
        if self.state == MarketState.RANGE_BOUND:
            return 'mean_reversion'
        elif self.state in [MarketState.STRONG_UPTREND, MarketState.STRONG_DOWNTREND]:
            return 'sma_crossover'
        elif self.state == MarketState.MODERATE_TREND:
            return 'macd'
        elif self.state == MarketState.VOLATILE_BREAKOUT:
            return 'breakout'
        elif self.state == MarketState.CHOPPY:
            return 'mean_reversion'
        elif self.state == MarketState.LOW_VOLATILITY:
            return 'grid'
        else:
            return 'mean_reversion'  # Default to conservative strategy
