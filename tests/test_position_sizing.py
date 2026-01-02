from src.position_sizing import equal_split_quote_allocation


def test_equal_split_quote_allocation_basic():
    # $1000 balance, reserve 1% for fees => $990 usable, 3 coins => $330 each
    assert equal_split_quote_allocation(1000.0, 3, fee_buffer_pct=1.0, exposure_pct=100.0) == 330.0


def test_equal_split_quote_allocation_respects_exposure_pct():
    # Use only 75% exposure, reserve 1% fees: 1000 * 0.75 * 0.99 = 742.5
    # 4 coins => 185.625 each
    assert equal_split_quote_allocation(1000.0, 4, fee_buffer_pct=1.0, exposure_pct=75.0) == 185.625


def test_equal_split_quote_allocation_guards():
    assert equal_split_quote_allocation(0.0, 4) == 0.0
    assert equal_split_quote_allocation(-10.0, 4) == 0.0
    assert equal_split_quote_allocation(100.0, 0) == 0.0
    assert equal_split_quote_allocation(100.0, -1) == 0.0
    assert equal_split_quote_allocation(100.0, 2, fee_buffer_pct=100.0) == 0.0
    assert equal_split_quote_allocation(100.0, 2, exposure_pct=0.0) == 0.0
