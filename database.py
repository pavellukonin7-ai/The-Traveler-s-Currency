"""SQLite storage with automatic migration from the classic bot schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from config import SETTINGS


DATABASE_PATH = SETTINGS.database_path


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def init_db() -> None:
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(
            """
            PRAGMA journal_mode = WAL;

            CREATE TABLE IF NOT EXISTS trips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                origin_country TEXT NOT NULL,
                destination_country TEXT NOT NULL,
                home_currency TEXT NOT NULL,
                destination_currency TEXT NOT NULL,
                rate REAL NOT NULL,
                rate_source TEXT NOT NULL DEFAULT 'api',
                balance_home REAL NOT NULL,
                balance_destination REAL NOT NULL,
                initial_balance_home REAL,
                initial_balance_destination REAL,
                rate_updated_at TEXT,
                active INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                amount_destination REAL NOT NULL,
                amount_home REAL NOT NULL,
                category TEXT NOT NULL DEFAULT 'Другое',
                note TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS ix_trips_user_active ON trips(user_id, active);
            CREATE INDEX IF NOT EXISTS ix_expenses_trip_id ON expenses(trip_id, id DESC);
            """
        )

        trip_columns = _columns(conn, "trips")
        migrations = {
            "rate_source": "ALTER TABLE trips ADD COLUMN rate_source TEXT NOT NULL DEFAULT 'api'",
            "initial_balance_home": "ALTER TABLE trips ADD COLUMN initial_balance_home REAL",
            "initial_balance_destination": "ALTER TABLE trips ADD COLUMN initial_balance_destination REAL",
            "rate_updated_at": "ALTER TABLE trips ADD COLUMN rate_updated_at TEXT",
        }
        for column, sql in migrations.items():
            if column not in trip_columns:
                conn.execute(sql)

        expense_columns = _columns(conn, "expenses")
        if "category" not in expense_columns:
            conn.execute("ALTER TABLE expenses ADD COLUMN category TEXT NOT NULL DEFAULT 'Другое'")

        conn.execute(
            """
            UPDATE trips
            SET initial_balance_home = balance_home + COALESCE((
                    SELECT SUM(amount_home) FROM expenses WHERE expenses.trip_id = trips.id
                ), 0)
            WHERE initial_balance_home IS NULL
            """
        )
        conn.execute(
            """
            UPDATE trips
            SET initial_balance_destination = balance_destination + COALESCE((
                    SELECT SUM(amount_destination) FROM expenses WHERE expenses.trip_id = trips.id
                ), 0)
            WHERE initial_balance_destination IS NULL
            """
        )


def create_trip(
    user_id: int,
    origin_country: str,
    destination_country: str,
    home_currency: str,
    destination_currency: str,
    rate: float,
    rate_source: str,
    balance_home: float,
    balance_destination: float,
    rate_updated_at: str | None = None,
) -> int:
    with connect() as conn:
        conn.execute("UPDATE trips SET active = 0 WHERE user_id = ?", (user_id,))
        cursor = conn.execute(
            """
            INSERT INTO trips (
                user_id, origin_country, destination_country, home_currency,
                destination_currency, rate, rate_source, balance_home,
                balance_destination, initial_balance_home,
                initial_balance_destination, rate_updated_at, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                user_id,
                origin_country,
                destination_country,
                home_currency,
                destination_currency,
                rate,
                rate_source,
                balance_home,
                balance_destination,
                balance_home,
                balance_destination,
                rate_updated_at,
            ),
        )
        return int(cursor.lastrowid)


def get_active_trip(user_id: int) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM trips WHERE user_id = ? AND active = 1 ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()


def get_trip(user_id: int, trip_id: int) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM trips WHERE user_id = ? AND id = ?",
            (user_id, trip_id),
        ).fetchone()


def list_trips(user_id: int) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM trips WHERE user_id = ? ORDER BY active DESC, id DESC",
            (user_id,),
        ).fetchall()


def set_active_trip(user_id: int, trip_id: int) -> sqlite3.Row | None:
    if get_trip(user_id, trip_id) is None:
        return None
    with connect() as conn:
        conn.execute("UPDATE trips SET active = 0 WHERE user_id = ?", (user_id,))
        conn.execute("UPDATE trips SET active = 1 WHERE user_id = ? AND id = ?", (user_id, trip_id))
    return get_trip(user_id, trip_id)


