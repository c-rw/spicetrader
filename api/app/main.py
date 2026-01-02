from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import FastAPI, Query

from .db import _build_in_clause, build_filters, db_session, fetch_all, fetch_one


def _coerce_datetime_str(value: Optional[str], *, default: str) -> str:
    if not value:
        return default

    v = value.strip()

    # Accept YYYY-MM-DD and expand to a full datetime string for comparisons.
    if len(v) == 10 and v[4] == '-' and v[7] == '-':
        return f"{v} 00:00:00"

    # Allow ISO 8601 with 'T' and optional 'Z' and normalize to SQLite-friendly.
    v = v.replace('T', ' ').replace('Z', '')
    return v


def _to_iso(ts: Optional[str]) -> Optional[str]:
    if not ts:
        return None
    # Best-effort normalize SQLite timestamps like "YYYY-MM-DD HH:MM:SS".
    if 'T' not in ts and ' ' in ts:
        return ts.replace(' ', 'T') + 'Z'
    if ts.endswith('Z'):
        return ts
    return ts + 'Z'


def _row_to_dict(row) -> Dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def _build_time_symbol_filters(
    *,
    start: str,
    end: str,
    time_column: str,
    symbols: Optional[Sequence[str]],
    symbol_column: str = "symbol",
) -> Tuple[str, Dict[str, Any]]:
    where = [f"{time_column} >= :start", f"{time_column} <= :end"]
    params: Dict[str, Any] = {"start": start, "end": end}

    if symbols:
        clause, sym_params = _build_in_clause(symbols, "sym")
        where.append(f"{symbol_column} IN {clause}")
        params.update(sym_params)

    return " AND ".join(where), params


app = FastAPI(title="SpiceTrader Dashboard API", version="0.1.0")


@app.get("/health")
def health() -> Dict[str, Any]:
    db_path = os.getenv("DB_PATH", "/app/data/trading.db")
    with db_session(db_path) as conn:
        row = fetch_one(conn, "SELECT 1 as ok", {})
        return {"ok": bool(row and row["ok"] == 1), "db_path": db_path}


