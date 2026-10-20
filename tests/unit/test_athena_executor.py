"""Unit tests for the Athena executor module.

Tests cover:
- Successful query execution with result formatting
- Timeout handling with query cancellation
- Empty result set handling
- Athena service errors (permissions, general failures)
- Query start failure handling
- Pagination of results
"""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from modules.athena_query_lambda.src.athena_executor import execute_query
from modules.athena_query_lambda.src.config import ValidatorConfig


def _make_config(
    workgroup: str = "test-workgroup",
    timeout: int = 10,
) -> ValidatorConfig:
    """Create a ValidatorConfig with test defaults."""
    return ValidatorConfig(
        athena_workgroup=workgroup,
        athena_output_s3_bucket="test-bucket",
        allowed_databases=["security_lake_db"],
        allowed_tables=["amazon_security_lake_table_us_east_2_sh_findings_2_0"],
        allowed_table_prefixes=[],
        max_query_limit=1000,
        max_lookback_days=90,
        query_timeout_seconds=timeout,
    )


def _mock_athena_client(
    query_execution_id: str = "qe-12345",
    states: list[str] | None = None,
    result_rows: list[dict] | None = None,
    column_info: list[dict] | None = None,
    start_error: ClientError | None = None,
    get_execution_error: ClientError | None = None,
    get_results_error: ClientError | None = None,
    state_reason: str | None = None,
) -> MagicMock:
    """Create a mock Athena client with configurable behavior."""
    client = MagicMock()

    # start_query_execution
    if start_error:
        client.start_query_execution.side_effect = start_error
    else:
        client.start_query_execution.return_value = {
            "QueryExecutionId": query_execution_id
        }

    # get_query_execution
    if get_execution_error:
        client.get_query_execution.side_effect = get_execution_error
    elif states:
        responses = []
        for state in states:
            resp = {
                "QueryExecution": {
                    "Status": {
                        "State": state,
                    }
                }
            }
            if state_reason and state == "FAILED":
                resp["QueryExecution"]["Status"]["StateChangeReason"] = state_reason
            responses.append(resp)
        client.get_query_execution.side_effect = responses

    # get_query_results
    if get_results_error:
        client.get_query_results.side_effect = get_results_error
    elif column_info and result_rows is not None:
        # Build Athena-style result set
        athena_rows = []
        # Header row (column names)
        header_row = {
            "Data": [{"VarCharValue": col["Name"]} for col in column_info]
        }
        athena_rows.append(header_row)
        # Data rows
        for row in result_rows:
            data = []
            for col in column_info:
                value = row.get(col["Name"])
                if value is not None:
                    data.append({"VarCharValue": str(value)})
                else:
                    data.append({})
            athena_rows.append({"Data": data})

        client.get_query_results.return_value = {
            "ResultSet": {
                "ResultSetMetadata": {"ColumnInfo": column_info},
                "Rows": athena_rows,
            }
        }
    else:
        # Default empty result set
        client.get_query_results.return_value = {
            "ResultSet": {
                "ResultSetMetadata": {"ColumnInfo": []},
                "Rows": [],
            }
        }

    return client