def update_trip_rate(
    user_id: int,
    trip_id: int,
    new_rate: float,
    rate_source: str = "manual",
    rate_updated_at: str | None = None,
) -> sqlite3.Row | None:
    trip = get_trip(user_id, trip_id)
    if trip is None or new_rate <= 0:
        return None
    balance_destination = float(trip["balance_destination"])
    balance_home = balance_destination / new_rate
    with connect() as conn:
        conn.execute(
            """
            UPDATE trips
            SET rate = ?, rate_source = ?, rate_updated_at = ?, balance_home = ?
            WHERE user_id = ? AND id = ?
            """,
            (new_rate, rate_source, rate_updated_at, balance_home, user_id, trip_id),
        )
    return get_trip(user_id, trip_id)


def add_expense(
    user_id: int,
    trip_id: int,
    amount_destination: float,
    amount_home: float,
    category: str = "Другое",
    note: str = "",
) -> sqlite3.Row | None:
    with connect() as conn:
        trip = conn.execute(
            "SELECT * FROM trips WHERE user_id = ? AND id = ?",
            (user_id, trip_id),
        ).fetchone()
        if trip is None:
            return None
        new_destination = float(trip["balance_destination"]) - amount_destination
        new_home = float(trip["balance_home"]) - amount_home
        conn.execute(
            """
            INSERT INTO expenses (
                trip_id, user_id, amount_destination, amount_home, category, note
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (trip_id, user_id, amount_destination, amount_home, category, note),
        )
        conn.execute(
            """
            UPDATE trips SET balance_destination = ?, balance_home = ?
            WHERE user_id = ? AND id = ?
            """,
            (new_destination, new_home, user_id, trip_id),
        )
    return get_trip(user_id, trip_id)


def undo_last_expense(user_id: int, trip_id: int) -> tuple[sqlite3.Row, sqlite3.Row] | None:
    with connect() as conn:
        expense = conn.execute(
            """
            SELECT * FROM expenses
            WHERE user_id = ? AND trip_id = ? ORDER BY id DESC LIMIT 1
            """,
            (user_id, trip_id),
        ).fetchone()
        trip = conn.execute(
            "SELECT * FROM trips WHERE user_id = ? AND id = ?",
            (user_id, trip_id),
        ).fetchone()
        if expense is None or trip is None:
            return None
        conn.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense["id"], user_id))
        conn.execute(
            """
            UPDATE trips
            SET balance_destination = balance_destination + ?,
                balance_home = balance_home + ?
            WHERE id = ? AND user_id = ?
            """,
            (expense["amount_destination"], expense["amount_home"], trip_id, user_id),
        )
    updated = get_trip(user_id, trip_id)
    return (expense, updated) if updated is not None else None


def list_expenses(user_id: int, trip_id: int, limit: int | None = 10) -> list[sqlite3.Row]:
    query = """
        SELECT * FROM expenses
        WHERE user_id = ? AND trip_id = ? ORDER BY id DESC
    """
    params: list[Any] = [user_id, trip_id]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    with connect() as conn:
        return conn.execute(query, params).fetchall()


def trip_stats(user_id: int, trip_id: int) -> dict[str, Any] | None:
    trip = get_trip(user_id, trip_id)
    if trip is None:
        return None
    with connect() as conn:
        totals = conn.execute(
            """
            SELECT COUNT(*) AS count,
                   COALESCE(SUM(amount_destination), 0) AS spent_destination,
                   COALESCE(SUM(amount_home), 0) AS spent_home
            FROM expenses WHERE user_id = ? AND trip_id = ?
            """,
            (user_id, trip_id),
        ).fetchone()
        categories = conn.execute(
            """
            SELECT category, SUM(amount_destination) AS total
            FROM expenses WHERE user_id = ? AND trip_id = ?
            GROUP BY category ORDER BY total DESC
            """,
            (user_id, trip_id),
        ).fetchall()
    return {
        "trip": trip,
        "count": int(totals["count"]),
        "spent_destination": float(totals["spent_destination"]),
        "spent_home": float(totals["spent_home"]),
        "categories": categories,
    }


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None

