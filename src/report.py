"""Trading performance reporting utility."""
import sys
from datetime import datetime, timedelta
from database import TradingDatabase


def print_daily_summary(db: TradingDatabase, date: str = None):
    """Print daily trading summary."""
    if date is None:
        date = datetime.now().date()

    stats = db.get_daily_stats(date)

    print("\n" + "=" * 80)
    print(f"DAILY SUMMARY - {date}")
    print("=" * 80)
    print(f"Total Trades: {stats.get('total_trades', 0)}")
    print(f"Winning Trades: {stats.get('winning_trades', 0)}")

    if stats.get('total_trades', 0) > 0:
        win_rate = (stats['winning_trades'] / stats['total_trades']) * 100
        print(f"Win Rate: {win_rate:.1f}%")

    print(f"\nGross P&L: ${stats.get('gross_pnl', 0):.2f}")
    print(f"Total Fees: ${stats.get('total_fees', 0):.2f}")
    print(f"Net P&L: ${stats.get('net_pnl', 0):.2f}")

    print(f"\nStrategy Switches: {stats.get('strategy_switches', 0)}")

    if stats.get('coins_traded'):
        print(f"Coins Traded: {stats['coins_traded']}")

    print("=" * 80)


def print_strategy_performance(db: TradingDatabase, symbol: str, strategy: str):
    """Print performance for a specific strategy."""
    stats = db.get_strategy_performance(symbol, strategy)

    print("\n" + "=" * 80)
    print(f"STRATEGY PERFORMANCE - {symbol} - {strategy.upper()}")
    print("=" * 80)
    print(f"Total Trades: {stats.get('total_trades', 0)}")
    print(f"Winning Trades: {stats.get('winning_trades', 0)}")
    print(f"Losing Trades: {stats.get('losing_trades', 0)}")
    print(f"Win Rate: {stats.get('win_rate', 0):.1f}%")

    print(f"\nGross P&L: ${stats.get('gross_pnl', 0):.2f}")
    print(f"Total Fees: ${stats.get('total_fees', 0):.2f}")
    print(f"Net P&L: ${stats.get('net_pnl', 0):.2f}")

    print(f"\nAvg Win: ${stats.get('avg_win', 0):.2f}")
    print(f"Avg Loss: ${stats.get('avg_loss', 0):.2f}")
    print(f"Profit Factor: {stats.get('profit_factor', 0):.2f}")

    print("=" * 80)


def print_recent_trades(db: TradingDatabase, limit: int = 10):
    """Print recent trades."""
    cursor = db.conn.cursor()
    cursor.execute("""
        SELECT
            timestamp,
            symbol,
            strategy,
            trade_type,
            side,
            price,
            volume,
            fee,
            value
        FROM trades
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,))

    trades = cursor.fetchall()

    print("\n" + "=" * 80)
    print(f"RECENT TRADES (Last {limit})")
    print("=" * 80)
    print(f"{'Time':<20} {'Symbol':<10} {'Type':<6} {'Side':<5} {'Price':<12} {'Volume':<10} {'Fee':<8}")
    print("-" * 80)

    for trade in trades:
        trade_dict = dict(trade)
        print(
            f"{trade_dict['timestamp'][:19]:<20} "
            f"{trade_dict['symbol']:<10} "
            f"{trade_dict['trade_type']:<6} "
            f"{trade_dict['side']:<5} "
            f"${trade_dict['price']:<11,.2f} "
            f"{trade_dict['volume']:<10.6f} "
            f"${trade_dict['fee']:<7.2f}"
        )

    print("=" * 80)


def print_open_positions(db: TradingDatabase):
    """Print currently open positions."""
    cursor = db.conn.cursor()
    cursor.execute("""
        SELECT
            symbol,
            strategy,
            position_type,
            entry_time,
            entry_price,
            entry_volume,
            entry_fee
        FROM positions
        WHERE status = 'open'
        ORDER BY entry_time DESC
    """)

    positions = cursor.fetchall()

    print("\n" + "=" * 80)
    print("OPEN POSITIONS")
    print("=" * 80)

    if not positions:
        print("No open positions")
    else:
        print(f"{'Symbol':<10} {'Strategy':<15} {'Type':<6} {'Entry Time':<20} {'Entry Price':<12} {'Volume':<10}")
        print("-" * 80)

        for pos in positions:
            pos_dict = dict(pos)
            print(
                f"{pos_dict['symbol']:<10} "
                f"{pos_dict['strategy']:<15} "
                f"{pos_dict['position_type']:<6} "
                f"{pos_dict['entry_time'][:19]:<20} "
                f"${pos_dict['entry_price']:<11,.2f} "
                f"{pos_dict['entry_volume']:<10.6f}"
            )

    print("=" * 80)


def print_all_positions(db: TradingDatabase, limit: int = 20):
    """Print recent closed positions with P&L."""
    cursor = db.conn.cursor()
    cursor.execute("""
        SELECT
            symbol,
            strategy,
            position_type,
            entry_price,
            exit_price,
            gross_pnl,
            total_fees,
            net_pnl,
            pnl_percent,
            closed_time
        FROM positions
        WHERE status = 'closed'
        ORDER BY closed_time DESC
        LIMIT ?
    """, (limit,))

    positions = cursor.fetchall()

    print("\n" + "=" * 80)
    print(f"CLOSED POSITIONS (Last {limit})")
    print("=" * 80)
    print(f"{'Symbol':<10} {'Strategy':<12} {'Type':<6} {'Entry':<10} {'Exit':<10} {'Gross':<10} {'Fees':<8} {'Net P&L':<10} {'%':<8}")
    print("-" * 80)

    for pos in positions:
        pos_dict = dict(pos)
        pnl_color = "+" if pos_dict.get('net_pnl', 0) > 0 else "-"
        print(
            f"{pos_dict['symbol']:<10} "
            f"{pos_dict['strategy']:<12} "
            f"{pos_dict['position_type']:<6} "
            f"${pos_dict['entry_price']:<9,.2f} "
            f"${pos_dict['exit_price']:<9,.2f} "
            f"${pos_dict['gross_pnl']:<9.2f} "
            f"${pos_dict['total_fees']:<7.2f} "
            f"{pnl_color}${abs(pos_dict['net_pnl']):<9.2f} "
            f"{pos_dict['pnl_percent']:<7.2f}%"
        )

    print("=" * 80)


def main():
    """Main reporting function."""
    db = TradingDatabase()

    print("\n" + "=" * 80)
    print("SPICETRADER PERFORMANCE REPORT")
    print("=" * 80)

    # Print today's summary
    print_daily_summary(db)

    # Print open positions
    print_open_positions(db)

    # Print recent closed positions
    print_all_positions(db, limit=10)

    # Print recent trades
    print_recent_trades(db, limit=15)

    db.close()


if __name__ == '__main__':
    main()
