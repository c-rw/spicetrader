"""Fee Calculator - Kraken trading fee calculations and profitability checks."""
from typing import Tuple, Optional


class FeeCalculator:
    """
    Calculates trading fees and determines trade profitability.

    Kraken fee structure (default tiers):
    - Maker: 0.16% (limit orders that add liquidity)
    - Taker: 0.26% (market orders that remove liquidity)

    Volume tiers (30-day volume in USD):
    - <$50k: 0.16% maker, 0.26% taker
    - $50k-$100k: 0.14% maker, 0.24% taker
    - $100k-$250k: 0.12% maker, 0.22% taker
    """

    def __init__(self, maker_fee: float = 0.0016, taker_fee: float = 0.0026):
        """
        Initialize fee calculator.

        Args:
            maker_fee: Maker fee as decimal (0.0016 = 0.16%)
            taker_fee: Taker fee as decimal (0.0026 = 0.26%)
        """
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee

    def calculate_fee(self, trade_value: float, is_maker: bool = False) -> float:
        """
        Calculate fee for a trade.

        Args:
            trade_value: Total value of trade (price * volume)
            is_maker: True for limit orders (maker), False for market (taker)

        Returns:
            Fee amount in quote currency
        """
        fee_rate = self.maker_fee if is_maker else self.taker_fee
        return trade_value * fee_rate

    def calculate_roundtrip_fee(self, trade_value: float, is_maker: bool = False) -> float:
        """
        Calculate total fee for a round-trip (buy + sell).

        Args:
            trade_value: Total value of one side of trade
            is_maker: True for limit orders, False for market orders

        Returns:
            Total fee for both entry and exit
        """
        fee_rate = self.maker_fee if is_maker else self.taker_fee
        return 2 * trade_value * fee_rate

    def get_breakeven_percent(self, is_maker: bool = False) -> float:
        """
        Get minimum price movement needed to break even after fees.

        Args:
            is_maker: True for limit orders, False for market orders

        Returns:
            Breakeven percentage as decimal (e.g., 0.0052 = 0.52%)
        """
        fee_rate = self.maker_fee if is_maker else self.taker_fee
        return 2 * fee_rate  # Round-trip fee

    def is_profitable(
        self,
        entry_price: float,
        exit_price: float,
        position_type: str = 'long',
        is_maker: bool = False,
        min_profit_threshold: float = 0.0
    ) -> Tuple[bool, float]:
        """
        Check if a trade would be profitable after fees.

        Args:
            entry_price: Entry price
            exit_price: Exit price
            position_type: 'long' or 'short'
            is_maker: True for limit orders, False for market orders
            min_profit_threshold: Minimum profit % required (as decimal)

        Returns:
            Tuple of (is_profitable, net_profit_percent)
        """
        # Calculate gross profit %
        if position_type == 'long':
            gross_profit_pct = (exit_price - entry_price) / entry_price
        else:  # short
            gross_profit_pct = (entry_price - exit_price) / entry_price

        # Subtract fees
        fee_rate = self.maker_fee if is_maker else self.taker_fee
        net_profit_pct = gross_profit_pct - (2 * fee_rate)

        # Check against threshold
        is_profitable = net_profit_pct > min_profit_threshold

        return is_profitable, net_profit_pct

    def calculate_net_pnl(
        self,
        entry_price: float,
        exit_price: float,
        volume: float,
        position_type: str = 'long',
        entry_fee: Optional[float] = None,
        exit_fee: Optional[float] = None
    ) -> Tuple[float, float, float]:
        """
        Calculate net P&L after fees.

        Args:
            entry_price: Entry price
            exit_price: Exit price
            volume: Trade volume in base currency
            position_type: 'long' or 'short'
            entry_fee: Actual entry fee (if known), otherwise estimated
            exit_fee: Actual exit fee (if known), otherwise estimated

        Returns:
            Tuple of (gross_pnl, total_fees, net_pnl)
        """
        # Calculate gross P&L
        if position_type == 'long':
            gross_pnl = (exit_price - entry_price) * volume
        else:  # short
            gross_pnl = (entry_price - exit_price) * volume

        # Calculate fees (use actual if provided, otherwise estimate)
        if entry_fee is None:
            entry_fee = self.calculate_fee(entry_price * volume, is_maker=False)
        if exit_fee is None:
            exit_fee = self.calculate_fee(exit_price * volume, is_maker=False)

        total_fees = entry_fee + exit_fee
        net_pnl = gross_pnl - total_fees

        return gross_pnl, total_fees, net_pnl

    def estimate_min_target_price(
        self,
        entry_price: float,
        position_type: str = 'long',
        is_maker: bool = False,
        min_profit_pct: float = 0.005  # 0.5% minimum profit
    ) -> float:
        """
        Calculate minimum target price to achieve desired profit after fees.

        Args:
            entry_price: Entry price
            position_type: 'long' or 'short'
            is_maker: True for limit orders, False for market orders
            min_profit_pct: Desired net profit % (as decimal)

        Returns:
            Minimum target exit price
        """
        fee_rate = self.maker_fee if is_maker else self.taker_fee

        # Need: (exit - entry) / entry = min_profit_pct + 2*fee_rate
        required_move_pct = min_profit_pct + (2 * fee_rate)

        if position_type == 'long':
            # For long: exit = entry * (1 + required_move)
            return entry_price * (1 + required_move_pct)
        else:  # short
            # For short: exit = entry * (1 - required_move)
            return entry_price * (1 - required_move_pct)

    def get_fee_summary(self, cumulative_fees: float, total_volume: float) -> dict:
        """
        Get summary of fee statistics.

        Args:
            cumulative_fees: Total fees paid
            total_volume: Total trading volume

        Returns:
            Dictionary with fee statistics
        """
        avg_fee_pct = (cumulative_fees / total_volume * 100) if total_volume > 0 else 0

        return {
            'cumulative_fees': cumulative_fees,
            'total_volume': total_volume,
            'avg_fee_percent': avg_fee_pct,
            'maker_fee_percent': self.maker_fee * 100,
            'taker_fee_percent': self.taker_fee * 100,
            'breakeven_percent': self.get_breakeven_percent(is_maker=False) * 100
        }


def format_fee_summary(summary: dict) -> str:
    """
    Format fee summary for display.

    Args:
        summary: Dictionary from get_fee_summary()

    Returns:
        Formatted string
    """
    return (
        f"Cumulative Fees: ${summary['cumulative_fees']:.2f} | "
        f"Total Volume: ${summary['total_volume']:.2f} | "
        f"Avg Fee: {summary['avg_fee_percent']:.3f}% | "
        f"Breakeven: {summary['breakeven_percent']:.3f}%"
    )
