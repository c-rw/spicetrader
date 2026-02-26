"""Tests for technical indicators (src/indicators.py).

Covers:
- RSI (Wilder's smoothing)
- MACD (O(n) incremental)
- Bollinger Bands
- SMA / EMA
- ATR
- Volume surge detection
- Fibonacci helpers
"""
from __future__ import annotations

import pytest

from src.indicators import (
    calculate_rsi,
    calculate_bollinger_bands,
    calculate_sma,
    calculate_ema,
    calculate_atr,
    calculate_macd,
    calculate_volume_surge,
    find_swing_high_low,
    calculate_fibonacci_retracement,
    calculate_fibonacci_extensions,
    is_near_fibonacci_level,
    get_fibonacci_signal_strength,
    calculate_linear_regression_slope,
    calculate_range_percent,
)


# ---------------------------------------------------------------------------
# RSI — Wilder's smoothing
# ---------------------------------------------------------------------------

class TestRSI:
    """Tests for calculate_rsi using Wilder's smoothing."""

    def test_insufficient_data_returns_none(self):
        """Need at least period+1 prices."""
        assert calculate_rsi([100.0] * 14, period=14) is None
        assert calculate_rsi([], period=14) is None

    def test_exact_minimum_data(self):
        """period+1 prices should produce a result (seed only, no smoothing)."""
        prices = list(range(100, 116))  # 16 prices, 15 changes, period=14 -> 1 extra
        result = calculate_rsi(prices, period=14)
        assert result is not None
        assert 0 <= result <= 100

    def test_all_gains_returns_100(self):
        """Monotonically increasing prices => RSI = 100."""
        prices = [float(i) for i in range(100, 130)]  # 30 up ticks
        rsi = calculate_rsi(prices, period=14)
        assert rsi == 100.0

    def test_all_losses_returns_0(self):
        """Monotonically decreasing prices => RSI = 0."""
        prices = [float(200 - i) for i in range(30)]  # 30 down ticks
        rsi = calculate_rsi(prices, period=14)
        assert rsi is not None
        assert rsi == pytest.approx(0.0, abs=0.01)

    def test_flat_prices(self):
        """Flat prices => avg_gain=0, avg_loss=0 => RSI=100 (per implementation)."""
        prices = [100.0] * 30
        rsi = calculate_rsi(prices, period=14)
        # avg_loss==0 branch returns 100.0
        assert rsi == 100.0

    def test_wilder_smoothing_differs_from_simple(self):
        """Verify smoothing is applied — result uses more data than just the seed window."""
        # Build prices that rise for 15 ticks then drop sharply
        prices = [100.0 + i for i in range(16)]  # 100..115 (all gains in seed)
        prices += [115.0 - i * 3 for i in range(1, 11)]  # sharp drop
        assert len(prices) == 26

        rsi = calculate_rsi(prices, period=14)
        assert rsi is not None
        # After the sharp drop, RSI should be well below 50
        assert rsi < 50

    def test_rsi_range_always_0_to_100(self):
        """RSI must always be in [0, 100] for any realistic input."""
        import random
        random.seed(42)
        prices = [100.0]
        for _ in range(100):
            prices.append(prices[-1] + random.uniform(-5, 5))
        rsi = calculate_rsi(prices, period=14)
        assert rsi is not None
        assert 0 <= rsi <= 100


# ---------------------------------------------------------------------------
# MACD — O(n) incremental
# ---------------------------------------------------------------------------

class TestMACD:
    """Tests for calculate_macd (O(n) incremental EMA)."""

    def test_insufficient_data_returns_none(self):
        """Need at least slow_period + signal_period prices."""
        prices = [100.0] * 34  # 26 + 9 - 1 = 34 (not enough)
        assert calculate_macd(prices, fast_period=12, slow_period=26, signal_period=9) is None

    def test_exact_minimum_data(self):
        """slow_period + signal_period = 35 prices should work."""
        prices = [100.0 + i * 0.1 for i in range(35)]
        result = calculate_macd(prices, fast_period=12, slow_period=26, signal_period=9)
        assert result is not None
        macd_line, signal_line, histogram = result
        assert isinstance(macd_line, float)
        assert isinstance(signal_line, float)
        assert abs(histogram - (macd_line - signal_line)) < 1e-10

    def test_histogram_equals_macd_minus_signal(self):
        """Histogram must always equal macd_line - signal_line."""
        prices = [100.0 + i * 0.5 for i in range(60)]
        result = calculate_macd(prices)
        assert result is not None
        macd_line, signal_line, histogram = result
        assert histogram == pytest.approx(macd_line - signal_line, abs=1e-10)

    def test_uptrend_positive_macd(self):
        """In a consistent uptrend, fast EMA > slow EMA => positive MACD line."""
        prices = [100.0 + i for i in range(60)]
        result = calculate_macd(prices)
        assert result is not None
        macd_line, _, _ = result
        assert macd_line > 0

    def test_downtrend_negative_macd(self):
        """In a consistent downtrend, fast EMA < slow EMA => negative MACD line."""
        prices = [200.0 - i for i in range(60)]
        result = calculate_macd(prices)
        assert result is not None
        macd_line, _, _ = result
        assert macd_line < 0

    def test_flat_prices_near_zero_macd(self):
        """Flat prices => MACD near zero."""
        prices = [100.0] * 60
        result = calculate_macd(prices)
        assert result is not None
        macd_line, signal_line, histogram = result
        assert abs(macd_line) < 0.01
        assert abs(signal_line) < 0.01
        assert abs(histogram) < 0.01


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

