"""Technical indicators for trading strategies."""
from typing import List, Optional, Tuple
import statistics


def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """
    Calculate Relative Strength Index (RSI).

    Args:
        prices: List of prices (most recent last)
        period: RSI period (default 14)

    Returns:
        RSI value (0-100) or None if insufficient data
    """
    if len(prices) < period + 1:
        return None

    # Calculate price changes
    changes = [prices[i] - prices[i - 1] for i in range(-period, 0)]

    # Separate gains and losses
    gains = [change if change > 0 else 0 for change in changes]
    losses = [-change if change < 0 else 0 for change in changes]

    # Calculate average gain and loss
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    # Avoid division by zero
    if avg_loss == 0:
        return 100.0

    # Calculate RS and RSI
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_bollinger_bands(
    prices: List[float], period: int = 20, std_dev: float = 2.0
) -> Optional[Tuple[float, float, float]]:
    """
    Calculate Bollinger Bands.

    Args:
        prices: List of prices (most recent last)
        period: Moving average period (default 20)
        std_dev: Number of standard deviations (default 2.0)

    Returns:
        Tuple of (upper_band, middle_band, lower_band) or None if insufficient data
    """
    if len(prices) < period:
        return None

    # Calculate middle band (SMA)
    recent_prices = prices[-period:]
    middle_band = sum(recent_prices) / period

    # Calculate standard deviation
    variance = sum((p - middle_band) ** 2 for p in recent_prices) / period
    std = variance ** 0.5

    # Calculate bands
    upper_band = middle_band + (std_dev * std)
    lower_band = middle_band - (std_dev * std)

    return (upper_band, middle_band, lower_band)


def calculate_sma(prices: List[float], period: int) -> Optional[float]:
    """
    Calculate Simple Moving Average.

    Args:
        prices: List of prices (most recent last)
        period: SMA period

    Returns:
        SMA value or None if insufficient data
    """
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def calculate_ema(prices: List[float], period: int) -> Optional[float]:
    """
    Calculate Exponential Moving Average.

    Args:
        prices: List of prices (most recent last)
        period: EMA period

    Returns:
        EMA value or None if insufficient data
    """
    if len(prices) < period:
        return None

    # Calculate multiplier
    multiplier = 2 / (period + 1)

    # Start with SMA
    ema = sum(prices[:period]) / period

    # Calculate EMA for remaining prices
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema

    return ema


def detect_support_resistance(
    prices: List[float], window: int = 10, threshold: float = 0.02
) -> Tuple[List[float], List[float]]:
    """
    Detect support and resistance levels from price history.

    Args:
        prices: List of prices
        window: Window size for local min/max detection
        threshold: Clustering threshold (as fraction of price)

    Returns:
        Tuple of (support_levels, resistance_levels)
    """
    if len(prices) < window * 2:
        return ([], [])

    support_levels = []
    resistance_levels = []

    # Find local minima (support) and maxima (resistance)
    for i in range(window, len(prices) - window):
        price = prices[i]

        # Check if local minimum
        if price == min(prices[i - window : i + window + 1]):
            support_levels.append(price)

        # Check if local maximum
        if price == max(prices[i - window : i + window + 1]):
            resistance_levels.append(price)

    # Cluster nearby levels
    support_levels = _cluster_levels(support_levels, threshold)
    resistance_levels = _cluster_levels(resistance_levels, threshold)

    return (support_levels, resistance_levels)


def _cluster_levels(levels: List[float], threshold: float) -> List[float]:
    """
    Cluster nearby price levels together.

    Args:
        levels: List of price levels
        threshold: Clustering threshold (as fraction of price)

    Returns:
        List of clustered average levels
    """
    if not levels:
        return []

    levels = sorted(levels)
    clustered = []
    current_cluster = [levels[0]]

    for level in levels[1:]:
        # Check if within threshold of current cluster average
        cluster_avg = sum(current_cluster) / len(current_cluster)
        if abs(level - cluster_avg) / cluster_avg <= threshold:
            current_cluster.append(level)
        else:
            # Save current cluster and start new one
            clustered.append(sum(current_cluster) / len(current_cluster))
            current_cluster = [level]

    # Add last cluster
    if current_cluster:
        clustered.append(sum(current_cluster) / len(current_cluster))

    return clustered


