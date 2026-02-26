"""Tests for database position P&L calculations."""
from __future__ import annotations

import os
import tempfile

import pytest

from src.database import TradingDatabase


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = TradingDatabase(db_path=path)
    yield database
    database.close()
    os.unlink(path)


def test_open_and_close_long_position_pnl(db: TradingDatabase):
    """Closing a long position should compute correct gross/net P&L."""
    pos_id = db.open_position(
        symbol="XBTUSD",
        strategy="mean_reversion",
        position_type="long",
        entry_price=100_000.0,
        entry_volume=0.01,
        entry_fee=2.60,
        dry_run=True,
    )
    assert pos_id is not None

    db.close_position(
        position_id=pos_id,
        exit_price=102_000.0,
        exit_volume=0.01,
        exit_fee=2.65,
    )

    # Verify P&L
    pos = db.get_open_position("XBTUSD")
    assert pos is None  # No longer open

    # Fetch closed position directly
    cursor = db.conn.cursor()
    cursor.execute("SELECT * FROM positions WHERE id = ?", (pos_id,))
    row = cursor.fetchone()

    assert row["status"] == "closed"
    # gross = (102000 - 100000) * 0.01 = 20.0
    assert abs(row["gross_pnl"] - 20.0) < 0.01
    # fees = 2.60 + 2.65 = 5.25
    assert abs(row["total_fees"] - 5.25) < 0.01
    # net = 20.0 - 5.25 = 14.75
    assert abs(row["net_pnl"] - 14.75) < 0.01
    # pnl_percent = 14.75 / (100000 * 0.01) * 100 = 1.475%
    assert abs(row["pnl_percent"] - 1.475) < 0.01


def test_open_and_close_short_position_pnl(db: TradingDatabase):
    """Closing a short position should compute correct P&L."""
    pos_id = db.open_position(
        symbol="ETHUSD",
        strategy="sma_crossover",
        position_type="short",
        entry_price=3_000.0,
        entry_volume=1.0,
        entry_fee=7.80,
        dry_run=True,
    )

    db.close_position(
        position_id=pos_id,
        exit_price=2_900.0,
        exit_volume=1.0,
        exit_fee=7.54,
    )

    cursor = db.conn.cursor()
    cursor.execute("SELECT * FROM positions WHERE id = ?", (pos_id,))
    row = cursor.fetchone()

    # gross = (3000 - 2900) * 1.0 = 100.0
    assert abs(row["gross_pnl"] - 100.0) < 0.01
    # fees = 7.80 + 7.54 = 15.34
    assert abs(row["total_fees"] - 15.34) < 0.01
    # net = 100.0 - 15.34 = 84.66
    assert abs(row["net_pnl"] - 84.66) < 0.01


def test_close_position_with_loss(db: TradingDatabase):
    """P&L should be negative when trade loses money."""
    pos_id = db.open_position(
        symbol="SOLUSD",
        strategy="breakout",
        position_type="long",
        entry_price=150.0,
        entry_volume=10.0,
        entry_fee=3.90,
        dry_run=True,
    )

    db.close_position(
        position_id=pos_id,
        exit_price=145.0,
        exit_volume=10.0,
        exit_fee=3.77,
    )

    cursor = db.conn.cursor()
    cursor.execute("SELECT * FROM positions WHERE id = ?", (pos_id,))
    row = cursor.fetchone()

    # gross = (145 - 150) * 10 = -50.0
    assert row["gross_pnl"] < 0
    assert abs(row["gross_pnl"] - (-50.0)) < 0.01
    # net = -50.0 - (3.90 + 3.77) = -57.67
    assert row["net_pnl"] < row["gross_pnl"]


def test_get_open_position_returns_none_when_no_position(db: TradingDatabase):
    """No open positions should return None."""
    assert db.get_open_position("NONEXISTENT") is None


def test_zero_volume_position_no_division_error(db: TradingDatabase):
    """Zero cost basis should not cause a division error."""
    pos_id = db.open_position(
        symbol="XBTUSD",
        strategy="grid",
        position_type="long",
        entry_price=0.0,
        entry_volume=0.0,
        entry_fee=0.0,
        dry_run=True,
    )

    # Should not raise
    db.close_position(
        position_id=pos_id,
        exit_price=100.0,
        exit_volume=0.0,
        exit_fee=0.0,
    )

    cursor = db.conn.cursor()
    cursor.execute("SELECT pnl_percent FROM positions WHERE id = ?", (pos_id,))
    row = cursor.fetchone()
    assert row["pnl_percent"] == 0.0