class TestBollingerBands:
    """Tests for calculate_bollinger_bands."""

    def test_insufficient_data(self):
        assert calculate_bollinger_bands([100.0] * 19, period=20) is None

    def test_flat_prices_zero_bandwidth(self):
        """Flat prices => upper == middle == lower."""
        result = calculate_bollinger_bands([50.0] * 20, period=20, std_dev=2.0)
        assert result is not None
        upper, middle, lower = result
        assert upper == pytest.approx(50.0)
        assert middle == pytest.approx(50.0)
        assert lower == pytest.approx(50.0)

    def test_band_ordering(self):
        """Upper >= middle >= lower always."""
        prices = [100 + i % 5 for i in range(30)]
        result = calculate_bollinger_bands(prices, period=20)
        assert result is not None
        upper, middle, lower = result
        assert upper >= middle >= lower

    def test_middle_band_is_sma(self):
        """Middle band should equal the SMA of last `period` prices."""
        prices = list(range(100, 130))  # 30 prices
        result = calculate_bollinger_bands(prices, period=20)
        assert result is not None
        _, middle, _ = result
        expected_sma = sum(prices[-20:]) / 20
        assert middle == pytest.approx(expected_sma)

    def test_wider_std_dev_widens_bands(self):
        """Increasing std_dev multiplier should widen the bands."""
        prices = [100 + (i % 10) for i in range(30)]
        r1 = calculate_bollinger_bands(prices, period=20, std_dev=1.0)
        r2 = calculate_bollinger_bands(prices, period=20, std_dev=3.0)
        assert r1 is not None and r2 is not None
        # Wider std_dev => wider bandwidth
        bw1 = r1[0] - r1[2]
        bw2 = r2[0] - r2[2]
        assert bw2 > bw1


# ---------------------------------------------------------------------------
# SMA / EMA
# ---------------------------------------------------------------------------

class TestSMAEMA:
    """Tests for calculate_sma and calculate_ema."""

    def test_sma_insufficient_data(self):
        assert calculate_sma([1.0, 2.0], period=5) is None

    def test_sma_correct_value(self):
        prices = [10.0, 20.0, 30.0, 40.0, 50.0]
        assert calculate_sma(prices, period=5) == pytest.approx(30.0)

    def test_sma_uses_last_n_prices(self):
        prices = [1.0, 2.0, 3.0, 4.0, 5.0, 100.0]
        # SMA(3) of last 3: (4+5+100)/3
        assert calculate_sma(prices, period=3) == pytest.approx(109.0 / 3)

    def test_ema_insufficient_data(self):
        assert calculate_ema([1.0], period=5) is None

    def test_ema_with_exact_period(self):
        """With exactly period prices, EMA == SMA (no smoothing applied)."""
        prices = [10.0, 20.0, 30.0, 40.0, 50.0]
        ema = calculate_ema(prices, period=5)
        assert ema == pytest.approx(30.0)

    def test_ema_weights_recent_more(self):
        """EMA should be pulled toward recent prices more than SMA."""
        # Prices go up at the end
        prices = [100.0] * 20 + [110.0, 120.0, 130.0]
        sma = calculate_sma(prices, period=10)
        ema = calculate_ema(prices, period=10)
        assert sma is not None and ema is not None
        # EMA reacts faster to the recent spike
        assert ema > sma


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------

class TestATR:
    """Tests for calculate_atr."""

    def test_insufficient_data(self):
        assert calculate_atr([100.0] * 5, [90.0] * 5, [95.0] * 5, period=14) is None

    def test_flat_market_zero_atr(self):
        """If high==low==close for all bars, ATR should be 0."""
        n = 20
        flat = [100.0] * n
        atr = calculate_atr(flat, flat, flat, period=14)
        assert atr is not None
        assert atr == pytest.approx(0.0)

    def test_known_atr(self):
        """ATR with simple known values."""
        # 16 bars: high-low=10 constant, closes in middle, no gaps
        n = 16
        highs = [110.0] * n
        lows = [100.0] * n
        closes = [105.0] * n
        atr = calculate_atr(highs, lows, closes, period=14)
        assert atr is not None
        # True range = max(10, |110-105|, |100-105|) = 10 for each bar
        assert atr == pytest.approx(10.0)

    def test_gap_increases_atr(self):
        """A gap (close far from next high/low) should increase true range."""
        n = 16
        highs = [110.0] * n
        lows = [100.0] * n
        closes = [105.0] * n
        # Create a gap: previous close at 90 makes high_close = |110-90| = 20
        closes[-15] = 90.0  # The bar before the ATR window
        atr = calculate_atr(highs, lows, closes, period=14)
        assert atr is not None
        assert atr > 10.0  # Should be larger than the no-gap case


