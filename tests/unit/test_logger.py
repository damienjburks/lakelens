"""Unit tests for the structured JSON logger.

Tests cover:
- All event types emit valid JSON to stdout
- All entries include required fields (timestamp, correlation_id, event_type, query)
- All entries in a single invocation share the same correlation_id
- Success events include execution_time_ms and row_count
- No result row data or cell values appear in any log entry
- Validation fail events include validation_errors
- Timeout events include execution_time_ms
- Error events include error_message
"""

import json
from io import StringIO
from unittest.mock import patch

import pytest

from modules.athena_query_lambda.src.logger import StructuredLogger


@pytest.fixture
def logger() -> StructuredLogger:
    """Create a StructuredLogger with a fixed correlation ID for testing."""
    return StructuredLogger(correlation_id="test-uuid-1234-5678")


class TestBaseLogEntry:
    """Tests for common log entry fields."""

    def test_all_entries_contain_timestamp(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_validation_pass("SELECT 1")
        entry = json.loads(mock_stdout.getvalue().strip())
        assert "timestamp" in entry
        # ISO 8601 format check — should contain 'T' separator and timezone
        assert "T" in entry["timestamp"]

    def test_all_entries_contain_correlation_id(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_validation_pass("SELECT 1")
        entry = json.loads(mock_stdout.getvalue().strip())
        assert entry["correlation_id"] == "test-uuid-1234-5678"

    def test_all_entries_contain_event_type(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_validation_pass("SELECT 1")
        entry = json.loads(mock_stdout.getvalue().strip())
        assert entry["event_type"] == "validation_pass"

    def test_all_entries_contain_query(self, logger: StructuredLogger):
        query = "SELECT * FROM my_table LIMIT 10"
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_validation_pass(query)
        entry = json.loads(mock_stdout.getvalue().strip())
        assert entry["query"] == query

    def test_correlation_id_shared_across_entries(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_validation_pass("SELECT 1")
            logger.log_query_start("SELECT 1")
            logger.log_query_success("SELECT 1", execution_time_ms=100, row_count=5)

        lines = mock_stdout.getvalue().strip().split("\n")
        entries = [json.loads(line) for line in lines]

        correlation_ids = {e["correlation_id"] for e in entries}
        assert len(correlation_ids) == 1
        assert "test-uuid-1234-5678" in correlation_ids

    def test_entries_are_valid_json(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_validation_pass("SELECT 1")
            logger.log_validation_fail("DROP TABLE x", ["Forbidden keyword"])
            logger.log_query_start("SELECT 1")
            logger.log_query_success("SELECT 1", 200, 10)
            logger.log_query_timeout("SELECT 1", 60000)
            logger.log_query_error("SELECT 1", "Access denied")

        lines = mock_stdout.getvalue().strip().split("\n")
        assert len(lines) == 6
        for line in lines:
            parsed = json.loads(line)
            assert isinstance(parsed, dict)


class TestValidationPass:
    """Tests for validation_pass log events."""

    def test_event_type_is_validation_pass(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_validation_pass("SELECT id FROM findings LIMIT 10")
        entry = json.loads(mock_stdout.getvalue().strip())
        assert entry["event_type"] == "validation_pass"

    def test_does_not_contain_result_data(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_validation_pass("SELECT id FROM findings LIMIT 10")
        entry = json.loads(mock_stdout.getvalue().strip())
        assert "results" not in entry
        assert "rows" not in entry
        assert "data" not in entry


class TestValidationFail:
    """Tests for validation_fail log events."""

    def test_event_type_is_validation_fail(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_validation_fail("DROP TABLE x", ["Forbidden keyword 'DROP'"])
        entry = json.loads(mock_stdout.getvalue().strip())
        assert entry["event_type"] == "validation_fail"

    def test_includes_validation_errors(self, logger: StructuredLogger):
        errors = ["Forbidden keyword 'DROP'", "Table not approved"]
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_validation_fail("DROP TABLE x", errors)
        entry = json.loads(mock_stdout.getvalue().strip())
        assert entry["validation_errors"] == errors

    def test_empty_errors_list(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_validation_fail("SELECT 1", [])
        entry = json.loads(mock_stdout.getvalue().strip())
        assert entry["validation_errors"] == []


class TestQueryStart:
    """Tests for query_start log events."""

    def test_event_type_is_query_start(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_query_start("SELECT id FROM findings LIMIT 10")
        entry = json.loads(mock_stdout.getvalue().strip())
        assert entry["event_type"] == "query_start"

    def test_does_not_contain_execution_time(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_query_start("SELECT id FROM findings LIMIT 10")
        entry = json.loads(mock_stdout.getvalue().strip())
        assert "execution_time_ms" not in entry


class TestQuerySuccess:
    """Tests for query_success log events."""

    def test_event_type_is_query_success(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_query_success("SELECT 1", execution_time_ms=150, row_count=42)
        entry = json.loads(mock_stdout.getvalue().strip())
        assert entry["event_type"] == "query_success"

    def test_includes_execution_time_ms(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_query_success("SELECT 1", execution_time_ms=1234, row_count=10)
        entry = json.loads(mock_stdout.getvalue().strip())
        assert entry["execution_time_ms"] == 1234

    def test_includes_row_count(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_query_success("SELECT 1", execution_time_ms=100, row_count=99)
        entry = json.loads(mock_stdout.getvalue().strip())
        assert entry["row_count"] == 99

    def test_does_not_contain_result_data(self, logger: StructuredLogger):
        """CRITICAL: row data / cell values must NEVER appear in logs."""
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_query_success("SELECT 1", execution_time_ms=100, row_count=5)
        entry = json.loads(mock_stdout.getvalue().strip())
        assert "results" not in entry
        assert "rows" not in entry
        assert "data" not in entry
        assert "cells" not in entry

    def test_zero_row_count(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_query_success("SELECT 1", execution_time_ms=50, row_count=0)
        entry = json.loads(mock_stdout.getvalue().strip())
        assert entry["row_count"] == 0


class TestQueryTimeout:
    """Tests for query_timeout log events."""

    def test_event_type_is_query_timeout(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_query_timeout("SELECT 1", execution_time_ms=60000)
        entry = json.loads(mock_stdout.getvalue().strip())
        assert entry["event_type"] == "query_timeout"

    def test_includes_execution_time_ms(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_query_timeout("SELECT 1", execution_time_ms=60000)
        entry = json.loads(mock_stdout.getvalue().strip())
        assert entry["execution_time_ms"] == 60000

    def test_does_not_contain_row_count(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_query_timeout("SELECT 1", execution_time_ms=60000)
        entry = json.loads(mock_stdout.getvalue().strip())
        assert "row_count" not in entry


class TestQueryError:
    """Tests for query_error log events."""

    def test_event_type_is_query_error(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_query_error("SELECT 1", "Access denied")
        entry = json.loads(mock_stdout.getvalue().strip())
        assert entry["event_type"] == "query_error"

    def test_includes_error_message(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_query_error("SELECT 1", "Access denied to table")
        entry = json.loads(mock_stdout.getvalue().strip())
        assert entry["error_message"] == "Access denied to table"

    def test_does_not_contain_result_data(self, logger: StructuredLogger):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.log_query_error("SELECT 1", "Some error")
        entry = json.loads(mock_stdout.getvalue().strip())
        assert "results" not in entry
        assert "rows" not in entry


class TestCorrelationIdProperty:
    """Tests for the correlation_id property."""

    def test_exposes_correlation_id(self):
        logger = StructuredLogger(correlation_id="my-corr-id-abc")
        assert logger.correlation_id == "my-corr-id-abc"

    def test_different_loggers_have_different_ids(self):
        logger1 = StructuredLogger(correlation_id="id-1")
        logger2 = StructuredLogger(correlation_id="id-2")
        assert logger1.correlation_id != logger2.correlation_id
