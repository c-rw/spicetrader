"""Database module for tracking trades, performance, and analytics."""
import sqlite3
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class TradingDatabase:
    """
    SQLite database for tracking all trading activity.

    Stores:
    - Trade history with entry/exit prices and fees
    - Strategy performance metrics
    - Market conditions at time of trades
    - Daily/weekly/monthly statistics
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file (defaults to project_root/data/trading.db)
        """
        # Use absolute path relative to project root if not provided
        if db_path is None:
            project_root = Path(__file__).parent.parent
            db_path = str(project_root / 'data' / 'trading.db')

        # Ensure data directory exists
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        self.db_path = db_path
        self.conn = None
        self.connect()
        self.create_tables()

    def connect(self):
        """Create database connection."""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row  # Return rows as dictionaries
            logger.info(f"Connected to database: {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def create_tables(self):
        """Create database tables if they don't exist."""
        cursor = self.conn.cursor()

        # Trades table - individual trade records
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT NOT NULL,
                strategy TEXT NOT NULL,
                market_state TEXT,

                -- Trade details
                trade_type TEXT NOT NULL,  -- 'entry' or 'exit'
                position_type TEXT,  -- 'long' or 'short'
                side TEXT NOT NULL,  -- 'buy' or 'sell'

                -- Pricing
                price REAL NOT NULL,
                volume REAL NOT NULL,
                value REAL NOT NULL,  -- price * volume

                -- Fees
                fee REAL DEFAULT 0.0,
                fee_currency TEXT DEFAULT 'USD',

                -- References
                position_id INTEGER,  -- Links entry/exit trades
                txid TEXT,  -- Kraken transaction ID

                -- Metadata
                dry_run BOOLEAN DEFAULT 1,
                notes TEXT
            )
        """)

        # Positions table - completed trades with P&L
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                strategy TEXT NOT NULL,
                market_state TEXT,
                position_type TEXT NOT NULL,  -- 'long' or 'short'

                -- Entry
                entry_time DATETIME NOT NULL,
                entry_price REAL NOT NULL,
                entry_volume REAL NOT NULL,
                entry_fee REAL DEFAULT 0.0,

                -- Exit
                exit_time DATETIME,
                exit_price REAL,
                exit_volume REAL,
                exit_fee REAL DEFAULT 0.0,

                -- P&L
                gross_pnl REAL,
                total_fees REAL,
                net_pnl REAL,
                pnl_percent REAL,

                -- Status
                status TEXT DEFAULT 'open',  -- 'open', 'closed', 'cancelled'

                -- Metadata
                dry_run BOOLEAN DEFAULT 1,
                closed_time DATETIME
            )
        """)

        # Strategy performance table - aggregated stats per strategy
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                strategy TEXT NOT NULL,
                date DATE NOT NULL,

                -- Trade counts
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,

                -- P&L
                gross_pnl REAL DEFAULT 0.0,
                total_fees REAL DEFAULT 0.0,
                net_pnl REAL DEFAULT 0.0,

                -- Metrics
                win_rate REAL DEFAULT 0.0,
                avg_profit REAL DEFAULT 0.0,
                avg_loss REAL DEFAULT 0.0,
                profit_factor REAL DEFAULT 0.0,

                -- Volume
                total_volume REAL DEFAULT 0.0,

                UNIQUE(symbol, strategy, date)
            )
        """)

        # Market conditions table - track market state at time of decisions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_conditions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT NOT NULL,

                -- Market metrics
                state TEXT NOT NULL,
                adx REAL,
                atr REAL,
                range_percent REAL,
                choppiness REAL,
                slope REAL,
                confidence REAL,

                -- Price info
                price REAL,
                volume REAL,

                -- Selected strategy
                recommended_strategy TEXT,
                active_strategy TEXT
            )
        """)

        # Strategy switches table - track when and why strategies changed
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_switches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT NOT NULL,

                -- Switch details
                from_strategy TEXT NOT NULL,
                to_strategy TEXT NOT NULL,
                reason TEXT,

                -- Market context
                market_state TEXT,
                confidence REAL,

                -- Switch metrics
                confirmations_received INTEGER,
                switches_today INTEGER,

                -- Performance before switch
                trades_with_old_strategy INTEGER,
                pnl_with_old_strategy REAL
            )
        """)

        # Daily summary table - overall performance per day
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL UNIQUE,

                -- Trade counts
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,

                -- P&L
                gross_pnl REAL DEFAULT 0.0,
                total_fees REAL DEFAULT 0.0,
                net_pnl REAL DEFAULT 0.0,

                -- Account
                starting_balance REAL,
                ending_balance REAL,

                -- Strategy switches
                total_switches INTEGER DEFAULT 0,

                -- Active coins
                coins_traded TEXT
            )
        """)

        # Create indexes for performance
        # Single column indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_conditions_symbol ON market_conditions(symbol)")

        # Composite indexes for common queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol_strategy ON trades(symbol, strategy)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol_timestamp ON trades(symbol, timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_symbol_strategy ON positions(symbol, strategy)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_symbol_status ON positions(symbol, status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_conditions_symbol_timestamp ON market_conditions(symbol, timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_strategy_perf_symbol_strategy ON strategy_performance(symbol, strategy)")

        self.conn.commit()
        logger.info("Database tables created/verified")

    def record_trade(
        self,
        symbol: str,
        strategy: str,
        trade_type: str,
        side: str,
        price: float,
        volume: float,
        fee: float = 0.0,
        position_type: Optional[str] = None,
        market_state: Optional[str] = None,
        position_id: Optional[int] = None,
        txid: Optional[str] = None,
        dry_run: bool = True
    ) -> int:
        """
        Record a trade in the database.

        Args:
            symbol: Trading pair
            strategy: Strategy name
            trade_type: 'entry' or 'exit'
            side: 'buy' or 'sell'
            price: Trade price
            volume: Trade volume
            fee: Fee paid
            position_type: 'long' or 'short'
            market_state: Market condition at time of trade
            position_id: ID of associated position
            txid: Kraken transaction ID
            dry_run: Whether this is a dry run trade

        Returns:
            Trade ID
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO trades (
                symbol, strategy, trade_type, position_type, side,
                price, volume, value, fee, fee_currency,
                position_id, market_state, txid, dry_run
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol, strategy, trade_type, position_type, side,
            price, volume, price * volume, fee, 'USD',
            position_id, market_state, txid, dry_run
        ))
        self.conn.commit()
        trade_id = cursor.lastrowid
        dry_run_label = "dry_run=True (TEST)" if dry_run else "dry_run=False (LIVE)"
        logger.debug(f"Recorded trade {trade_id} for {symbol}: {trade_type} {side} @ ${price:,.2f} ({dry_run_label})")
        return trade_id

    def open_position(
        self,
        symbol: str,
        strategy: str,
        position_type: str,
        entry_price: float,
        entry_volume: float,
        entry_fee: float = 0.0,
        market_state: Optional[str] = None,
        dry_run: bool = True
    ) -> int:
        """
        Open a new position.

        Returns:
            Position ID
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO positions (
                symbol, strategy, position_type, market_state,
                entry_time, entry_price, entry_volume, entry_fee,
                status, dry_run
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
        """, (
            symbol, strategy, position_type, market_state,
            datetime.now(), entry_price, entry_volume, entry_fee, dry_run
        ))
        self.conn.commit()
        position_id = cursor.lastrowid
        dry_run_label = "dry_run=True (TEST)" if dry_run else "dry_run=False (LIVE)"
        logger.info(f"Opened position {position_id} for {symbol}: {position_type} @ ${entry_price:,.2f} ({dry_run_label})")
        return position_id

    def close_position(
        self,
        position_id: int,
        exit_price: float,
        exit_volume: float,
        exit_fee: float = 0.0
    ):
        """Close an existing position and calculate P&L."""
        cursor = self.conn.cursor()

        # Get position details
        cursor.execute("SELECT * FROM positions WHERE id = ?", (position_id,))
        position = cursor.fetchone()

        if not position:
            logger.error(f"Position {position_id} not found")
            return

        # Calculate P&L
        if position['position_type'] == 'long':
            gross_pnl = (exit_price - position['entry_price']) * exit_volume
        else:  # short
            gross_pnl = (position['entry_price'] - exit_price) * exit_volume

        total_fees = position['entry_fee'] + exit_fee
        net_pnl = gross_pnl - total_fees
        pnl_percent = (net_pnl / (position['entry_price'] * position['entry_volume'])) * 100

        # Update position
        cursor.execute("""
            UPDATE positions SET
                exit_time = ?,
                exit_price = ?,
                exit_volume = ?,
                exit_fee = ?,
                gross_pnl = ?,
                total_fees = ?,
                net_pnl = ?,
                pnl_percent = ?,
                status = 'closed',
                closed_time = ?
            WHERE id = ?
        """, (
            datetime.now(), exit_price, exit_volume, exit_fee,
            gross_pnl, total_fees, net_pnl, pnl_percent,
            datetime.now(), position_id
        ))
        self.conn.commit()

        logger.info(
            f"Closed position {position_id}: "
            f"Gross P&L: ${gross_pnl:.2f}, Fees: ${total_fees:.2f}, Net P&L: ${net_pnl:.2f}"
        )

    def record_market_condition(
        self,
        symbol: str,
        state: str,
        price: float,
        recommended_strategy: str,
        active_strategy: str,
        adx: Optional[float] = None,
        atr: Optional[float] = None,
        range_percent: Optional[float] = None,
        choppiness: Optional[float] = None,
        slope: Optional[float] = None,
        confidence: Optional[float] = None
    ):
        """Record market condition analysis."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO market_conditions (
                symbol, state, price,
                adx, atr, range_percent, choppiness, slope, confidence,
                recommended_strategy, active_strategy
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol, state, price,
            adx, atr, range_percent, choppiness, slope, confidence,
            recommended_strategy, active_strategy
        ))
        self.conn.commit()

    def record_strategy_switch(
        self,
        symbol: str,
        from_strategy: str,
        to_strategy: str,
        reason: str,
        market_state: str,
        confidence: float,
        confirmations: int,
        switches_today: int
    ):
        """Record a strategy switch."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO strategy_switches (
                symbol, from_strategy, to_strategy, reason,
                market_state, confidence,
                confirmations_received, switches_today
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol, from_strategy, to_strategy, reason,
            market_state, confidence,
            confirmations, switches_today
        ))
        self.conn.commit()
        logger.info(f"Recorded strategy switch for {symbol}: {from_strategy} → {to_strategy}")

    def get_open_position(self, symbol: str) -> Optional[Dict]:
        """Get currently open position for a symbol."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM positions
            WHERE symbol = ? AND status = 'open'
            ORDER BY entry_time DESC
            LIMIT 1
        """, (symbol,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_daily_stats(self, date: Optional[str] = None) -> Dict[str, Any]:
        """Get trading statistics for a specific date."""
        if date is None:
            date = datetime.now().date()

        cursor = self.conn.cursor()

        # Get completed positions for the date
        cursor.execute("""
            SELECT
                COUNT(*) as total_trades,
                COALESCE(SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END), 0) as winning_trades,
                COALESCE(SUM(gross_pnl), 0) as gross_pnl,
                COALESCE(SUM(total_fees), 0) as total_fees,
                COALESCE(SUM(net_pnl), 0) as net_pnl,
                GROUP_CONCAT(DISTINCT symbol) as coins_traded
            FROM positions
            WHERE DATE(closed_time) = ?
            AND status = 'closed'
        """, (date,))

        stats = dict(cursor.fetchone())

        # Get strategy switches for the day
        cursor.execute("""
            SELECT COUNT(*) as switches
            FROM strategy_switches
            WHERE DATE(timestamp) = ?
        """, (date,))

        stats['strategy_switches'] = cursor.fetchone()['switches']

        return stats

    def get_strategy_performance(self, symbol: str, strategy: str) -> Dict[str, Any]:
        """Get performance metrics for a specific strategy."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as total_trades,
                COALESCE(SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END), 0) as winning_trades,
                COALESCE(SUM(CASE WHEN net_pnl <= 0 THEN 1 ELSE 0 END), 0) as losing_trades,
                COALESCE(SUM(gross_pnl), 0) as gross_pnl,
                COALESCE(SUM(total_fees), 0) as total_fees,
                COALESCE(SUM(net_pnl), 0) as net_pnl,
                COALESCE(AVG(CASE WHEN net_pnl > 0 THEN net_pnl END), 0) as avg_win,
                COALESCE(AVG(CASE WHEN net_pnl <= 0 THEN ABS(net_pnl) END), 0) as avg_loss
            FROM positions
            WHERE symbol = ? AND strategy = ? AND status = 'closed'
        """, (symbol, strategy))

        stats = dict(cursor.fetchone())

        # Calculate win rate and profit factor
        if stats['total_trades'] and stats['total_trades'] > 0:
            stats['win_rate'] = (stats['winning_trades'] / stats['total_trades']) * 100
        else:
            stats['win_rate'] = 0.0

        if stats['avg_loss'] and stats['avg_loss'] > 0:
            stats['profit_factor'] = (stats['avg_win'] or 0) / stats['avg_loss']
        else:
            stats['profit_factor'] = 0.0

        return stats

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