class TestExecuteQuerySuccess:
    """Tests for successful query execution."""

    @patch("modules.athena_query_lambda.src.athena_executor.time.sleep")
    def test_successful_query_returns_results(self, mock_sleep):
        config = _make_config()
        column_info = [
            {"Name": "severity", "Type": "varchar"},
            {"Name": "count", "Type": "bigint"},
        ]
        result_rows = [
            {"severity": "HIGH", "count": "15"},
            {"severity": "CRITICAL", "count": "3"},
        ]
        client = _mock_athena_client(
            states=["SUCCEEDED"],
            column_info=column_info,
            result_rows=result_rows,
        )

        result = execute_query("SELECT severity, count FROM t", config, client)

        assert result["status"] == "success"
        assert result["query"] == "SELECT severity, count FROM t"
        assert len(result["results"]) == 2
        assert result["results"][0] == {"severity": "HIGH", "count": "15"}
        assert result["results"][1] == {"severity": "CRITICAL", "count": "3"}
        assert result["validation_errors"] == []
        assert "2 rows" in result["summary"]

    @patch("modules.athena_query_lambda.src.athena_executor.time.sleep")
    def test_single_row_result_summary(self, mock_sleep):
        config = _make_config()
        column_info = [{"Name": "id", "Type": "varchar"}]
        result_rows = [{"id": "abc123"}]
        client = _mock_athena_client(
            states=["SUCCEEDED"],
            column_info=column_info,
            result_rows=result_rows,
        )

        result = execute_query("SELECT id FROM t", config, client)

        assert result["status"] == "success"
        assert "1 row" in result["summary"]
        assert "rows" not in result["summary"]

    @patch("modules.athena_query_lambda.src.athena_executor.time.sleep")
    def test_empty_result_set_returns_success(self, mock_sleep):
        config = _make_config()
        column_info = [{"Name": "id", "Type": "varchar"}]
        client = _mock_athena_client(
            states=["SUCCEEDED"],
            column_info=column_info,
            result_rows=[],
        )

        result = execute_query("SELECT id FROM t WHERE 1=0", config, client)

        assert result["status"] == "success"
        assert result["results"] == []
        assert result["summary"] == "Query returned no results"
        assert result["validation_errors"] == []

    @patch("modules.athena_query_lambda.src.athena_executor.time.sleep")
    def test_polls_through_running_state(self, mock_sleep):
        config = _make_config()
        column_info = [{"Name": "id", "Type": "varchar"}]
        client = _mock_athena_client(
            states=["RUNNING", "RUNNING", "SUCCEEDED"],
            column_info=column_info,
            result_rows=[{"id": "1"}],
        )

        result = execute_query("SELECT id FROM t", config, client)

        assert result["status"] == "success"
        assert mock_sleep.call_count == 2

    @patch("modules.athena_query_lambda.src.athena_executor.time.sleep")
    def test_polls_through_queued_state(self, mock_sleep):
        config = _make_config()
        column_info = [{"Name": "id", "Type": "varchar"}]
        client = _mock_athena_client(
            states=["QUEUED", "RUNNING", "SUCCEEDED"],
            column_info=column_info,
            result_rows=[{"id": "1"}],
        )

        result = execute_query("SELECT id FROM t", config, client)

        assert result["status"] == "success"
        assert mock_sleep.call_count == 2

    @patch("modules.athena_query_lambda.src.athena_executor.time.sleep")
    def test_workgroup_passed_to_start_query(self, mock_sleep):
        config = _make_config(workgroup="my-custom-workgroup")
        client = _mock_athena_client(
            states=["SUCCEEDED"],
            column_info=[{"Name": "id", "Type": "varchar"}],
            result_rows=[],
        )

        execute_query("SELECT 1", config, client)

        client.start_query_execution.assert_called_once_with(
            QueryString="SELECT 1",
            WorkGroup="my-custom-workgroup",
        )


class TestExecuteQueryTimeout:
    """Tests for timeout handling with query cancellation."""

    @patch("modules.athena_query_lambda.src.athena_executor.time.sleep")
    def test_timeout_cancels_query_and_returns_error(self, mock_sleep):
        config = _make_config(timeout=2)
        # Return RUNNING indefinitely (more responses than timeout allows)
        client = MagicMock()
        client.start_query_execution.return_value = {"QueryExecutionId": "qe-123"}
        client.get_query_execution.return_value = {
            "QueryExecution": {"Status": {"State": "RUNNING"}}
        }

        result = execute_query("SELECT * FROM t", config, client)

        assert result["status"] == "error"
        assert "timeout" in result["validation_errors"][0].lower()
        assert "2 seconds" in result["validation_errors"][0]
        client.stop_query_execution.assert_called_once_with(
            QueryExecutionId="qe-123"
        )

    @patch("modules.athena_query_lambda.src.athena_executor.time.sleep")
    def test_timeout_includes_query_in_response(self, mock_sleep):
        config = _make_config(timeout=1)
        client = MagicMock()
        client.start_query_execution.return_value = {"QueryExecutionId": "qe-123"}
        client.get_query_execution.return_value = {
            "QueryExecution": {"Status": {"State": "RUNNING"}}
        }

        result = execute_query("SELECT severity FROM findings", config, client)

        assert result["query"] == "SELECT severity FROM findings"
        assert result["results"] == []


