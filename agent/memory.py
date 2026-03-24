"""
SQLite-based memory system for tracking fix attempts and results.
Enables the agent to learn from past fixes and avoid redundant API calls.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


class FixMemory:
    """Manages persistent storage of fix attempts and results using SQLite."""

    def __init__(self, db_path: str = "fix_history.db"):
        """
        Initialize the fix memory database.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_database()

    def _init_database(self) -> None:
        """Create database and tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fix_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pipeline_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                error_type TEXT NOT NULL,
                error_message TEXT NOT NULL,
                error_file TEXT,
                fix_applied TEXT NOT NULL,
                fix_strategy TEXT NOT NULL,
                pipeline_passed INTEGER DEFAULT 0,
                attempt_number INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create index for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_error_lookup
            ON fix_history(error_type, error_message)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pipeline
            ON fix_history(pipeline_id)
        """)

        conn.commit()
        conn.close()

    def save_fix(
        self,
        pipeline_id: str,
        job_id: str,
        error_type: str,
        error_message: str,
        fix_applied: str,
        fix_strategy: str,
        error_file: Optional[str] = None,
        pipeline_passed: bool = False,
        attempt_number: int = 1
    ) -> int:
        """
        Save a fix attempt to the database.

        Args:
            pipeline_id: GitLab pipeline ID
            job_id: GitLab job ID
            error_type: Classification of error (dependency, syntax, test, config, unknown)
            error_message: The exact error message from logs
            fix_applied: Description of the fix that was applied
            fix_strategy: The strategy used (e.g., "openai_syntax_fix", "manifest_append")
            error_file: File path where error occurred (optional)
            pipeline_passed: Whether the pipeline passed after fix (default False)
            attempt_number: Which attempt this was (default 1, -1 for escalated)

        Returns:
            int: The ID of the inserted row
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO fix_history (
                pipeline_id, job_id, error_type, error_message, error_file,
                fix_applied, fix_strategy, pipeline_passed, attempt_number, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pipeline_id,
            job_id,
            error_type,
            error_message[:500],  # Truncate very long error messages
            error_file,
            fix_applied,
            fix_strategy,
            1 if pipeline_passed else 0,
            attempt_number,
            datetime.now().isoformat()
        ))

        row_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return row_id

    def get_past_fix(self, error_type: str, error_message: str) -> Optional[dict]:
        """
        Check if we've successfully fixed this exact error before.

        Args:
            error_type: Classification of error
            error_message: The exact error message

        Returns:
            dict with fix details if found and it worked, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Truncate error message to match how we store it
        error_message_truncated = error_message[:500]

        cursor.execute("""
            SELECT * FROM fix_history
            WHERE error_type = ?
            AND error_message = ?
            AND pipeline_passed = 1
            ORDER BY created_at DESC
            LIMIT 1
        """, (error_type, error_message_truncated))

        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def update_result(self, pipeline_id: str, passed: bool) -> int:
        """
        Update the result of a fix attempt after the pipeline completes.

        Args:
            pipeline_id: GitLab pipeline ID
            passed: Whether the pipeline passed

        Returns:
            Number of rows updated
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE fix_history
            SET pipeline_passed = ?
            WHERE pipeline_id = ?
        """, (1 if passed else 0, pipeline_id))

        rows_updated = cursor.rowcount
        conn.commit()
        conn.close()

        return rows_updated

    def get_attempts_for_pipeline(self, pipeline_id: str) -> list[dict]:
        """
        Get all fix attempts for a specific pipeline.

        Args:
            pipeline_id: GitLab pipeline ID

        Returns:
            List of fix attempt records
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM fix_history
            WHERE pipeline_id = ?
            ORDER BY attempt_number ASC, created_at ASC
        """, (pipeline_id,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_stats(self) -> dict:
        """
        Get statistics about fix history.

        Returns:
            dict: Statistics including total fixes, success rate, common errors
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Total fixes
        cursor.execute("SELECT COUNT(*) as total FROM fix_history WHERE attempt_number != -1")
        total = cursor.fetchone()["total"]

        # Successful fixes
        cursor.execute("SELECT COUNT(*) as success FROM fix_history WHERE pipeline_passed = 1")
        success = cursor.fetchone()["success"]

        # Success rate
        success_rate = (success / total * 100) if total > 0 else 0.0

        # Most common error types
        cursor.execute("""
            SELECT error_type, COUNT(*) as count
            FROM fix_history
            WHERE attempt_number != -1
            GROUP BY error_type
            ORDER BY count DESC
            LIMIT 5
        """)
        common_errors = [dict(row) for row in cursor.fetchall()]

        # Escalations
        cursor.execute("SELECT COUNT(*) as escalated FROM fix_history WHERE attempt_number = -1")
        escalated = cursor.fetchone()["escalated"]

        conn.close()

        return {
            "total_fixes": total,
            "successful_fixes": success,
            "success_rate": round(success_rate, 2),
            "escalated": escalated,
            "common_errors": common_errors
        }

    def clear_history(self) -> int:
        """
        Clear all fix history. Use with caution!

        Returns:
            Number of rows deleted
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM fix_history")
        rows_deleted = cursor.rowcount

        conn.commit()
        conn.close()

        return rows_deleted


if __name__ == "__main__":
    # Test the memory system
    memory = FixMemory("test_fix_history.db")

    # Save a test fix
    fix_id = memory.save_fix(
        pipeline_id="12345",
        job_id="67890",
        error_type="syntax",
        error_message="SyntaxError: invalid syntax at line 42",
        fix_applied="Fixed missing colon in function definition",
        fix_strategy="openai_syntax_fix",
        error_file="src/main.py",
        pipeline_passed=True,
        attempt_number=1
    )

    print(f"Saved fix with ID: {fix_id}")

    # Try to find it
    past_fix = memory.get_past_fix("syntax", "SyntaxError: invalid syntax at line 42")
    print(f"Found past fix: {past_fix is not None}")

    # Get stats
    stats = memory.get_stats()
    print(f"Stats: {stats}")

    # Clean up test database
    Path("test_fix_history.db").unlink(missing_ok=True)
    print("Test completed successfully!")
