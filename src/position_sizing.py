"""Position sizing utilities.

These helpers are intentionally pure (no API calls) so they can be unit tested.
"""

from __future__ import annotations


def equal_split_quote_allocation(
    quote_balance: float,
    num_coins: int,
    *,
    fee_buffer_pct: float = 1.0,
    exposure_pct: float = 100.0,
) -> float:
    """Compute per-coin quote allocation from a quote balance.

    This follows a simple rule:
      1) Limit capital used by `exposure_pct`.
      2) Reserve `fee_buffer_pct` of that for fees.
      3) Split the remainder evenly across `num_coins`.

    Returns a quote-currency amount (e.g., USD) per coin.
    """
    if quote_balance <= 0:
        return 0.0

    if num_coins <= 0:
        return 0.0

    # Clamp percentages to sensible ranges.
    exposure_pct = max(0.0, min(float(exposure_pct), 100.0))
    fee_buffer_pct = max(0.0, min(float(fee_buffer_pct), 100.0))

    if exposure_pct <= 0:
        return 0.0

    # If fee buffer is 100%, nothing remains for trading.
    if fee_buffer_pct >= 100.0:
        return 0.0

    usable_value = quote_balance * (exposure_pct / 100.0)
    usable_value *= (1.0 - (fee_buffer_pct / 100.0))

    if usable_value <= 0:
        return 0.0

    return usable_value / float(num_coins)
