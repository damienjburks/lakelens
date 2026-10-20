"""Unit tests for the Lambda handler entry point and router."""

import json
import uuid

import pytest

from modules.athena_query_lambda.src.lambda_handler import (
    ROUTE_EXPLAIN_QUERY_RESULTS,
    ROUTE_GENERATE_AND_RUN_QUERY,
    ROUTE_GET_SCHEMA_CONTEXT,
    _build_response,
    _extract_parameters,
    _generate_correlation_id,
    _route_request,
    lambda_handler,
)


class TestCorrelationId:
    """Tests for correlation ID generation."""

    def test_generates_valid_uuid4(self):
        cid = _generate_correlation_id()
        # Should be a valid UUID v4
        parsed = uuid.UUID(cid, version=4)
        assert str(parsed) == cid

    def test_generates_unique_ids(self):
        ids = {_generate_correlation_id() for _ in range(100)}
        assert len(ids) == 100


class TestBuildResponse:
    """Tests for the structured response builder."""

    def test_success_response_all_fields(self):
        resp = _build_response(
            status="success",
            query="SELECT * FROM t LIMIT 10",
            results=[{"col1": "val1"}],
            summary="Found 1 row",
            validation_errors=[],
        )
        assert resp["status"] == "success"
        assert resp["query"] == "SELECT * FROM t LIMIT 10"
        assert resp["results"] == [{"col1": "val1"}]
        assert resp["summary"] == "Found 1 row"
        assert resp["validation_errors"] == []

    def test_error_response_with_validation_errors(self):
        resp = _build_response(
            status="error",
            query="DROP TABLE t",
            validation_errors=["Forbidden keyword 'DROP' detected"],
        )
        assert resp["status"] == "error"
        assert resp["query"] == "DROP TABLE t"
        assert resp["results"] == []
        assert resp["summary"] is None
        assert resp["validation_errors"] == ["Forbidden keyword 'DROP' detected"]

    def test_defaults_results_to_empty_list(self):
        resp = _build_response(status="success")
        assert resp["results"] == []

    def test_defaults_validation_errors_to_empty_list(self):
        resp = _build_response(status="success")
        assert resp["validation_errors"] == []

    def test_defaults_query_to_none(self):
        resp = _build_response(status="error")
        assert resp["query"] is None

    def test_defaults_summary_to_none(self):
        resp = _build_response(status="error")
        assert resp["summary"] is None

    def test_response_has_all_required_fields(self):
        resp = _build_response(status="success")
        required_fields = {"status", "query", "results", "summary", "validation_errors"}
        assert set(resp.keys()) == required_fields


class TestExtractParameters:
    """Tests for parameter extraction from Bedrock Agent events."""

    def test_extracts_from_parameters_list(self):
        event = {
            "parameters": [
                {"name": "query", "value": "SELECT 1"},
                {"name": "database", "value": "mydb"},
            ]
        }
        params = _extract_parameters(event)
        assert params == {"query": "SELECT 1", "database": "mydb"}

    def test_extracts_from_request_body(self):
        event = {
            "requestBody": {
                "content": {
                    "application/json": {
                        "properties": [
                            {"name": "query", "value": "SELECT 1"},
                        ]
                    }
                }
            }
        }
        params = _extract_parameters(event)
        assert params == {"query": "SELECT 1"}

    def test_empty_event_returns_empty_dict(self):
        assert _extract_parameters({}) == {}

    def test_skips_empty_name_parameters(self):
        event = {
            "parameters": [
                {"name": "", "value": "ignored"},
                {"name": "valid", "value": "kept"},
            ]
        }
        params = _extract_parameters(event)
        assert params == {"valid": "kept"}

    def test_handles_none_parameters(self):
        event = {"parameters": None}
        params = _extract_parameters(event)
        assert params == {}


