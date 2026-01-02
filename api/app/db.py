from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple


def _sqlite_ro_uri(db_path: str) -> str:
    # Ensure absolute path for consistent URI behavior.
    abs_path = os.path.abspath(db_path)
    return f"file:{abs_path}?mode=ro"


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(_sqlite_ro_uri(db_path), uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout = 2000")
    except Exception:
        pass
    return conn


@contextmanager
def db_session(db_path: str) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def _build_in_clause(values: Sequence[str], prefix: str) -> Tuple[str, Dict[str, Any]]:
    params: Dict[str, Any] = {}
    placeholders: List[str] = []
    for idx, val in enumerate(values):
        key = f"{prefix}{idx}"
        placeholders.append(f":{key}")
        params[key] = val
    clause = f"({', '.join(placeholders)})"
    return clause, params


def build_filters(
    *,
    start: str,
    end: str,
    dry_run: str,
    symbols: Optional[Sequence[str]],
    time_column: str,
) -> Tuple[str, Dict[str, Any]]:
    where = [f"{time_column} >= :start", f"{time_column} <= :end"]
    params: Dict[str, Any] = {"start": start, "end": end}

    if dry_run != "all":
        where.append("dry_run = :dry_run")
        params["dry_run"] = 1 if dry_run == "true" else 0

    if symbols:
        clause, sym_params = _build_in_clause(symbols, "sym")
        where.append(f"symbol IN {clause}")
        params.update(sym_params)

    return " AND ".join(where), params


def fetch_all(conn: sqlite3.Connection, query: str, params: Dict[str, Any]) -> List[sqlite3.Row]:
    cur = conn.execute(query, params)
    return list(cur.fetchall())


def fetch_one(conn: sqlite3.Connection, query: str, params: Dict[str, Any]) -> Optional[sqlite3.Row]:
    cur = conn.execute(query, params)
    return cur.fetchone()
