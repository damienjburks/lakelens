"""Athena query executor with timeout cancellation.

Executes validated SQL queries against Amazon Athena using a workgroup-scoped
configuration. Polls for query completion with a configurable timeout, cancels
queries that exceed the timeout, and formats results as a list of dictionaries.
"""

import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

from config import ValidatorConfig


# Athena query states
_STATE_QUEUED = "QUEUED"
_STATE_RUNNING = "RUNNING"
_STATE_SUCCEEDED = "SUCCEEDED"
_STATE_FAILED = "FAILED"
_STATE_CANCELLED = "CANCELLED"

# Poll interval in seconds
_POLL_INTERVAL_SECONDS = 1.0


def execute_query(
    query: str,
    config: ValidatorConfig,
    athena_client: Any | None = None,
) -> dict[str, Any]:
    """Execute a validated SQL query against Athena with timeout cancellation.

    Starts a query execution scoped to the configured workgroup, polls for
    completion within the configured timeout, and returns formatted results.

    Args:
        query: The validated SQL query string to execute.
        config: ValidatorConfig instance providing workgroup and timeout settings.
        athena_client: Optional boto3 Athena client (injected for testing).
            If None, a new client is created.

    Returns:
        A structured result dict with:
        - status: "success" or "error"
        - query: the executed SQL string
        - results: list of dicts (column names as keys) or empty list
        - summary: descriptive text or None
        - validation_errors: list of error messages or empty list
    """
    if athena_client is None:
        athena_client = boto3.client("athena")

    # Start query execution (workgroup handles output location)
    query_execution_id, start_error = _start_query(query, config, athena_client)
    if query_execution_id is None:
        return _error_response(query, f"Failed to start Athena query execution: {start_error}")

    # Poll for completion with timeout
    final_state, state_reason = _poll_query_completion(
        query_execution_id, config.query_timeout_seconds, athena_client
    )

    if final_state == _STATE_SUCCEEDED:
        return _fetch_and_format_results(query, query_execution_id, athena_client)
    elif final_state == "TIMEOUT":
        _cancel_query(query_execution_id, athena_client)
        return _error_response(
            query,
            f"Query exceeded the configured timeout of {config.query_timeout_seconds} seconds",
        )
    elif final_state == _STATE_FAILED:
        return _error_response(
            query, f"Athena query failed: {state_reason or 'Unknown error'}"
        )
    elif final_state == _STATE_CANCELLED:
        return _error_response(query, "Athena query was cancelled")
    else:
        return _error_response(
            query, f"Unexpected query state: {final_state}"
        )


def _start_query(
    query: str,
    config: ValidatorConfig,
    athena_client: Any,
) -> tuple[str | None, str | None]:
    """Start an Athena query execution scoped to the configured workgroup.

    Returns a tuple of (QueryExecutionId, error_message).
    On success: (id, None). On failure: (None, error_message).
    """
    try:
        # Use the first configured database as the default catalog/schema context
        exec_params = {
            "QueryString": query,
            "WorkGroup": config.athena_workgroup,
        }
        if config.allowed_databases:
            exec_params["QueryExecutionContext"] = {
                "Database": config.allowed_databases[0],
            }
        response = athena_client.start_query_execution(**exec_params)
        return response["QueryExecutionId"], None
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        return None, f"{error_code}: {error_message}"


def _poll_query_completion(
    query_execution_id: str,
    timeout_seconds: int,
    athena_client: Any,
) -> tuple[str, str | None]:
    """Poll Athena for query completion within the configured timeout.

    Returns a tuple of (final_state, state_change_reason).
    final_state is one of: SUCCEEDED, FAILED, CANCELLED, or "TIMEOUT".
    """
    elapsed = 0.0

    while elapsed < timeout_seconds:
        try:
            response = athena_client.get_query_execution(
                QueryExecutionId=query_execution_id
            )
            status = response["QueryExecution"]["Status"]
            state = status["State"]

            if state in (_STATE_SUCCEEDED, _STATE_FAILED, _STATE_CANCELLED):
                reason = status.get("StateChangeReason")
                return state, reason

            # Still QUEUED or RUNNING — wait and poll again
            time.sleep(_POLL_INTERVAL_SECONDS)
            elapsed += _POLL_INTERVAL_SECONDS

        except ClientError:
            # If we can't check status, treat as an error
            return _STATE_FAILED, "Unable to retrieve query execution status"

    # Timeout reached
    return "TIMEOUT", None


def _cancel_query(query_execution_id: str, athena_client: Any) -> None:
    """Cancel a running Athena query via StopQueryExecution.

    Best-effort cancellation — errors are silently ignored since the query
    may have already completed or been cancelled.
    """
    try:
        athena_client.stop_query_execution(
            QueryExecutionId=query_execution_id
        )
    except ClientError:
        # Best-effort cancellation; ignore errors
        pass


def _fetch_and_format_results(
    query: str,
    query_execution_id: str,
    athena_client: Any,
) -> dict[str, Any]:
    """Fetch query results and format as a list of dicts.

    Column names from the result set metadata are used as dictionary keys.
    Handles pagination via NextToken to retrieve all result rows.

    Returns a success response with results, or an error response on failure.
    """
    try:
        rows: list[dict[str, Any]] = []
        column_names: list[str] = []
        next_token: str | None = None
        is_first_page = True

        while True:
            kwargs: dict[str, Any] = {
                "QueryExecutionId": query_execution_id,
            }
            if next_token:
                kwargs["NextToken"] = next_token

            response = athena_client.get_query_results(**kwargs)
            result_set = response["ResultSet"]

            # Extract column names from metadata on first page
            if is_first_page:
                column_info = result_set.get("ResultSetMetadata", {}).get(
                    "ColumnInfo", []
                )
                column_names = [col["Name"] for col in column_info]
                is_first_page = False

            # Process rows (first row on first page is column headers)
            result_rows = result_set.get("Rows", [])
            start_index = 1 if not next_token and len(rows) == 0 else 0

            for row in result_rows[start_index:]:
                data = row.get("Data", [])
                row_dict = {}
                for i, cell in enumerate(data):
                    if i < len(column_names):
                        row_dict[column_names[i]] = cell.get("VarCharValue")
                rows.append(row_dict)

            # Check for more pages
            next_token = response.get("NextToken")
            if not next_token:
                break

        # Build success response
        row_count = len(rows)
        if row_count == 0:
            summary = "Query returned no results"
        else:
            summary = f"Query returned {row_count} row{'s' if row_count != 1 else ''}"

        return {
            "status": "success",
            "query": query,
            "results": rows,
            "summary": summary,
            "validation_errors": [],
        }

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        error_message = e.response.get("Error", {}).get("Message", "Unknown error")

        if error_code in ("AccessDeniedException", "UnauthorizedOperation"):
            return _error_response(
                query,
                f"Access denied when fetching query results: {error_message}",
            )

        return _error_response(
            query, f"Error fetching query results: {error_message}"
        )


def _error_response(query: str, error_message: str) -> dict[str, Any]:
    """Build a structured error response."""
    return {
        "status": "error",
        "query": query,
        "results": [],
        "summary": None,
        "validation_errors": [error_message],
    }