@app.get("/api/overview")
def overview(
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
    dry_run: str = Query(default="true", pattern="^(all|true|false)$"),
    symbols: Optional[str] = Query(default=None),
    limit_trades: int = Query(default=15, ge=1, le=200),
    limit_closed_positions: int = Query(default=10, ge=1, le=200),
    limit_strategy_switches: int = Query(default=10, ge=1, le=200),
    limit_market_conditions: int = Query(default=20, ge=1, le=200),
) -> Dict[str, Any]:
    db_path = os.getenv("DB_PATH", "/app/data/trading.db")

    now = datetime.utcnow()
    default_end = now.strftime("%Y-%m-%d %H:%M:%S")

    symbol_list: Optional[List[str]] = None
    if symbols:
        symbol_list = [s.strip() for s in symbols.split(',') if s.strip()]

    generated_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    with db_session(db_path) as conn:
        # If the UI doesn't provide a start time, default to "since bot started",
        # which we define as the earliest timestamp present in the DB.
        default_start = datetime.combine(date.today(), datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
        if not start:
            row = fetch_one(
                conn,
                """
                SELECT MIN(ts) AS start_ts
                FROM (
                  SELECT MIN(timestamp) AS ts FROM trades
                  UNION ALL
                  SELECT MIN(entry_time) AS ts FROM positions
                  UNION ALL
                  SELECT MIN(closed_time) AS ts FROM positions
                  UNION ALL
                  SELECT MIN(timestamp) AS ts FROM strategy_switches
                  UNION ALL
                  SELECT MIN(timestamp) AS ts FROM market_conditions
                )
                """,
                {},
            )
            if row and row["start_ts"]:
                default_start = str(row["start_ts"])

        start_s = _coerce_datetime_str(start, default=default_start)
        end_s = _coerce_datetime_str(end, default=default_end)

        # KPIs from closed positions
        where_closed, params_closed = build_filters(
            start=start_s,
            end=end_s,
            dry_run=dry_run,
            symbols=symbol_list,
            time_column="closed_time",
        )
        closed_kpi = fetch_one(
            conn,
            f"""
            SELECT
              COUNT(*) AS total,
              COALESCE(SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END), 0) AS wins,
              COALESCE(SUM(CASE WHEN net_pnl <= 0 THEN 1 ELSE 0 END), 0) AS losses,
              COALESCE(SUM(gross_pnl), 0) AS gross,
              COALESCE(SUM(total_fees), 0) AS fees,
              COALESCE(SUM(net_pnl), 0) AS net,
              COALESCE(AVG(CASE WHEN net_pnl > 0 THEN net_pnl END), 0) AS avg_win,
              COALESCE(AVG(CASE WHEN net_pnl <= 0 THEN ABS(net_pnl) END), 0) AS avg_loss,
              MAX(closed_time) AS last_position_closed_at
            FROM positions
            WHERE status = 'closed' AND {where_closed}
            """,
            params_closed,
        )
        closed_total = int(closed_kpi["total"]) if closed_kpi else 0
        closed_wins = int(closed_kpi["wins"]) if closed_kpi else 0
        closed_losses = int(closed_kpi["losses"]) if closed_kpi else 0
        win_rate = (closed_wins / closed_total * 100.0) if closed_total else 0.0
        avg_loss = float(closed_kpi["avg_loss"]) if closed_kpi else 0.0
        profit_factor = (float(closed_kpi["avg_win"]) / avg_loss) if avg_loss else 0.0

        # Exposure from open positions
        # Open positions should be interpreted as positions that are open *as of range end*.
        # If a position was opened before the range start and is still open, it should be included.
        where_open_parts = ["entry_time <= :end"]
        params_open: Dict[str, Any] = {"end": end_s}
        if dry_run != "all":
            where_open_parts.append("dry_run = :dry_run")
            params_open["dry_run"] = 1 if dry_run == "true" else 0

        if symbol_list:
            clause, sym_params = _build_in_clause(symbol_list, "sym")
            where_open_parts.append(f"symbol IN {clause}")
            params_open.update(sym_params)

        where_open = " AND ".join(where_open_parts)
        open_exposure = fetch_one(
            conn,
            f"""
            SELECT
              COUNT(*) AS open_positions_count,
              COALESCE(SUM(entry_price * entry_volume), 0) AS notional_usd
            FROM positions
            WHERE status = 'open' AND {where_open}
            """,
            params_open,
        )

        # Activity timestamps
        where_trades, params_trades = build_filters(
            start=start_s,
            end=end_s,
            dry_run=dry_run,
            symbols=symbol_list,
            time_column="timestamp",
        )
        last_trade = fetch_one(
            conn,
            f"SELECT MAX(timestamp) AS last_trade_at FROM trades WHERE {where_trades}",
            params_trades,
        )

        # Strategy switches (no dry_run column in schema)
        where_switch_sql, params_switch = _build_time_symbol_filters(
            start=start_s,
            end=end_s,
            time_column="timestamp",
            symbols=symbol_list,
        )

        switch_kpi = fetch_one(
            conn,
            f"SELECT COUNT(*) AS strategy_switches, MAX(timestamp) AS last_strategy_switch_at FROM strategy_switches WHERE {where_switch_sql}",
            params_switch,
        )

        # Timeseries: daily PnL
        pnl_by_day_rows = fetch_all(
            conn,
            f"""
            SELECT
              DATE(closed_time) AS date,
              COUNT(*) AS closed_positions,
              COALESCE(SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END), 0) AS wins,
              COALESCE(SUM(gross_pnl), 0) AS gross_pnl,
              COALESCE(SUM(total_fees), 0) AS total_fees,
              COALESCE(SUM(net_pnl), 0) AS net_pnl
            FROM positions
            WHERE status = 'closed' AND {where_closed}
            GROUP BY DATE(closed_time)
            ORDER BY DATE(closed_time) ASC
            """,
            params_closed,
        )
        pnl_by_day: List[Dict[str, Any]] = []
        for r in pnl_by_day_rows:
            closed_positions = int(r["closed_positions"]) if r["closed_positions"] is not None else 0
            wins = int(r["wins"]) if r["wins"] is not None else 0
            pnl_by_day.append(
                {
                    "date": r["date"],
                    "closed_positions": closed_positions,
                    "wins": wins,
                    "win_rate": (wins / closed_positions * 100.0) if closed_positions else 0.0,
                    "gross_pnl": float(r["gross_pnl"] or 0.0),
                    "total_fees": float(r["total_fees"] or 0.0),
                    "net_pnl": float(r["net_pnl"] or 0.0),
                }
            )

        # Tables
        open_positions_rows = fetch_all(
            conn,
            f"""
            SELECT
              id, symbol, strategy, market_state, position_type,
              entry_time, entry_price, entry_volume, entry_fee, dry_run
            FROM positions
            WHERE status = 'open' AND {where_open}
            ORDER BY entry_time DESC
            """,
            params_open,
        )
        open_positions = []
        for r in open_positions_rows:
            d = _row_to_dict(r)
            d["entry_time"] = _to_iso(d.get("entry_time"))
            d["dry_run"] = bool(d.get("dry_run"))
            d["notional_usd"] = float((d.get("entry_price") or 0.0) * (d.get("entry_volume") or 0.0))
            open_positions.append(d)

        recent_trades_rows = fetch_all(
            conn,
            f"""
            SELECT
              id, timestamp, symbol, strategy, market_state,
              trade_type, position_type, side,
              price, volume, value, fee, fee_currency,
              position_id, txid, dry_run, notes
            FROM trades
            WHERE {where_trades}
            ORDER BY timestamp DESC
            LIMIT :limit
            """,
            {**params_trades, "limit": limit_trades},
        )
        recent_trades = []
        for r in recent_trades_rows:
            d = _row_to_dict(r)
            d["timestamp"] = _to_iso(d.get("timestamp"))
            d["dry_run"] = bool(d.get("dry_run"))
            recent_trades.append(d)

        recent_closed_rows = fetch_all(
            conn,
            f"""
            SELECT
              id, symbol, strategy, market_state, position_type,
              entry_price, exit_price,
              gross_pnl, total_fees, net_pnl, pnl_percent,
              closed_time, dry_run
            FROM positions
            WHERE status = 'closed' AND {where_closed}
            ORDER BY closed_time DESC
            LIMIT :limit
            """,
            {**params_closed, "limit": limit_closed_positions},
        )
        recent_closed_positions = []
        for r in recent_closed_rows:
            d = _row_to_dict(r)
            d["closed_time"] = _to_iso(d.get("closed_time"))
            d["dry_run"] = bool(d.get("dry_run"))
            net_pnl_val = float(d.get("net_pnl") or 0.0)
            d["is_win"] = net_pnl_val > 0
            recent_closed_positions.append(d)

        recent_switch_rows = fetch_all(
            conn,
            f"""
            SELECT
              id, timestamp, symbol,
              from_strategy, to_strategy, reason,
              market_state, confidence,
              confirmations_received, switches_today,
              trades_with_old_strategy, pnl_with_old_strategy
            FROM strategy_switches
            WHERE {where_switch_sql}
            ORDER BY timestamp DESC
            LIMIT :limit
            """,
            {**params_switch, "limit": limit_strategy_switches},
        )
        recent_strategy_switches = []
        for r in recent_switch_rows:
            d = _row_to_dict(r)
            d["timestamp"] = _to_iso(d.get("timestamp"))
            recent_strategy_switches.append(d)

        where_mc_sql, params_mc = _build_time_symbol_filters(
            start=start_s,
            end=end_s,
            time_column="timestamp",
            symbols=symbol_list,
        )
        latest_market_conditions = fetch_all(
            conn,
            f"""
            SELECT mc.*
            FROM market_conditions mc
            WHERE {where_mc_sql}
              AND mc.timestamp = (
                SELECT MAX(timestamp)
                FROM market_conditions mc2
                WHERE mc2.symbol = mc.symbol
                  AND mc2.timestamp >= :start AND mc2.timestamp <= :end
              )
            ORDER BY mc.symbol ASC
            LIMIT :limit
            """,
            {**params_mc, "limit": limit_market_conditions},
        )
        latest_market_conditions_out = []
        for r in latest_market_conditions:
            d = _row_to_dict(r)
            d["timestamp"] = _to_iso(d.get("timestamp"))
            latest_market_conditions_out.append(d)

        # Breakdowns
        by_symbol_rows = fetch_all(
            conn,
            f"""
            SELECT
              symbol,
              COUNT(*) AS closed_positions,
              COALESCE(SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END), 0) AS wins,
              COALESCE(SUM(CASE WHEN net_pnl <= 0 THEN 1 ELSE 0 END), 0) AS losses,
              COALESCE(SUM(gross_pnl), 0) AS gross_pnl,
              COALESCE(SUM(total_fees), 0) AS fees,
              COALESCE(SUM(net_pnl), 0) AS net_pnl
            FROM positions
            WHERE status = 'closed' AND {where_closed}
            GROUP BY symbol
            ORDER BY net_pnl DESC
            """,
            params_closed,
        )
        by_symbol = []
        for r in by_symbol_rows:
            closed_positions = int(r["closed_positions"])
            wins = int(r["wins"])
            by_symbol.append(
                {
                    "symbol": r["symbol"],
                    "closed_positions": closed_positions,
                    "wins": wins,
                    "losses": int(r["losses"]),
                    "win_rate": (wins / closed_positions * 100.0) if closed_positions else 0.0,
                    "gross_pnl": float(r["gross_pnl"] or 0.0),
                    "fees": float(r["fees"] or 0.0),
                    "net_pnl": float(r["net_pnl"] or 0.0),
                }
            )

        by_strategy_rows = fetch_all(
            conn,
            f"""
            SELECT
              strategy,
              COUNT(*) AS closed_positions,
              COALESCE(SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END), 0) AS wins,
              COALESCE(SUM(CASE WHEN net_pnl <= 0 THEN 1 ELSE 0 END), 0) AS losses,
              COALESCE(SUM(gross_pnl), 0) AS gross_pnl,
              COALESCE(SUM(total_fees), 0) AS fees,
              COALESCE(SUM(net_pnl), 0) AS net_pnl
            FROM positions
            WHERE status = 'closed' AND {where_closed}
            GROUP BY strategy
            ORDER BY net_pnl DESC
            """,
            params_closed,
        )
        by_strategy = []
        for r in by_strategy_rows:
            closed_positions = int(r["closed_positions"])
            wins = int(r["wins"])
            by_strategy.append(
                {
                    "strategy": r["strategy"],
                    "closed_positions": closed_positions,
                    "wins": wins,
                    "losses": int(r["losses"]),
                    "win_rate": (wins / closed_positions * 100.0) if closed_positions else 0.0,
                    "gross_pnl": float(r["gross_pnl"] or 0.0),
                    "fees": float(r["fees"] or 0.0),
                    "net_pnl": float(r["net_pnl"] or 0.0),
                }
            )

        market_state_counts_rows = fetch_all(
            conn,
            f"""
            SELECT state, COUNT(*) AS count
            FROM market_conditions
            WHERE {where_mc_sql}
            GROUP BY state
            ORDER BY count DESC
            """,
            params_mc,
        )
        market_state_counts = [
            {"state": r["state"], "count": int(r["count"])} for r in market_state_counts_rows
        ]

    return {
        "meta": {
            "generated_at": generated_at,
            "range": {"start": start_s.replace(' ', 'T') + 'Z', "end": end_s.replace(' ', 'T') + 'Z'},
            "filters": {"dry_run": dry_run, "symbols": symbol_list or []},
            "limits": {
                "trades": limit_trades,
                "closed_positions": limit_closed_positions,
                "strategy_switches": limit_strategy_switches,
                "market_conditions": limit_market_conditions,
            },
        },
        "kpis": {
            "positions_closed": {
                "total": closed_total,
                "wins": closed_wins,
                "losses": closed_losses,
                "win_rate": win_rate,
            },
            "pnl": {
                "gross": float(closed_kpi["gross"] or 0.0) if closed_kpi else 0.0,
                "fees": float(closed_kpi["fees"] or 0.0) if closed_kpi else 0.0,
                "net": float(closed_kpi["net"] or 0.0) if closed_kpi else 0.0,
                "avg_win": float(closed_kpi["avg_win"] or 0.0) if closed_kpi else 0.0,
                "avg_loss": avg_loss,
                "profit_factor": profit_factor,
            },
            "activity": {
                "strategy_switches": int(switch_kpi["strategy_switches"]) if switch_kpi else 0,
                "last_trade_at": _to_iso(last_trade["last_trade_at"]) if last_trade else None,
                "last_position_closed_at": _to_iso(closed_kpi["last_position_closed_at"]) if closed_kpi else None,
                "last_strategy_switch_at": _to_iso(switch_kpi["last_strategy_switch_at"]) if switch_kpi else None,
            },
            "exposure": {
                "open_positions_count": int(open_exposure["open_positions_count"]) if open_exposure else 0,
                "notional_usd": float(open_exposure["notional_usd"] or 0.0) if open_exposure else 0.0,
            },
        },
        "timeseries": {"pnl_by_day": pnl_by_day},
        "tables": {
            "open_positions": open_positions,
            "recent_trades": recent_trades,
            "recent_closed_positions": recent_closed_positions,
            "recent_strategy_switches": recent_strategy_switches,
            "latest_market_conditions": latest_market_conditions_out,
        },
        "breakdowns": {
            "by_symbol": by_symbol,
            "by_strategy": by_strategy,
            "market_state_counts": market_state_counts,
        },
    }