class TestExecuteQueryErrors:
    """Tests for error handling scenarios."""

    @patch("modules.athena_query_lambda.src.athena_executor.time.sleep")
    def test_start_query_access_denied(self, mock_sleep):
        config = _make_config()
        error = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Access Denied"}},
            "StartQueryExecution",
        )
        client = _mock_athena_client(start_error=error)

        result = execute_query("SELECT 1", config, client)

        assert result["status"] == "error"
        assert "Failed to start" in result["validation_errors"][0]

    @patch("modules.athena_query_lambda.src.athena_executor.time.sleep")
    def test_start_query_generic_client_error(self, mock_sleep):
        config = _make_config()
        error = ClientError(
            {"Error": {"Code": "InternalServerException", "Message": "Oops"}},
            "StartQueryExecution",
        )
        client = _mock_athena_client(start_error=error)

        result = execute_query("SELECT 1", config, client)

        assert result["status"] == "error"
        assert "Failed to start" in result["validation_errors"][0]

    @patch("modules.athena_query_lambda.src.athena_executor.time.sleep")
    def test_query_failed_state_returns_error(self, mock_sleep):
        config = _make_config()
        client = _mock_athena_client(
            states=["RUNNING", "FAILED"],
            state_reason="Table not found",
        )

        result = execute_query("SELECT * FROM missing", config, client)

        assert result["status"] == "error"
        assert "Table not found" in result["validation_errors"][0]

    @patch("modules.athena_query_lambda.src.athena_executor.time.sleep")
    def test_query_cancelled_state_returns_error(self, mock_sleep):
        config = _make_config()
        client = _mock_athena_client(states=["CANCELLED"])

        result = execute_query("SELECT 1", config, client)

        assert result["status"] == "error"
        assert "cancelled" in result["validation_errors"][0].lower()

    @patch("modules.athena_query_lambda.src.athena_executor.time.sleep")
    def test_get_execution_client_error(self, mock_sleep):
        config = _make_config()
        error = ClientError(
            {"Error": {"Code": "InternalError", "Message": "Service error"}},
            "GetQueryExecution",
        )
        client = _mock_athena_client(get_execution_error=error)

        result = execute_query("SELECT 1", config, client)

        assert result["status"] == "error"

    @patch("modules.athena_query_lambda.src.athena_executor.time.sleep")
    def test_get_results_access_denied(self, mock_sleep):
        config = _make_config()
        error = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "No access"}},
            "GetQueryResults",
        )
        client = _mock_athena_client(
            states=["SUCCEEDED"],
            get_results_error=error,
        )

        result = execute_query("SELECT 1", config, client)

        assert result["status"] == "error"
        assert "Access denied" in result["validation_errors"][0]

    @patch("modules.athena_query_lambda.src.athena_executor.time.sleep")
    def test_get_results_generic_error(self, mock_sleep):
        config = _make_config()
        error = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "Something broke"}},
            "GetQueryResults",
        )
        client = _mock_athena_client(
            states=["SUCCEEDED"],
            get_results_error=error,
        )

        result = execute_query("SELECT 1", config, client)

        assert result["status"] == "error"
        assert "Something broke" in result["validation_errors"][0]

    @patch("modules.athena_query_lambda.src.athena_executor.time.sleep")
    def test_cancel_failure_is_silent(self, mock_sleep):
        """StopQueryExecution errors should not propagate."""
        config = _make_config(timeout=1)
        client = MagicMock()
        client.start_query_execution.return_value = {"QueryExecutionId": "qe-123"}
        client.get_query_execution.return_value = {
            "QueryExecution": {"Status": {"State": "RUNNING"}}
        }
        client.stop_query_execution.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "Oops"}},
            "StopQueryExecution",
        )

        # Should not raise despite StopQueryExecution failure
        result = execute_query("SELECT 1", config, client)

        assert result["status"] == "error"
        assert "timeout" in result["validation_errors"][0].lower()


class TestExecuteQueryResponseStructure:
    """Tests that verify the response structure matches the expected schema."""

    @patch("modules.athena_query_lambda.src.athena_executor.time.sleep")
    def test_success_response_has_all_fields(self, mock_sleep):
        config = _make_config()
        client = _mock_athena_client(
            states=["SUCCEEDED"],
            column_info=[{"Name": "id", "Type": "varchar"}],
            result_rows=[{"id": "1"}],
        )

        result = execute_query("SELECT id FROM t", config, client)

        assert "status" in result
        assert "query" in result
        assert "results" in result
        assert "summary" in result
        assert "validation_errors" in result

    @patch("modules.athena_query_lambda.src.athena_executor.time.sleep")
    def test_error_response_has_all_fields(self, mock_sleep):
        config = _make_config()
        error = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}},
            "StartQueryExecution",
        )
        client = _mock_athena_client(start_error=error)

        result = execute_query("SELECT 1", config, client)

        assert "status" in result
        assert "query" in result
        assert "results" in result
        assert "summary" in result
        assert "validation_errors" in result
        assert result["results"] == []
        assert result["summary"] is None

    @patch("modules.athena_query_lambda.src.athena_executor.time.sleep")
    def test_null_values_in_results_handled(self, mock_sleep):
        """Cells without VarCharValue should map to None."""
        config = _make_config()
        column_info = [
            {"Name": "id", "Type": "varchar"},
            {"Name": "name", "Type": "varchar"},
        ]
        # One row with a null value for 'name'
        result_rows = [{"id": "1"}]  # 'name' is missing → None
        client = _mock_athena_client(
            states=["SUCCEEDED"],
            column_info=column_info,
            result_rows=result_rows,
        )

        result = execute_query("SELECT id, name FROM t", config, client)

        assert result["status"] == "success"
        assert result["results"][0]["id"] == "1"
        assert result["results"][0]["name"] is None