# ---------------------------------------------------------------------------
# Volume Surge
# ---------------------------------------------------------------------------

class TestVolumeSurge:
    """Tests for calculate_volume_surge."""

    def test_insufficient_data(self):
        assert calculate_volume_surge([100.0] * 10, period=20) is False

    def test_surge_detected(self):
        """Volume 2x the average should be detected with threshold=1.5."""
        volumes = [100.0] * 21 + [200.0]  # avg of prior 20 = 100, current = 200
        assert calculate_volume_surge(volumes, period=20, threshold=1.5) is True

    def test_no_surge(self):
        """Volume at average should not be a surge."""
        volumes = [100.0] * 22  # current == average
        assert calculate_volume_surge(volumes, period=20, threshold=1.5) is False

    def test_zero_average_no_crash(self):
        """Zero average volume should return False, not crash."""
        volumes = [0.0] * 22
        assert calculate_volume_surge(volumes, period=20) is False


# ---------------------------------------------------------------------------
# Fibonacci helpers
# ---------------------------------------------------------------------------

class TestFibonacci:
    """Tests for Fibonacci retracement, extension, and proximity helpers."""

    def test_find_swing_high_low(self):
        prices = list(range(50, 110))  # 60 prices, 50..109
        result = find_swing_high_low(prices, period=50)
        assert result is not None
        swing_high, swing_low = result
        assert swing_high == 109.0
        assert swing_low == 60.0  # last 50 prices: 60..109

    def test_find_swing_high_low_insufficient(self):
        assert find_swing_high_low([1.0, 2.0], period=50) is None

    def test_retracement_levels(self):
        fib = calculate_fibonacci_retracement(110.0, 100.0)
        assert fib['0.0%'] == 110.0
        assert fib['100.0%'] == 100.0
        assert fib['50.0%'] == pytest.approx(105.0)
        assert fib['61.8%'] == pytest.approx(103.82)
        assert fib['38.2%'] == pytest.approx(106.18)

    def test_extension_levels(self):
        fib = calculate_fibonacci_extensions(110.0, 100.0)
        assert fib['0.0%'] == 110.0
        assert fib['200.0%'] == pytest.approx(120.0)
        assert fib['161.8%'] == pytest.approx(116.18)

    def test_is_near_fibonacci_level_hit(self):
        fib = calculate_fibonacci_retracement(110.0, 100.0)
        # Price at 61.8% level = 103.82
        result = is_near_fibonacci_level(103.82, fib, tolerance_percent=0.5)
        assert result is not None
        assert result[0] == '61.8%'

    def test_is_near_fibonacci_level_miss(self):
        fib = calculate_fibonacci_retracement(110.0, 100.0)
        # Price far from any level
        result = is_near_fibonacci_level(107.5, fib, tolerance_percent=0.1)
        assert result is None

    def test_signal_strength_at_golden_ratio(self):
        fib = calculate_fibonacci_retracement(110.0, 100.0)
        # Exactly at 61.8% => diff_percent ~0 => strength 1.3
        strength = get_fibonacci_signal_strength(103.82, fib, tolerance_percent=1.0)
        assert strength >= 1.2

    def test_signal_strength_away_from_levels(self):
        fib = calculate_fibonacci_retracement(110.0, 100.0)
        strength = get_fibonacci_signal_strength(107.5, fib, tolerance_percent=0.1)
        assert strength == 1.0  # No bonus


# ---------------------------------------------------------------------------
# Linear regression slope & range percent
# ---------------------------------------------------------------------------

class TestMiscIndicators:
    """Tests for linear regression slope and range percent."""

    def test_slope_uptrend_positive(self):
        prices = [float(i) for i in range(20)]
        slope = calculate_linear_regression_slope(prices, period=14)
        assert slope is not None
        assert slope > 0

    def test_slope_downtrend_negative(self):
        prices = [float(100 - i) for i in range(20)]
        slope = calculate_linear_regression_slope(prices, period=14)
        assert slope is not None
        assert slope < 0

    def test_slope_flat_near_zero(self):
        prices = [100.0] * 20
        slope = calculate_linear_regression_slope(prices, period=14)
        assert slope == pytest.approx(0.0)

    def test_slope_insufficient_data(self):
        assert calculate_linear_regression_slope([1.0], period=14) is None

    def test_range_percent(self):
        # High=110, Low=100 => 10/100*100 = 10%
        prices = [100.0, 105.0, 110.0, 102.0, 108.0]
        rp = calculate_range_percent(prices, period=5)
        assert rp == pytest.approx(10.0)

    def test_range_percent_insufficient(self):
        assert calculate_range_percent([1.0, 2.0], period=50) is None

    def test_range_percent_zero_low(self):
        prices = [0.0] * 5
        assert calculate_range_percent(prices, period=5) is None