class TestRouteRequest:
    """Tests for the request router."""

    def test_routes_generate_and_run_query(self):
        result = _route_request(
            ROUTE_GENERATE_AND_RUN_QUERY,
            {"query": "SELECT 1"},
            "test-corr-id",
        )
        # Should route to handler (currently placeholder returns error)
        assert result["status"] == "error"
        assert result["query"] == "SELECT 1"

    def test_routes_get_schema_context(self):
        result = _route_request(
            ROUTE_GET_SCHEMA_CONTEXT,
            {"table_name": "my_table"},
            "test-corr-id",
        )
        assert result["status"] == "error"

    def test_routes_explain_query_results(self):
        result = _route_request(
            ROUTE_EXPLAIN_QUERY_RESULTS,
            {"query": "SELECT 1", "results": "[]"},
            "test-corr-id",
        )
        assert result["status"] == "error"
        assert result["query"] == "SELECT 1"

    def test_rejects_unknown_operation(self):
        result = _route_request("/unknownOperation", {}, "test-corr-id")
        assert result["status"] == "error"
        assert any("Unknown operation" in e for e in result["validation_errors"])
        assert "'/unknownOperation'" in result["validation_errors"][0]

    def test_rejects_empty_api_path(self):
        result = _route_request("", {}, "test-corr-id")
        assert result["status"] == "error"
        assert any("Unknown operation" in e for e in result["validation_errors"])

    def test_unknown_operation_lists_permitted_operations(self):
        result = _route_request("/badPath", {}, "test-corr-id")
        error_msg = result["validation_errors"][0]
        assert "/generateAndRunAthenaQuery" in error_msg
        assert "/getSecurityLakeSchemaContext" in error_msg
        assert "/explainQueryResults" in error_msg


class TestMissingParameters:
    """Tests for missing required parameters in each operation."""

    def test_generate_query_missing_query_param(self):
        result = _route_request(ROUTE_GENERATE_AND_RUN_QUERY, {}, "corr-id")
        assert result["status"] == "error"
        assert any("query" in e for e in result["validation_errors"])

    def test_get_schema_missing_table_name(self):
        result = _route_request(ROUTE_GET_SCHEMA_CONTEXT, {}, "corr-id")
        assert result["status"] == "error"
        assert any("table_name" in e for e in result["validation_errors"])

    def test_explain_results_missing_query(self):
        result = _route_request(ROUTE_EXPLAIN_QUERY_RESULTS, {}, "corr-id")
        assert result["status"] == "error"
        assert any("query" in e for e in result["validation_errors"])


class TestLambdaHandler:
    """Integration tests for the full lambda_handler function."""

    def _make_event(self, api_path, parameters=None):
        """Create a mock Bedrock Agent action group event."""
        event = {
            "actionGroup": "security-lake-query",
            "apiPath": api_path,
            "httpMethod": "POST",
            "parameters": parameters or [],
        }
        return event

    def test_returns_bedrock_agent_response_format(self):
        event = self._make_event("/generateAndRunAthenaQuery", [
            {"name": "query", "value": "SELECT 1"},
        ])
        result = lambda_handler(event, None)

        assert result["messageVersion"] == "1.0"
        assert "response" in result
        response = result["response"]
        assert response["actionGroup"] == "security-lake-query"
        assert response["apiPath"] == "/generateAndRunAthenaQuery"
        assert response["httpMethod"] == "POST"
        assert "httpStatusCode" in response
        assert "responseBody" in response

    def test_response_body_is_json_string(self):
        event = self._make_event("/generateAndRunAthenaQuery", [
            {"name": "query", "value": "SELECT 1"},
        ])
        result = lambda_handler(event, None)
        body_str = result["response"]["responseBody"]["application/json"]["body"]
        # Should be a valid JSON string
        body = json.loads(body_str)
        assert "status" in body
        assert "query" in body
        assert "results" in body
        assert "summary" in body
        assert "validation_errors" in body

    def test_unknown_operation_returns_404(self):
        event = self._make_event("/unknownPath")
        result = lambda_handler(event, None)
        assert result["response"]["httpStatusCode"] == 404

    def test_valid_route_returns_400_for_placeholder(self):
        # Current placeholder returns error, so should be 400
        event = self._make_event("/generateAndRunAthenaQuery", [
            {"name": "query", "value": "SELECT 1"},
        ])
        result = lambda_handler(event, None)
        assert result["response"]["httpStatusCode"] == 400

    def test_preserves_action_group_in_response(self):
        event = self._make_event("/getSecurityLakeSchemaContext", [
            {"name": "table_name", "value": "my_table"},
        ])
        result = lambda_handler(event, None)
        assert result["response"]["actionGroup"] == "security-lake-query"

    def test_handles_empty_event(self):
        result = lambda_handler({}, None)
        assert result["messageVersion"] == "1.0"
        assert result["response"]["httpStatusCode"] == 404
        body = json.loads(result["response"]["responseBody"]["application/json"]["body"])
        assert body["status"] == "error"
        assert any("Unknown operation" in e for e in body["validation_errors"])
