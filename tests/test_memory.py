"""
Unit tests for fix memory system.
"""

import os
import pytest
from pathlib import Path

from agent.memory import FixMemory


@pytest.fixture
def temp_memory():
    """Create a temporary memory database for testing."""
    db_path = "test_memory.db"

    # Create fresh database
    memory = FixMemory(db_path)

    yield memory

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


def test_save_and_retrieve_fix(temp_memory):
    """Test saving and retrieving a fix."""
    memory = temp_memory

    # Save a fix
    fix_id = memory.save_fix(
        pipeline_id="12345",
        job_id="67890",
        error_type="syntax",
        error_message="SyntaxError: invalid syntax",
        fix_applied="Fixed missing colon",
        fix_strategy="openai_syntax_fix",
        error_file="main.py",
        pipeline_passed=True,
        attempt_number=1
    )

    assert fix_id > 0

    # Retrieve it
    past_fix = memory.get_past_fix("syntax", "SyntaxError: invalid syntax")

    assert past_fix is not None
    assert past_fix["pipeline_id"] == "12345"
    assert past_fix["fix_strategy"] == "openai_syntax_fix"
    assert past_fix["pipeline_passed"] == 1


def test_no_past_fix_for_new_error(temp_memory):
    """Test that non-existent errors return None."""
    memory = temp_memory

    past_fix = memory.get_past_fix("dependency", "ModuleNotFoundError: No module named 'xyz'")

    assert past_fix is None


def test_update_pipeline_result(temp_memory):
    """Test updating pipeline result."""
    memory = temp_memory

    # Save a fix
    memory.save_fix(
        pipeline_id="99999",
        job_id="11111",
        error_type="test",
        error_message="AssertionError",
        fix_applied="Fixed test",
        fix_strategy="openai_test_fix",
        pipeline_passed=False,
        attempt_number=1
    )

    # Update result
    rows = memory.update_result("99999", passed=True)

    assert rows == 1

    # Verify update
    past_fix = memory.get_past_fix("test", "AssertionError")
    assert past_fix["pipeline_passed"] == 1


def test_get_stats(temp_memory):
    """Test statistics calculation."""
    memory = temp_memory

    # Add multiple fixes
    for i in range(5):
        memory.save_fix(
            pipeline_id=f"pipe_{i}",
            job_id=f"job_{i}",
            error_type="dependency",
            error_message=f"Error {i}",
            fix_applied="Fixed",
            fix_strategy="manifest_append",
            pipeline_passed=(i % 2 == 0),  # 3 pass, 2 fail
            attempt_number=1
        )

    stats = memory.get_stats()

    assert stats["total_fixes"] == 5
    assert stats["successful_fixes"] == 3
    assert stats["success_rate"] == 60.0
    assert len(stats["common_errors"]) > 0


def test_escalation_flag(temp_memory):
    """Test escalation flag (attempt_number = -1)."""
    memory = temp_memory

    # Save escalated fix
    memory.save_fix(
        pipeline_id="esc_123",
        job_id="esc_456",
        error_type="unknown",
        error_message="Unknown error",
        fix_applied="Escalated",
        fix_strategy="escalated",
        pipeline_passed=False,
        attempt_number=-1  # Escalation flag
    )

    stats = memory.get_stats()
    assert stats["escalated"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