def calculate_atr(
    highs: List[float], lows: List[float], closes: List[float], period: int = 14
) -> Optional[float]:
    """
    Calculate Average True Range (ATR) for volatility measurement.

    Args:
        highs: List of high prices
        lows: List of low prices
        closes: List of closing prices
        period: ATR period

    Returns:
        ATR value or None if insufficient data
    """
    if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
        return None

    true_ranges = []
    for i in range(-period, 0):
        high_low = highs[i] - lows[i]
        high_close = abs(highs[i] - closes[i - 1])
        low_close = abs(lows[i] - closes[i - 1])
        true_range = max(high_low, high_close, low_close)
        true_ranges.append(true_range)

    atr = sum(true_ranges) / period
    return atr


def calculate_adx(
    highs: List[float], lows: List[float], closes: List[float], period: int = 14
) -> Optional[float]:
    """
    Calculate Average Directional Index (ADX) for trend strength measurement.

    ADX measures trend strength regardless of direction:
    - ADX > 25: Strong trend
    - ADX 20-25: Moderate trend
    - ADX < 20: Weak trend or ranging market

    Args:
        highs: List of high prices
        lows: List of low prices
        closes: List of closing prices
        period: ADX period (typically 14)

    Returns:
        ADX value (0-100) or None if insufficient data
    """
    if len(highs) < period * 2 or len(lows) < period * 2 or len(closes) < period * 2:
        return None

    # Calculate +DM and -DM
    plus_dm = []
    minus_dm = []

    for i in range(1, len(highs)):
        high_diff = highs[i] - highs[i - 1]
        low_diff = lows[i - 1] - lows[i]

        if high_diff > low_diff and high_diff > 0:
            plus_dm.append(high_diff)
        else:
            plus_dm.append(0)

        if low_diff > high_diff and low_diff > 0:
            minus_dm.append(low_diff)
        else:
            minus_dm.append(0)

    # Calculate ATR for normalization
    atr_values = []
    for i in range(period, len(closes)):
        atr = calculate_atr(highs[i-period:i+1], lows[i-period:i+1], closes[i-period:i+1], period)
        if atr:
            atr_values.append(atr)

    if not atr_values:
        return None

    # Calculate smoothed +DI and -DI
    plus_di_values = []
    minus_di_values = []

    for i in range(period - 1, len(plus_dm)):
        smoothed_plus_dm = sum(plus_dm[i-period+1:i+1]) / period
        smoothed_minus_dm = sum(minus_dm[i-period+1:i+1]) / period

        if i - period + 1 < len(atr_values):
            atr_val = atr_values[min(i - period + 1, len(atr_values) - 1)]
            if atr_val > 0:
                plus_di = (smoothed_plus_dm / atr_val) * 100
                minus_di = (smoothed_minus_dm / atr_val) * 100
                plus_di_values.append(plus_di)
                minus_di_values.append(minus_di)

    if not plus_di_values or not minus_di_values:
        return None

    # Calculate DX
    dx_values = []
    for i in range(len(plus_di_values)):
        di_sum = plus_di_values[i] + minus_di_values[i]
        if di_sum > 0:
            di_diff = abs(plus_di_values[i] - minus_di_values[i])
            dx = (di_diff / di_sum) * 100
            dx_values.append(dx)

    if len(dx_values) < period:
        return None

    # Calculate ADX (smoothed DX)
    adx = sum(dx_values[-period:]) / period
    return adx


def calculate_choppiness_index(
    highs: List[float], lows: List[float], closes: List[float], period: int = 14
) -> Optional[float]:
    """
    Calculate Choppiness Index to determine if market is choppy or trending.

    Choppiness Index measures market directionality:
    - CI > 61.8: Very choppy, sideways market
    - CI 38.2-61.8: Transitioning
    - CI < 38.2: Strong trending market

    Args:
        highs: List of high prices
        lows: List of low prices
        closes: List of closing prices
        period: Choppiness period (typically 14)

    Returns:
        Choppiness Index value (0-100) or None if insufficient data
    """
    if len(highs) < period or len(lows) < period or len(closes) < period:
        return None

    # Calculate ATR sum
    atr_sum = 0
    for i in range(-period + 1, 1):
        if i == -period + 1:
            # First TR
            tr = highs[i] - lows[i]
        else:
            high_low = highs[i] - lows[i]
            high_close = abs(highs[i] - closes[i - 1])
            low_close = abs(lows[i] - closes[i - 1])
            tr = max(high_low, high_close, low_close)
        atr_sum += tr

    # Calculate high-low range
    period_high = max(highs[-period:])
    period_low = min(lows[-period:])
    high_low_range = period_high - period_low

    if high_low_range == 0:
        return 100.0  # Completely flat = maximum choppiness

    # Calculate Choppiness Index
    import math
    ci = 100 * math.log10(atr_sum / high_low_range) / math.log10(period)

    return max(0, min(100, ci))  # Clamp between 0-100


