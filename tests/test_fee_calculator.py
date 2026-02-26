"""Tests for FeeCalculator."""
from __future__ import annotations

import pytest

from src.fee_calculator import FeeCalculator


@pytest.fixture
def calc():
    """Default Kraken taker fee tier."""
    return FeeCalculator(maker_fee=0.0016, taker_fee=0.0026)


def test_calculate_fee_taker(calc: FeeCalculator):
    # 0.26% of $10,000 = $26
    assert abs(calc.calculate_fee(10_000.0, is_maker=False) - 26.0) < 0.01


def test_calculate_fee_maker(calc: FeeCalculator):
    # 0.16% of $10,000 = $16
    assert abs(calc.calculate_fee(10_000.0, is_maker=True) - 16.0) < 0.01


def test_calculate_fee_zero_value(calc: FeeCalculator):
    assert calc.calculate_fee(0.0) == 0.0


def test_roundtrip_fee(calc: FeeCalculator):
    # 2 * 0.26% * $10,000 = $52
    assert abs(calc.calculate_roundtrip_fee(10_000.0, is_maker=False) - 52.0) < 0.01


def test_breakeven_percent(calc: FeeCalculator):
    # Taker: 2 * 0.26% = 0.52%
    assert abs(calc.get_breakeven_percent(is_maker=False) - 0.0052) < 1e-6
    # Maker: 2 * 0.16% = 0.32%
    assert abs(calc.get_breakeven_percent(is_maker=True) - 0.0032) < 1e-6


def test_is_profitable_above_breakeven(calc: FeeCalculator):
    # 1% gross profit, 0.52% fees => 0.48% net profit (profitable)
    profitable, net_pct = calc.is_profitable(100.0, 101.0, position_type='long')
    assert profitable is True
    assert net_pct > 0


def test_is_profitable_below_breakeven(calc: FeeCalculator):
    # 0.1% gross profit, 0.52% fees => -0.42% net (unprofitable)
    profitable, net_pct = calc.is_profitable(100.0, 100.1, position_type='long')
    assert profitable is False
    assert net_pct < 0


def test_is_profitable_short(calc: FeeCalculator):
    # Short: entry 100, exit 98 => 2% gross profit
    profitable, net_pct = calc.is_profitable(100.0, 98.0, position_type='short')
    assert profitable is True
    assert net_pct > 0.01  # Should be ~1.48%


def test_is_profitable_zero_entry(calc: FeeCalculator):
    """Zero entry price should not crash (division guard)."""
    profitable, net_pct = calc.is_profitable(0.0, 100.0, position_type='long')
    assert profitable is False or net_pct <= 0


def test_calculate_net_pnl(calc: FeeCalculator):
    gross, fees, net = calc.calculate_net_pnl(
        entry_price=100.0, exit_price=105.0, volume=10.0, position_type='long'
    )
    # gross = (105-100)*10 = 50
    assert abs(gross - 50.0) < 0.01
    # fees = taker on entry (100*10*0.0026=2.60) + taker on exit (105*10*0.0026=2.73)
    assert abs(fees - 5.33) < 0.01
    assert abs(net - (50.0 - 5.33)) < 0.01


def test_calculate_net_pnl_with_explicit_fees(calc: FeeCalculator):
    gross, fees, net = calc.calculate_net_pnl(
        entry_price=100.0, exit_price=110.0, volume=1.0,
        position_type='long', entry_fee=1.0, exit_fee=1.5
    )
    assert abs(gross - 10.0) < 0.01
    assert abs(fees - 2.5) < 0.01
    assert abs(net - 7.5) < 0.01


def test_estimate_min_target_price_long(calc: FeeCalculator):
    target = calc.estimate_min_target_price(100.0, position_type='long', min_profit_pct=0.005)
    # Need 0.5% + 0.52% = 1.02% move => 101.02
    assert abs(target - 101.02) < 0.01


def test_estimate_min_target_price_short(calc: FeeCalculator):
    target = calc.estimate_min_target_price(100.0, position_type='short', min_profit_pct=0.005)
    # Short: entry * (1 - 1.02%) = 98.98
    assert abs(target - 98.98) < 0.01


def test_fee_summary(calc: FeeCalculator):
    summary = calc.get_fee_summary(cumulative_fees=52.0, total_volume=10_000.0)
    assert abs(summary['avg_fee_percent'] - 0.52) < 0.01
    assert summary['maker_fee_percent'] == 0.16
    assert summary['taker_fee_percent'] == 0.26


def test_fee_summary_zero_volume(calc: FeeCalculator):
    """Zero volume should not crash (division guard)."""
    summary = calc.get_fee_summary(cumulative_fees=0.0, total_volume=0.0)
    assert summary['avg_fee_percent'] == 0.0
