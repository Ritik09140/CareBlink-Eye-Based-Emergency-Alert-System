import unittest
import sqlite3
import os
from database.connection import db

class TestDatabase(unittest.TestCase):
    def test_database_dialect(self):
        # Verify db engine is registered
        self.assertIn(db.db_engine, ["sqlite", "mysql"])

    def test_query_placeholder_mapping(self):
        # We test that execute_query works for simple sqlite selections
        # SQLite should use '?' natively
        res = db.execute_query("SELECT 1 + ? AS result", (5,), fetch_one=True)
        # Check SQLite row formatting
        if isinstance(res, sqlite3.Row):
            val = res["result"]
        else:
            val = res[0]
        self.assertEqual(val, 6)

    def test_hospital_table_exists(self):
        # Verify tables exist
        res = db.execute_query("SELECT COUNT(*) FROM hospitals", fetch_one=True)
        self.assertIsNotNone(res)
        self.assertGreaterEqual(res[0], 0)

if __name__ == '__main__':
    unittest.main()
