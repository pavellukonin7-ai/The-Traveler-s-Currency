import sqlite3
import tempfile
import unittest
from pathlib import Path

import database


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DATABASE_PATH = str(Path(self.temp_dir.name) / "wallet.sqlite3")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_migrates_classic_schema_and_preserves_trip(self) -> None:
        conn = sqlite3.connect(database.DATABASE_PATH)
        conn.executescript(
            """
            CREATE TABLE trips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                origin_country TEXT NOT NULL,
                destination_country TEXT NOT NULL,
                home_currency TEXT NOT NULL,
                destination_currency TEXT NOT NULL,
                rate REAL NOT NULL,
                balance_home REAL NOT NULL,
                balance_destination REAL NOT NULL,
                active INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                rate_source TEXT NOT NULL DEFAULT 'api'
            );
            CREATE TABLE expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                amount_destination REAL NOT NULL,
                amount_home REAL NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO trips (
                user_id, origin_country, destination_country, home_currency,
                destination_currency, rate, balance_home, balance_destination, active
            ) VALUES (7, 'Россия', 'Турция', 'RUB', 'TRY', 0.5, 1000, 500, 1);
            """
        )
        conn.close()

        database.init_db()
        trip = database.get_active_trip(7)
        self.assertEqual(trip["destination_currency"], "TRY")
        self.assertEqual(trip["initial_balance_home"], 1000)
        with database.connect() as migrated:
            expense_columns = {
                row["name"] for row in migrated.execute("PRAGMA table_info(expenses)")
            }
        self.assertIn("category", expense_columns)

    def test_add_and_undo_expense(self) -> None:
        database.init_db()
        trip_id = database.create_trip(
            1, "Россия", "Турция", "RUB", "TRY", 0.5, "api", 1000, 500
        )
        updated = database.add_expense(1, trip_id, 50, 100, "Еда", "обед")
        self.assertEqual(updated["balance_destination"], 450)
        self.assertEqual(database.trip_stats(1, trip_id)["spent_destination"], 50)

        result = database.undo_last_expense(1, trip_id)
        self.assertIsNotNone(result)
        _, restored = result
        self.assertEqual(restored["balance_destination"], 500)
        self.assertEqual(database.trip_stats(1, trip_id)["count"], 0)


if __name__ == "__main__":
    unittest.main()

