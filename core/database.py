import sqlite3
import json
import os
import time
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("TestDatabase")

class TestDatabase:
    def __init__(self, db_path: str = "test_history.db"):
        self.db_path = os.path.abspath(db_path)
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Initializes database tables for test runs and execution metrics."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS test_runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id TEXT UNIQUE NOT NULL,
                        timestamp INTEGER NOT NULL,
                        target_url TEXT NOT NULL,
                        page_title TEXT,
                        engine TEXT NOT NULL,
                        login_mode TEXT,
                        passed_count INTEGER DEFAULT 0,
                        failed_count INTEGER DEFAULT 0,
                        healed_count INTEGER DEFAULT 0,
                        performance_score INTEGER DEFAULT 100,
                        accessibility_score INTEGER DEFAULT 100,
                        duration_seconds REAL DEFAULT 0.0,
                        summary_json TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Auto column migration for existing SQLite files
                cursor.execute("PRAGMA table_info(test_runs)")
                columns = [col[1] for col in cursor.fetchall()]
                
                missing_columns = {
                    "healed_count": "INTEGER DEFAULT 0",
                    "performance_score": "INTEGER DEFAULT 100",
                    "accessibility_score": "INTEGER DEFAULT 100",
                    "duration_seconds": "REAL DEFAULT 0.0"
                }

                for col_name, col_def in missing_columns.items():
                    if col_name not in columns:
                        cursor.execute(f"ALTER TABLE test_runs ADD COLUMN {col_name} {col_def}")
                        logger.info(f"Added missing column '{col_name}' to test_runs table")

                conn.commit()
                logger.info(f"TestDatabase initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")

    def save_run(
        self,
        run_id: str,
        target_url: str,
        page_title: str,
        engine: str,
        login_mode: str,
        passed_count: int,
        failed_count: int,
        healed_count: int,
        performance_score: int,
        accessibility_score: int,
        duration_seconds: float,
        summary_data: Dict[str, Any]
    ) -> bool:
        """Saves a completed test run record."""
        try:
            timestamp = int(time.time())
            summary_json = json.dumps(summary_data)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO test_runs (
                        run_id, timestamp, target_url, page_title, engine,
                        login_mode, passed_count, failed_count, healed_count,
                        performance_score, accessibility_score, duration_seconds, summary_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    run_id, timestamp, target_url, page_title, engine,
                    login_mode, passed_count, failed_count, healed_count,
                    performance_score, accessibility_score, duration_seconds, summary_json
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to save test run {run_id}: {e}")
            return False

    def get_history(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Retrieves recent test run history summaries."""
        runs = []
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, run_id, timestamp, target_url, page_title, engine,
                           login_mode, passed_count, failed_count, healed_count,
                           performance_score, accessibility_score, duration_seconds, created_at
                    FROM test_runs
                    ORDER BY id DESC
                    LIMIT ?
                """, (limit,))
                rows = cursor.fetchall()
                for row in rows:
                    runs.append(dict(row))
        except Exception as e:
            logger.error(f"Failed to fetch test history: {e}")
        return runs

    def get_run_details(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves full summary details for a specific run."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM test_runs WHERE run_id = ?", (run_id,))
                row = cursor.fetchone()
                if row:
                    data = dict(row)
                    if data.get("summary_json"):
                        try:
                            data["summary_data"] = json.loads(data["summary_json"])
                        except Exception:
                            data["summary_data"] = {}
                    return data
        except Exception as e:
            logger.error(f"Failed to fetch details for run {run_id}: {e}")
        return None
