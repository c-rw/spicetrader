from src.market_data import OHLCCache


class _FakeClient:
    def __init__(self, result):
        self._result = result

    def get_ohlc(self, pair: str, interval: int = 1, since=None):
        return self._result


def test_ohlc_cache_drops_last_uncommitted_candle():
    # Two candles + one "current" (uncommitted) candle. Cache should drop the last.
    result = {
        'XXBTZUSD': [
            [100, '1', '2', '0.5', '1.5', '1.4', '10', 1],
            [200, '1.5', '2.5', '1.0', '2.0', '1.9', '12', 2],
            [300, '2.0', '3.0', '1.5', '2.5', '2.4', '50', 3],
        ],
        'last': 300,
    }
    cache = OHLCCache(interval=1, maxlen=10)
    cache.update(_FakeClient(result), 'XBTUSD')

    series = cache.get_series('XBTUSD')
    assert series is not None
    assert series['closes'] == [1.5, 2.0]
    assert series['highs'] == [2.0, 2.5]
    assert series['lows'] == [0.5, 1.0]
    assert series['volumes'] == [10.0, 12.0]
    assert series['latest']['time'] == 200


def test_ohlc_cache_merges_by_timestamp():
    first = {
        'XXBTZUSD': [
            [100, '1', '2', '0.5', '1.5', '1.4', '10', 1],
            [200, '1.5', '2.5', '1.0', '2.0', '1.9', '12', 2],
            [300, '2.0', '3.0', '1.5', '2.5', '2.4', '50', 3],
        ],
        'last': 300,
    }
    # Second fetch includes an updated candle at t=200 and a new candle at t=400,
    # plus a "current" uncommitted last candle that should be dropped.
    second = {
        'XXBTZUSD': [
            [200, '1.6', '2.6', '1.1', '2.1', '2.0', '13', 2],
            [400, '2.1', '3.1', '1.6', '2.6', '2.5', '14', 4],
            [500, '2.6', '3.6', '2.1', '3.1', '3.0', '99', 5],
        ],
        'last': 500,
    }

    cache = OHLCCache(interval=1, maxlen=10)
    cache.update(_FakeClient(first), 'XBTUSD')
    cache.update(_FakeClient(second), 'XBTUSD')

    series = cache.get_series('XBTUSD')
    assert series is not None
    # Expect candles at 100, 200(updated), 400; and 500 dropped.
    assert [series['latest']['time']] == [400]
    assert series['closes'] == [1.5, 2.1, 2.6]
