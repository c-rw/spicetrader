import pytest


from src.kraken.client import KrakenClient


def test_normalize_order_rounds_volume_and_price_down():
    rules = {
        'lot_decimals': 4,
        'pair_decimals': 2,
        'tick_size': '0.05',
        'ordermin': '0.0100',
        'costmin': '10',
    }

    vol, px = KrakenClient.normalize_order_with_rules(
        rules,
        ordertype='limit',
        volume=0.10099,
        price=100.03,
        current_price=100.03,
    )

    assert vol == 0.1009
    # 100.03 floored to tick size 0.05 => 100.00, then to 2 decimals.
    assert px == 100.0


def test_normalize_order_enforces_ordermin():
    rules = {
        'lot_decimals': 3,
        'pair_decimals': 2,
        'ordermin': '0.100',
    }

    with pytest.raises(ValueError, match="below ordermin"):
        KrakenClient.normalize_order_with_rules(
            rules,
            ordertype='market',
            volume=0.0999,
            price=None,
            current_price=100.0,
        )


def test_normalize_order_enforces_costmin_when_price_known():
    rules = {
        'lot_decimals': 4,
        'pair_decimals': 2,
        'costmin': '10',
    }

    with pytest.raises(ValueError, match="below costmin"):
        KrakenClient.normalize_order_with_rules(
            rules,
            ordertype='limit',
            volume=0.05,
            price=100.0,
            current_price=100.0,
        )
