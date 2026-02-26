"""Tests for the base-class stop-loss mechanism (TradingStrategy).

Covers:
- check_stop_loss() trigger conditions
- _peek_price() extraction from various market_data formats
- set_entry_price / clear_entry_price lifecycle
- Interaction with position state
- Disabled stop-loss (missing / zero config)
"""
from __future__ import annotations

from typing import Optional, Dict, Any

import pytest

from src.strategies.base import TradingStrategy


# ---------------------------------------------------------------------------
# Concrete subclass for testing (ABC can't be instantiated directly)
# ---------------------------------------------------------------------------

class _StubStrategy(TradingStrategy):
    """Minimal concrete strategy for testing base-class behaviour."""

    def analyze(self, market_data: Dict[str, Any]) -> Optional[str]:
        # Delegate entirely to stop-loss check for test purposes
        price = self._peek_price(market_data)
        if price is not None:
            sl = self.check_stop_loss(price)
            if sl:
                return sl
        return None

    def get_strategy_name(self) -> str:
        return "stub"


def _make_config(stop_loss_pct: Optional[str] = "5.0", history_size: str = "100") -> dict:
    """Build a minimal config dict for _StubStrategy."""
    cfg = {"HISTORY_SIZE": history_size}
    if stop_loss_pct is not None:
        cfg["STOP_LOSS_PERCENTAGE"] = stop_loss_pct
    return cfg


# ---------------------------------------------------------------------------
# check_stop_loss
# ---------------------------------------------------------------------------

class TestCheckStopLoss:
    """Tests for check_stop_loss()."""

    def test_triggers_at_threshold(self):
        """Exact threshold breach should trigger sell."""
        s = _StubStrategy(_make_config("5.0"))
        s.position = "long"
        s.set_entry_price(100.0)
        # 5% loss: current = 95.0
        assert s.check_stop_loss(95.0) == "sell"

    def test_triggers_below_threshold(self):
        """Loss greater than threshold triggers sell."""
        s = _StubStrategy(_make_config("2.0"))
        s.position = "long"
        s.set_entry_price(100.0)
        assert s.check_stop_loss(90.0) == "sell"  # 10% > 2%

    def test_no_trigger_above_threshold(self):
        """Small loss should NOT trigger."""
        s = _StubStrategy(_make_config("5.0"))
        s.position = "long"
        s.set_entry_price(100.0)
        assert s.check_stop_loss(96.0) is None  # 4% < 5%

    def test_no_trigger_when_price_rises(self):
        """Price above entry => no loss => no trigger."""
        s = _StubStrategy(_make_config("2.0"))
        s.position = "long"
        s.set_entry_price(100.0)
        assert s.check_stop_loss(110.0) is None

    def test_no_trigger_without_position(self):
        """No open position => never trigger."""
        s = _StubStrategy(_make_config("2.0"))
        s.position = None
        s.set_entry_price(100.0)
        assert s.check_stop_loss(50.0) is None

    def test_no_trigger_for_short_position(self):
        """Stop-loss only applies to long positions in current implementation."""
        s = _StubStrategy(_make_config("2.0"))
        s.position = "short"
        s.set_entry_price(100.0)
        assert s.check_stop_loss(50.0) is None

    def test_no_trigger_without_entry_price(self):
        """Missing entry price => can't compute loss => no trigger."""
        s = _StubStrategy(_make_config("2.0"))
        s.position = "long"
        assert s.check_stop_loss(50.0) is None

    def test_clears_entry_price_on_trigger(self):
        """After triggering, entry_price should be cleared."""
        s = _StubStrategy(_make_config("2.0"))
        s.position = "long"
        s.set_entry_price(100.0)
        s.check_stop_loss(90.0)
        assert s.entry_price is None

    def test_disabled_when_pct_is_zero(self):
        """STOP_LOSS_PERCENTAGE=0 disables the stop-loss."""
        s = _StubStrategy(_make_config("0"))
        s.position = "long"
        s.set_entry_price(100.0)
        assert s.check_stop_loss(1.0) is None  # 99% loss, but disabled

    def test_disabled_when_key_missing(self):
        """Missing STOP_LOSS_PERCENTAGE key disables the stop-loss."""
        s = _StubStrategy(_make_config(stop_loss_pct=None))
        s.position = "long"
        s.set_entry_price(100.0)
        assert s.check_stop_loss(1.0) is None

    def test_zero_current_price_no_trigger(self):
        """Zero current price should not trigger (guard: current_price > 0)."""
        s = _StubStrategy(_make_config("2.0"))
        s.position = "long"
        s.set_entry_price(100.0)
        assert s.check_stop_loss(0.0) is None


# ---------------------------------------------------------------------------
# _peek_price — extract price from market_data
# ---------------------------------------------------------------------------

class TestPeekPrice:
    """Tests for _peek_price()."""

    def test_ohlc_latest_close(self):
        s = _StubStrategy(_make_config())
        data = {"ohlc": {"latest": {"close": "42000.5"}}}
        assert s._peek_price(data) == pytest.approx(42000.5)

    def test_ohlc_closes_list(self):
        s = _StubStrategy(_make_config())
        data = {"ohlc": {"closes": [100.0, 200.0, 300.0]}}
        assert s._peek_price(data) == pytest.approx(300.0)

    def test_ticker_fallback(self):
        s = _StubStrategy(_make_config())
        data = {"ticker": {"XXBTZUSD": {"c": ["42000.0", "0.1"]}}}
        assert s._peek_price(data) == pytest.approx(42000.0)

    def test_empty_market_data(self):
        s = _StubStrategy(_make_config())
        assert s._peek_price({}) is None

    def test_ohlc_takes_priority_over_ticker(self):
        s = _StubStrategy(_make_config())
        data = {
            "ohlc": {"latest": {"close": "100.0"}},
            "ticker": {"XXBTZUSD": {"c": ["200.0", "0.1"]}},
        }
        assert s._peek_price(data) == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Entry price lifecycle
# ---------------------------------------------------------------------------

class TestEntryPriceLifecycle:
    """Tests for set_entry_price / clear_entry_price."""

    def test_set_and_clear(self):
        s = _StubStrategy(_make_config())
        assert s.entry_price is None
        s.set_entry_price(50000.0)
        assert s.entry_price == 50000.0
        s.clear_entry_price()
        assert s.entry_price is None

    def test_reset_clears_entry_price(self):
        s = _StubStrategy(_make_config())
        s.set_entry_price(100.0)
        s.position = "long"
        s.reset()
        assert s.entry_price is None
        assert s.position is None


# ---------------------------------------------------------------------------
# Integration: analyze() with stop-loss
# ---------------------------------------------------------------------------

class TestAnalyzeWithStopLoss:
    """Integration: _StubStrategy.analyze() should trigger stop-loss via _peek_price."""

    def test_sell_signal_on_stop_loss(self):
        s = _StubStrategy(_make_config("3.0"))
        s.position = "long"
        s.set_entry_price(100.0)
        data = {"ohlc": {"latest": {"close": "90.0"}}}
        assert s.analyze(data) == "sell"

    def test_no_signal_when_price_ok(self):
        s = _StubStrategy(_make_config("3.0"))
        s.position = "long"
        s.set_entry_price(100.0)
        data = {"ohlc": {"latest": {"close": "99.0"}}}
        assert s.analyze(data) is None
