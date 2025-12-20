#!/usr/bin/env python3
"""Dry-run smoke test (no network, no infinite loops).

Runs a few iterations of both bots using a fully mocked Kraken client.
This is meant as a quick sanity check after refactors.

Usage:
    ./.venv/bin/python -m scripts.smoke_dry_run
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from src.adaptive_bot import AdaptiveBot
from src.multi_coin_bot import MultiCoinBot


class FakeKrakenClient:
    def __init__(self, *, starting_price: float = 100.0):
        self._starting_price = float(starting_price)
        self._ticks: Dict[str, int] = {}

    def get_server_time(self) -> Dict[str, Any]:
        return {"unixtime": int(time.time())}

    def get_account_balance(self) -> Dict[str, Any]:
        return {"ZUSD": "1000.0"}

    def get_trade_balance(self, asset: str = "ZUSD") -> Dict[str, Any]:
        return {"eb": "1000.0"}

    def get_order_book(self, pair: str, count: int = 10) -> Dict[str, Any]:
        return {"pair": pair, "asks": [], "bids": []}

    def get_ticker(self, pair: str) -> Dict[str, Any]:
        pairs = [p.strip() for p in pair.split(",")]
        out: Dict[str, Any] = {}
        for p in pairs:
            tick = self._ticks.get(p, 0)
            price = self._starting_price + tick * 1.0
            self._ticks[p] = tick + 1
            out[p] = {
                "c": [str(price), "1"],
                "h": [str(price * 1.01)],
                "l": [str(price * 0.99)],
                "v": ["1", "10"],
            }
        return out

    def get_ohlc(self, pair: str, interval: int = 1, since: Optional[int] = None) -> Dict[str, Any]:
        tick = self._ticks.get(pair, 0)
        base = self._starting_price + max(0, tick - 20) * 1.0

        # Produce 15 committed candles + 1 uncommitted (last) candle.
        rows: List[List[Any]] = []
        t0 = 1_000
        for i in range(0, 16):
            close = base + i
            open_ = close - 0.5
            high = close + 0.8
            low = close - 0.9
            vwap = close
            volume = 10 + i
            count = 1
            rows.append([t0 + i * interval * 60, str(open_), str(high), str(low), str(close), str(vwap), str(volume), count])

        last = rows[-1][0]
        return {pair: rows, "last": last}

    # The following are only used in live trading; present to make accidental
    # calls obvious.
    def add_order(self, *args, **kwargs):
        raise AssertionError("add_order should not be called in dry-run smoke")

    def normalize_order(self, *args, **kwargs):
        raise AssertionError("normalize_order should not be called in dry-run smoke")

    def get_trade_actual_fee(self, *args, **kwargs) -> float:
        return 0.0


def _run_adaptive_smoke() -> None:
    config = {
        "TRADING_PAIR": "XBTUSD",
        "ORDER_SIZE": 0.001,
        "DRY_RUN": "true",
        "API_CALL_DELAY": 0,
        "OHLC_INTERVAL": 1,
        # Make analysis kick in quickly.
        "RANGE_PERIOD": 10,
        "ADX_PERIOD": 3,
        "REANALYSIS_INTERVAL": 0,
        "SWITCH_COOLDOWN": 0,
        "CONFIRMATIONS_REQUIRED": 1,
        "MAX_SWITCHES_PER_DAY": 999,
    }

    bot = AdaptiveBot("key", "secret", config)
    bot.client = FakeKrakenClient(starting_price=100.0)

    # Run enough iterations to pass the analyzer's minimum data requirement.
    for _ in range(15):
        bot.run_strategy()


def _run_multi_coin_smoke() -> None:
    config = {
        "TRADING_PAIRS": "XBTUSD,ETHUSD",
        "DRY_RUN": "true",
        "API_CALL_DELAY": 0,
        "OHLC_INTERVAL": 1,
        # Make analysis kick in quickly.
        "RANGE_PERIOD": 10,
        "ADX_PERIOD": 3,
        "REANALYSIS_INTERVAL": 0,
        "SWITCH_COOLDOWN": 0,
        "CONFIRMATIONS_REQUIRED": 1,
        "MAX_SWITCHES_PER_DAY": 999,
        "MAX_TOTAL_EXPOSURE": 75,
        "MAX_PER_COIN": 25,
    }

    bot = MultiCoinBot("key", "secret", config)
    bot.client = FakeKrakenClient(starting_price=200.0)

    for _ in range(10):
        bot.run_iteration()


def main() -> None:
    _run_adaptive_smoke()
    _run_multi_coin_smoke()
    print("smoke_dry_run: OK")


if __name__ == "__main__":
    main()