def calculate_linear_regression_slope(prices: List[float], period: int = 14) -> Optional[float]:
    """
    Calculate the slope of linear regression line to determine trend direction.

    Positive slope = Uptrend
    Negative slope = Downtrend
    Near-zero slope = Sideways

    Args:
        prices: List of prices
        period: Number of periods to analyze

    Returns:
        Slope value or None if insufficient data
    """
    if len(prices) < period:
        return None

    recent_prices = prices[-period:]
    n = len(recent_prices)

    # Calculate means
    x_mean = (n - 1) / 2  # 0, 1, 2, ... n-1
    y_mean = sum(recent_prices) / n

    # Calculate slope using least squares
    numerator = 0
    denominator = 0

    for i in range(n):
        x_diff = i - x_mean
        y_diff = recent_prices[i] - y_mean
        numerator += x_diff * y_diff
        denominator += x_diff * x_diff

    if denominator == 0:
        return 0.0

    slope = numerator / denominator
    return slope


def calculate_range_percent(prices: List[float], period: int = 50) -> Optional[float]:
    """
    Calculate the percentage range of price movement.

    Shows how wide the trading range is as a percentage of price.

    Args:
        prices: List of prices
        period: Number of periods to analyze

    Returns:
        Range percentage or None if insufficient data
    """
    if len(prices) < period:
        return None

    recent_prices = prices[-period:]
    high = max(recent_prices)
    low = min(recent_prices)

    if low == 0:
        return None

    range_pct = ((high - low) / low) * 100
    return range_pct


