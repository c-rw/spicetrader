from __future__ import annotations

from typing import Dict, List

from src.strategies.sma_crossover import SMACrossoverStrategy
from src.strategies.macd import MACDStrategy
from src.strategies.mean_reversion import MeanReversionStrategy
from src.indicators import calculate_macd


def _make_ohlc(closes: List[float]) -> Dict[str, object]:
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    volumes = [1.0 for _ in closes]
    return {
        'interval': 1,
        'highs': highs,
        'lows': lows,
        'closes': list(closes),
        'volumes': volumes,
        'latest': {
            'time': len(closes),
            'open': closes[-1],
            'high': highs[-1],
            'low': lows[-1],
            'close': closes[-1],
            'vwap': closes[-1],
            'volume': volumes[-1],
            'count': 1,
        },
    }


def test_sma_crossover_uses_ohlc_and_emits_buy_on_bullish_cross():
    config = {
        'FAST_SMA_PERIOD': 3,
        'SLOW_SMA_PERIOD': 5,
        'ENABLE_TREND_FILTER': 'false',
        'MIN_HOLD_TIME': 0,
        'MIN_PROFIT_TARGET': 0.0,
    }
    strat = SMACrossoverStrategy(config)

    series1 = [10, 10, 10, 10, 10]
    series2 = [10, 10, 10, 10, 10, 12]

    assert strat.analyze({'ohlc': _make_ohlc(series1), 'ticker': {}}) is None
    assert strat.analyze({'ohlc': _make_ohlc(series2), 'ticker': {}}) == 'buy'


def test_macd_uses_ohlc_and_emits_buy_on_bullish_cross():
    config = {
        'MACD_FAST': 3,
        'MACD_SLOW': 6,
        'MACD_SIGNAL': 3,
        'MACD_HISTOGRAM_CONFIRM': 'false',
    }
    strat = MACDStrategy(config)

    base = [10, 9, 8, 7, 6, 5, 4, 3, 2]  # len == slow + signal (9)

    prev = calculate_macd(base, 3, 6, 3)
    assert prev is not None
    prev_macd, prev_signal, _ = prev

    # Extend the series until we force a bullish crossover (macd crosses above signal).
    series2 = list(base)
    for _ in range(1, 60):
        series2.append(series2[-1] + 5)
        cur = calculate_macd(series2, 3, 6, 3)
        if cur is None:
            continue
        cur_macd, cur_signal, _ = cur
        if prev_macd <= prev_signal and cur_macd > cur_signal:
            break
    else:
        raise AssertionError('Failed to construct a bullish MACD crossover series')

    assert strat.analyze({'ohlc': _make_ohlc(base), 'ticker': {}}) is None
    assert strat.analyze({'ohlc': _make_ohlc(series2), 'ticker': {}}) == 'buy'


def test_mean_reversion_uses_ohlc_and_emits_buy_near_support():
    config = {
        'RSI_PERIOD': 5,
        'RSI_OVERSOLD': 80,
        'RSI_OVERBOUGHT': 90,
        'BB_PERIOD': 5,
        'BB_STD_DEV': 0.5,
        'AUTO_DETECT_LEVELS': 'false',
        'USE_FIBONACCI': 'false',
        'SUPPORT_LEVEL': 85,
        'RESISTANCE_LEVEL': 110,
        'SUPPORT_ZONE': 5,
        'RESISTANCE_ZONE': 5,
        'BREAKOUT_LOWER': 0,
        'BREAKOUT_UPPER': 1_000_000,
        'MIN_PROFIT_TARGET': 0.0,
    }

    strat = MeanReversionStrategy(config)

    # Flat then sharp dip: should be below lower BB, RSI low, and within support zone.
    closes = [100, 100, 100, 100, 85, 85]

    signal = strat.analyze({'ohlc': _make_ohlc(closes), 'ticker': {}})
    assert signal == 'buy'
