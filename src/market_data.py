"""Market data helpers (OHLC cache and parsing)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class OHLCCandle:
    time: int
    open: float
    high: float
    low: float
    close: float
    vwap: float
    volume: float
    count: int


def _find_ohlc_pair_key(ohlc_result: Dict[str, Any]) -> Optional[str]:
    for key in ohlc_result.keys():
        if key != 'last':
            return key
    return None


def _parse_ohlc_rows(rows: List[List[Any]]) -> List[OHLCCandle]:
    candles: List[OHLCCandle] = []
    for row in rows:
        if len(row) < 8:
            continue
        candles.append(
            OHLCCandle(
                time=int(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                vwap=float(row[5]),
                volume=float(row[6]),
                count=int(row[7]),
            )
        )
    return candles


class OHLCCache:
    """Caches committed OHLC candles per trading pair.

    Kraken's OHLC endpoint includes a final "current" (not-yet-committed) candle.
    This cache always drops that last candle when present.
    """

    def __init__(self, interval: int = 1, maxlen: int = 200):
        self.interval = interval
        self.maxlen = maxlen
        self._since: Dict[str, int] = {}
        self._candles: Dict[str, Deque[OHLCCandle]] = {}

    def update(self, client: Any, pair: str) -> None:
        """Fetch and merge OHLC candles for pair."""
        since = self._since.get(pair)
        result = client.get_ohlc(pair, interval=self.interval, since=since)
        if not isinstance(result, dict) or not result:
            return

        pair_key = _find_ohlc_pair_key(result)
        if not pair_key:
            return

        rows = result.get(pair_key) or []
        candles = _parse_ohlc_rows(rows)

        # Kraken includes a final uncommitted candle; drop it when possible.
        if len(candles) >= 2:
            candles = candles[:-1]

        if not candles:
            # Still update since cursor if present.
            last_val = result.get('last')
            if last_val is not None:
                self._since[pair] = int(last_val)
            return

        dq = self._candles.get(pair)
        if dq is None:
            dq = deque(maxlen=self.maxlen)
            self._candles[pair] = dq

        last_ts = dq[-1].time if dq else None
        for candle in candles:
            if last_ts is None or candle.time > last_ts:
                dq.append(candle)
                last_ts = candle.time
            elif candle.time == last_ts:
                # Replace last candle if we got a newer version of same timestamp.
                dq.pop()
                dq.append(candle)

        last_val = result.get('last')
        if last_val is not None:
            self._since[pair] = int(last_val)

    def get_series(self, pair: str) -> Optional[Dict[str, Any]]:
        """Return series dict: highs/lows/closes/volumes + latest candle."""
        dq = self._candles.get(pair)
        if not dq:
            return None

        candles = list(dq)
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        volumes = [c.volume for c in candles]
        latest = candles[-1]

        return {
            'interval': self.interval,
            'highs': highs,
            'lows': lows,
            'closes': closes,
            'volumes': volumes,
            'latest': {
                'time': latest.time,
                'open': latest.open,
                'high': latest.high,
                'low': latest.low,
                'close': latest.close,
                'vwap': latest.vwap,
                'volume': latest.volume,
                'count': latest.count,
            },
        }

    def get_latest_committed(self, pair: str) -> Optional[OHLCCandle]:
        dq = self._candles.get(pair)
        if not dq:
            return None
        return dq[-1]
