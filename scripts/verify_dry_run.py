#!/usr/bin/env python3
"""
Verification script for dry_run status in trading database.

This script checks the database to ensure trades are properly tagged
as dry run (test) or live trades.
"""
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

def connect_db(db_path='data/trading.db'):
    """Connect to trading database."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)

def print_section(title):
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def verify_trades(conn):
    """Verify trades table dry_run status."""
    print_section("TRADES TABLE - DRY RUN STATUS")

    cursor = conn.cursor()

    # Count by dry_run status
    cursor.execute("""
        SELECT
            dry_run,
            COUNT(*) as count,
            MIN(timestamp) as first_trade,
            MAX(timestamp) as last_trade
        FROM trades
        GROUP BY dry_run
        ORDER BY dry_run
    """)

    results = cursor.fetchall()

    if not results:
        print("No trades found in database.")
        return

    print("\nSummary:")
    print("-" * 80)
    for row in results:
        dry_run = "DRY RUN (Test)" if row['dry_run'] == 1 else "LIVE TRADING"
        print(f"{dry_run:20} | Count: {row['count']:4} | First: {row['first_trade']} | Last: {row['last_trade']}")

    # Recent trades
    print("\nRecent Trades (last 10):")
    print("-" * 80)
    cursor.execute("""
        SELECT
            id,
            timestamp,
            symbol,
            trade_type,
            side,
            price,
            volume,
            dry_run
        FROM trades
        ORDER BY timestamp DESC
        LIMIT 10
    """)

    trades = cursor.fetchall()

    if trades:
        print(f"{'ID':<5} {'Timestamp':<20} {'Symbol':<10} {'Type':<6} {'Side':<5} {'Price':>10} {'Volume':>10} {'Dry Run':<10}")
        print("-" * 80)
        for trade in trades:
            dry_run_label = "DRY RUN" if trade['dry_run'] == 1 else "LIVE"
            print(f"{trade['id']:<5} {trade['timestamp']:<20} {trade['symbol']:<10} {trade['trade_type']:<6} {trade['side']:<5} ${trade['price']:>9,.2f} {trade['volume']:>10.6f} {dry_run_label:<10}")
    else:
        print("No recent trades.")

def verify_positions(conn):
    """Verify positions table dry_run status."""
    print_section("POSITIONS TABLE - DRY RUN STATUS")

    cursor = conn.cursor()

    # Count by dry_run and status
    cursor.execute("""
        SELECT
            dry_run,
            status,
            COUNT(*) as count
        FROM positions
        GROUP BY dry_run, status
        ORDER BY dry_run, status
    """)

    results = cursor.fetchall()

    if not results:
        print("No positions found in database.")
        return

    print("\nSummary:")
    print("-" * 80)
    for row in results:
        dry_run = "DRY RUN (Test)" if row['dry_run'] == 1 else "LIVE TRADING"
        print(f"{dry_run:20} | Status: {row['status']:10} | Count: {row['count']:4}")

    # Recent positions
    print("\nRecent Positions (last 10):")
    print("-" * 80)
    cursor.execute("""
        SELECT
            id,
            symbol,
            strategy,
            position_type,
            entry_time,
            entry_price,
            exit_price,
            net_pnl,
            status,
            dry_run
        FROM positions
        ORDER BY entry_time DESC
        LIMIT 10
    """)

    positions = cursor.fetchall()

    if positions:
        print(f"{'ID':<5} {'Symbol':<10} {'Strategy':<15} {'Type':<6} {'Entry':<20} {'Entry $':>10} {'Exit $':>10} {'Net P&L':>10} {'Status':<8} {'Dry Run':<10}")
        print("-" * 80)
        for pos in positions:
            dry_run_label = "DRY RUN" if pos['dry_run'] == 1 else "LIVE"
            exit_price = f"${pos['exit_price']:,.2f}" if pos['exit_price'] else "N/A"
            net_pnl = f"${pos['net_pnl']:,.2f}" if pos['net_pnl'] else "N/A"
            print(f"{pos['id']:<5} {pos['symbol']:<10} {pos['strategy']:<15} {pos['position_type']:<6} {pos['entry_time']:<20} ${pos['entry_price']:>9,.2f} {exit_price:>10} {net_pnl:>10} {pos['status']:<8} {dry_run_label:<10}")
    else:
        print("No recent positions.")

def check_inconsistencies(conn):
    """Check for inconsistencies between trades and positions."""
    print_section("INCONSISTENCY CHECK")

    cursor = conn.cursor()

    # Check for mismatched dry_run values
    cursor.execute("""
        SELECT
            t.id as trade_id,
            t.dry_run as trade_dry_run,
            p.id as position_id,
            p.dry_run as position_dry_run,
            t.symbol,
            t.timestamp
        FROM trades t
        LEFT JOIN positions p ON t.position_id = p.id
        WHERE t.position_id IS NOT NULL
        AND t.dry_run != p.dry_run
    """)

    inconsistencies = cursor.fetchall()

    if inconsistencies:
        print(f"\n⚠️  WARNING: Found {len(inconsistencies)} inconsistencies!")
        print("-" * 80)
        print(f"{'Trade ID':<10} {'Trade DryRun':<15} {'Pos ID':<10} {'Pos DryRun':<15} {'Symbol':<10} {'Timestamp':<20}")
        print("-" * 80)
        for row in inconsistencies:
            print(f"{row['trade_id']:<10} {row['trade_dry_run']:<15} {row['position_id']:<10} {row['position_dry_run']:<15} {row['symbol']:<10} {row['timestamp']:<20}")
    else:
        print("\n✅ No inconsistencies found - all trades and positions have matching dry_run values!")

def print_queries(conn):
    """Print useful SQL queries for manual verification."""
    print_section("USEFUL SQL QUERIES")

    print("\nTo check all live trades:")
    print("  sqlite3 data/trading.db \"SELECT * FROM trades WHERE dry_run = 0;\"")

    print("\nTo check all dry run trades:")
    print("  sqlite3 data/trading.db \"SELECT * FROM trades WHERE dry_run = 1;\"")

    print("\nTo check live positions:")
    print("  sqlite3 data/trading.db \"SELECT * FROM positions WHERE dry_run = 0;\"")

    print("\nTo count trades by type:")
    print("  sqlite3 data/trading.db \"SELECT dry_run, COUNT(*) FROM trades GROUP BY dry_run;\"")

def main():
    """Main verification routine."""
    print("\n" + "🔍 DRY RUN VERIFICATION TOOL" .center(80))
    print("Trading Database Dry Run Status Checker".center(80))
    print("=" * 80)

    # Try different database paths
    db_paths = ['data/trading.db', 'trading.db', '../data/trading.db']
    conn = None

    for db_path in db_paths:
        if Path(db_path).exists():
            print(f"\n✅ Found database at: {db_path}")
            conn = connect_db(db_path)
            break

    if not conn:
        print(f"\n❌ Error: Could not find trading.db in any of these locations:")
        for path in db_paths:
            print(f"   - {path}")
        sys.exit(1)

    try:
        # Run verifications
        verify_trades(conn)
        verify_positions(conn)
        check_inconsistencies(conn)
        print_queries(conn)

        print("\n" + "=" * 80)
        print("Verification complete!".center(80))
        print("=" * 80 + "\n")

    finally:
        conn.close()

if __name__ == '__main__':
    main()