def calculate_macd(
    prices: List[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9
) -> Optional[tuple]:
    """
    Calculate MACD (Moving Average Convergence Divergence).

    MACD is a trend-following momentum indicator that shows the relationship
    between two moving averages of prices.

    Args:
        prices: List of prices
        fast_period: Fast EMA period (default 12)
        slow_period: Slow EMA period (default 26)
        signal_period: Signal line EMA period (default 9)

    Returns:
        Tuple of (macd_line, signal_line, histogram) or None if insufficient data
    """
    if len(prices) < slow_period + signal_period:
        return None

    # Calculate fast and slow EMAs
    fast_ema = calculate_ema(prices, fast_period)
    slow_ema = calculate_ema(prices, slow_period)

    if fast_ema is None or slow_ema is None:
        return None

    # MACD line = Fast EMA - Slow EMA
    macd_line = fast_ema - slow_ema

    # Calculate signal line (EMA of MACD line)
    # We need to calculate MACD for all periods to get signal line
    macd_values = []
    for i in range(slow_period, len(prices) + 1):
        f_ema = calculate_ema(prices[:i], fast_period)
        s_ema = calculate_ema(prices[:i], slow_period)
        if f_ema and s_ema:
            macd_values.append(f_ema - s_ema)

    if len(macd_values) < signal_period:
        return None

    signal_line = calculate_ema(macd_values, signal_period)

    if signal_line is None:
        return None

    # Histogram = MACD line - Signal line
    histogram = macd_line - signal_line

    return (macd_line, signal_line, histogram)


def calculate_volume_surge(
    volumes: List[float],
    period: int = 20,
    threshold: float = 1.5
) -> bool:
    """
    Detect if current volume is significantly above average.

    Args:
        volumes: List of volume values
        period: Period to calculate average volume
        threshold: Multiplier for surge detection (1.5 = 50% above average)

    Returns:
        True if volume surge detected
    """
    if len(volumes) < period + 1:
        return False

    avg_volume = sum(volumes[-period-1:-1]) / period
    current_volume = volumes[-1]

    if avg_volume == 0:
        return False

    return current_volume >= (avg_volume * threshold)


def find_swing_high_low(
    prices: List[float],
    period: int = 50
) -> Optional[Tuple[float, float]]:
    """
    Find recent swing high and low for Fibonacci calculation.

    Args:
        prices: List of prices (most recent last)
        period: Lookback period to find swing points (default 50)

    Returns:
        Tuple of (swing_high, swing_low) or None if insufficient data
    """
    if len(prices) < period:
        return None

    # Use last 'period' prices
    recent_prices = prices[-period:]

    swing_high = max(recent_prices)
    swing_low = min(recent_prices)

    return (swing_high, swing_low)


def calculate_fibonacci_retracement(
    swing_high: float,
    swing_low: float
) -> dict:
    """
    Calculate Fibonacci retracement levels.

    Fibonacci retracement levels are used to identify potential support
    and resistance levels based on the Fibonacci sequence.

    Key levels:
    - 23.6%: Shallow retracement (weak pullback)
    - 38.2%: Moderate retracement
    - 50.0%: Midpoint (not a Fibonacci number but widely used)
    - 61.8%: Golden ratio - strongest retracement level
    - 78.6%: Deep retracement (trend may be weakening)

    Args:
        swing_high: Recent swing high price
        swing_low: Recent swing low price

    Returns:
        Dictionary with Fibonacci retracement levels
    """
    diff = swing_high - swing_low

    return {
        '0.0%': swing_high,
        '23.6%': swing_high - (diff * 0.236),
        '38.2%': swing_high - (diff * 0.382),
        '50.0%': swing_high - (diff * 0.500),
        '61.8%': swing_high - (diff * 0.618),
        '78.6%': swing_high - (diff * 0.786),
        '100.0%': swing_low
    }


def calculate_fibonacci_extensions(
    swing_high: float,
    swing_low: float
) -> dict:
    """
    Calculate Fibonacci extension levels (for breakout targets).

    Fibonacci extensions project potential price targets beyond the
    current price range, useful for identifying profit targets.

    Key levels:
    - 127.2%: First extension target
    - 161.8%: Golden ratio extension - primary target
    - 200.0%: Secondary target
    - 261.8%: Extended target

    Args:
        swing_high: Recent swing high price
        swing_low: Recent swing low price

    Returns:
        Dictionary with Fibonacci extension levels
    """
    diff = swing_high - swing_low

    return {
        '0.0%': swing_high,
        '127.2%': swing_high + (diff * 0.272),
        '161.8%': swing_high + (diff * 0.618),
        '200.0%': swing_high + diff,
        '261.8%': swing_high + (diff * 1.618)
    }


def is_near_fibonacci_level(
    current_price: float,
    fib_levels: dict,
    tolerance_percent: float = 0.5
) -> Optional[Tuple[str, float]]:
    """
    Check if current price is near a Fibonacci level.

    Args:
        current_price: Current market price
        fib_levels: Dictionary of Fibonacci levels from calculate_fibonacci_retracement()
        tolerance_percent: How close price needs to be (default 0.5%)

    Returns:
        Tuple of (level_name, level_price) if near a level, None otherwise

    Example:
        >>> fib = calculate_fibonacci_retracement(110000, 100000)
        >>> is_near_fibonacci_level(106180, fib, 0.5)
        ('61.8%', 106180.0)
    """
    for level_name, level_price in fib_levels.items():
        # Calculate percentage difference
        diff_percent = abs((current_price - level_price) / level_price * 100)

        if diff_percent <= tolerance_percent:
            return (level_name, level_price)

    return None


def get_fibonacci_signal_strength(
    current_price: float,
    fib_levels: dict,
    key_levels: List[str] = ['38.2%', '50.0%', '61.8%'],
    tolerance_percent: float = 1.0
) -> float:
    """
    Calculate signal strength based on proximity to key Fibonacci levels.

    The 61.8% level (golden ratio) is weighted highest, followed by
    38.2% and 50.0% levels.

    Args:
        current_price: Current market price
        fib_levels: Dictionary of Fibonacci levels
        key_levels: List of important Fibonacci levels to check
        tolerance_percent: Proximity tolerance (default 1.0%)

    Returns:
        Signal strength multiplier (1.0 to 1.3)
        - 1.0 = not near any Fibonacci level (no bonus)
        - 1.1 = near 38.2% or 50.0% level (+10% confidence)
        - 1.2 = near 61.8% level (+20% confidence - golden ratio)
        - 1.3 = at exact Fibonacci level (+30% confidence)
    """
    # Weight for each level
    level_weights = {
        '38.2%': 1.1,
        '50.0%': 1.1,
        '61.8%': 1.2,  # Golden ratio - highest weight
        '78.6%': 1.15
    }

    best_strength = 1.0

    for level_name in key_levels:
        if level_name not in fib_levels:
            continue

        level_price = fib_levels[level_name]
        diff_percent = abs((current_price - level_price) / level_price * 100)

        if diff_percent <= tolerance_percent:
            # Very close to level
            if diff_percent <= 0.2:
                strength = 1.3  # At exact level
            else:
                strength = level_weights.get(level_name, 1.1)

            best_strength = max(best_strength, strength)

    return best_strength
