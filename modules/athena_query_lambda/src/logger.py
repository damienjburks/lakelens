"""Structured JSON logger for the Athena Query Lambda Validator.

Provides JSON-formatted log entries written to stdout for CloudWatch Logs capture.
Each log entry includes a correlation_id that is shared across all entries within
a single Lambda invocation, enabling request-level tracing.

Event types:
- validation_pass: SQL query passed all validation rules
- validation_fail: SQL query failed one or more validation rules
- query_start: Athena query execution has begun
- query_success: Athena query completed successfully
- query_timeout: Athena query exceeded the configured timeout
- query_error: Athena query failed with an error

CRITICAL: This logger NEVER includes result row data or cell values.
Only metadata (row_count, execution_time_ms) is logged.
"""

import json
import sys
from datetime import datetime, timezone
from typing import Any


class StructuredLogger:
    """JSON-formatted logger for Lambda invocations.

    All log entries produced by an instance share the same correlation_id,
    enabling tracing of all events within a single invocation.

    Log entries are written as single-line JSON to stdout, which CloudWatch
    Logs captures automatically.
    """

    def __init__(self, correlation_id: str) -> None:
        """Initialize the logger with a correlation ID.

        Args:
            correlation_id: UUID v4 string shared across all log entries
                in a single Lambda invocation.
        """
        self._correlation_id = correlation_id

    @property
    def correlation_id(self) -> str:
        """The correlation ID for this logger instance."""
        return self._correlation_id

    def _emit(self, entry: dict[str, Any]) -> None:
        """Write a JSON log entry to stdout.

        Each entry is serialized as a single line of JSON.
        """
        print(json.dumps(entry, default=str), file=sys.stdout, flush=True)

    def _base_entry(self, event_type: str, query: str) -> dict[str, Any]:
        """Build the base log entry with common fields.

        Args:
            event_type: The type of event being logged.
            query: The SQL query text associated with this event.

        Returns:
            Dictionary with timestamp, correlation_id, event_type, and query.
        """
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": self._correlation_id,
            "event_type": event_type,
            "query": query,
        }

    def log_validation_pass(self, query: str) -> None:
        """Log a successful SQL validation.

        Args:
            query: The SQL query that passed validation.
        """
        entry = self._base_entry("validation_pass", query)
        self._emit(entry)

    def log_validation_fail(self, query: str, errors: list[str]) -> None:
        """Log a failed SQL validation.

        Args:
            query: The SQL query that failed validation.
            errors: List of validation error messages.
        """
        entry = self._base_entry("validation_fail", query)
        entry["validation_errors"] = errors
        self._emit(entry)

    def log_query_start(self, query: str) -> None:
        """Log the start of an Athena query execution.

        Args:
            query: The SQL query being executed.
        """
        entry = self._base_entry("query_start", query)
        self._emit(entry)

    def log_query_success(
        self, query: str, execution_time_ms: int, row_count: int
    ) -> None:
        """Log a successful Athena query execution.

        Only metadata (execution time and row count) is logged.
        Result row data and cell values are NEVER included.

        Args:
            query: The SQL query that was executed.
            execution_time_ms: Query execution duration in milliseconds.
            row_count: Number of rows returned by the query.
        """
        entry = self._base_entry("query_success", query)
        entry["execution_time_ms"] = execution_time_ms
        entry["row_count"] = row_count
        self._emit(entry)

    def log_query_timeout(self, query: str, execution_time_ms: int) -> None:
        """Log an Athena query that exceeded the configured timeout.

        Args:
            query: The SQL query that timed out.
            execution_time_ms: Duration before timeout in milliseconds.
        """
        entry = self._base_entry("query_timeout", query)
        entry["execution_time_ms"] = execution_time_ms
        self._emit(entry)

    def log_query_error(self, query: str, error_message: str) -> None:
        """Log an Athena query execution error.

        Args:
            query: The SQL query that produced an error.
            error_message: Description of the error that occurred.
        """
        entry = self._base_entry("query_error", query)
        entry["error_message"] = error_message
        self._emit(entry)
