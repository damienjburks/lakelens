"""Lambda handler entry point for the Bedrock Agent Action Group.

Parses Bedrock Agent action group event format, routes to the appropriate
operation handler, and returns structured JSON responses.
"""

import json
import uuid
from typing import Any

from config import ValidatorConfig
from schema_context import get_schema_context
from sql_validator import validate_query
from athena_executor import execute_query


# Operation route constants
ROUTE_GENERATE_AND_RUN_QUERY = "/generateAndRunAthenaQuery"
ROUTE_GET_SCHEMA_CONTEXT = "/getSecurityLakeSchemaContext"
ROUTE_EXPLAIN_QUERY_RESULTS = "/explainQueryResults"


def _generate_correlation_id() -> str:
    """Generate a UUID v4 correlation ID for log tracing."""
    return str(uuid.uuid4())


def _build_response(
    status: str,
    query: str | None = None,
    results: list[dict[str, Any]] | None = None,
    summary: str | None = None,
    validation_errors: list[str] | None = None,
) -> dict[str, Any]:
    """Build a structured JSON response.

    All Lambda responses follow a consistent schema with:
    - status: "success" or "error"
    - query: the executed SQL string or null
    - results: array of result rows or empty array
    - summary: descriptive text or null
    - validation_errors: array of validation failure descriptions or empty array
    """
    return {
        "status": status,
        "query": query,
        "results": results if results is not None else [],
        "summary": summary,
        "validation_errors": validation_errors if validation_errors is not None else [],
    }


def _extract_parameters(event: dict[str, Any]) -> dict[str, str]:
    """Extract parameters from Bedrock Agent action group event.

    Bedrock Agent events pass parameters as a list of objects with 'name' and 'value' keys.
    This converts them to a flat dictionary for easier access.
    """
    parameters = {}
    raw_params = event.get("parameters", [])
    if raw_params:
        for param in raw_params:
            name = param.get("name", "")
            value = param.get("value", "")
            if name:
                parameters[name] = value

    # Also check requestBody for parameters passed in the body
    request_body = event.get("requestBody", {})
    if request_body:
        content = request_body.get("content", {})
        app_json = content.get("application/json", {})
        properties = app_json.get("properties", [])
        if properties:
            for prop in properties:
                name = prop.get("name", "")
                value = prop.get("value", "")
                if name:
                    parameters[name] = value

    return parameters


def _build_bedrock_agent_response(
    event: dict[str, Any],
    status_code: int,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Build response in Bedrock Agent action group response format.

    The response format expected by Bedrock Agent includes the action group,
    API path, HTTP method, status code, and response body.
    """
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup", ""),
            "apiPath": event.get("apiPath", ""),
            "httpMethod": event.get("httpMethod", ""),
            "httpStatusCode": status_code,
            "responseBody": {
                "application/json": {
                    "body": json.dumps(body),
                }
            },
        },
    }


def _route_request(
    api_path: str,
    parameters: dict[str, str],
    correlation_id: str,
) -> dict[str, Any]:
    """Route the request to the appropriate operation handler.

    Returns a structured response dict with status, query, results, summary,
    and validation_errors fields.
    """
    if api_path == ROUTE_GENERATE_AND_RUN_QUERY:
        return _handle_generate_and_run_query(parameters, correlation_id)
    elif api_path == ROUTE_GET_SCHEMA_CONTEXT:
        return _handle_get_schema_context(parameters, correlation_id)
    elif api_path == ROUTE_EXPLAIN_QUERY_RESULTS:
        return _handle_explain_query_results(parameters, correlation_id)
    else:
        return _build_response(
            status="error",
            validation_errors=[
                f"Unknown operation: '{api_path}'. "
                "Permitted operations: /generateAndRunAthenaQuery, "
                "/getSecurityLakeSchemaContext, /explainQueryResults"
            ],
        )


def _handle_generate_and_run_query(
    parameters: dict[str, str],
    correlation_id: str,
) -> dict[str, Any]:
    """Handle the generateAndRunAthenaQuery operation.

    Validates the SQL query and executes it against Athena if valid.
    """
    query = parameters.get("query")
    if not query:
        return _build_response(
            status="error",
            validation_errors=["Missing required parameter: 'query'"],
        )

    # Load config
    try:
        config = ValidatorConfig.from_environment()
    except Exception as e:
        return _build_response(
            status="error",
            query=query,
            validation_errors=[f"Configuration error: {str(e)}"],
        )

    # Validate the SQL query
    validation_result = validate_query(query, config)
    if not validation_result.is_valid:
        return _build_response(
            status="error",
            query=query,
            validation_errors=validation_result.errors,
        )

    # Execute the validated query against Athena
    return execute_query(query, config)


def _handle_get_schema_context(
    parameters: dict[str, str],
    correlation_id: str,
) -> dict[str, Any]:
    """Handle the getSecurityLakeSchemaContext operation.

    Validates the table name against the approved list/prefixes and retrieves
    schema metadata from the AWS Glue Data Catalog.
    """
    table_name = parameters.get("table_name")
    if not table_name:
        return _build_response(
            status="error",
            validation_errors=["Missing required parameter: 'table_name'"],
        )

    try:
        config = ValidatorConfig.from_environment()
    except Exception as e:
        return _build_response(
            status="error",
            validation_errors=[f"Configuration error: {str(e)}"],
        )

    return get_schema_context(config=config, table_name=table_name)


def _handle_explain_query_results(
    parameters: dict[str, str],
    correlation_id: str,
) -> dict[str, Any]:
    """Handle the explainQueryResults operation.

    Returns query results with a description/summary.
    Placeholder implementation — full logic in tasks 5.4/5.5.
    """
    query = parameters.get("query")
    results_str = parameters.get("results")

    if not query:
        return _build_response(
            status="error",
            validation_errors=["Missing required parameter: 'query'"],
        )

    # Placeholder: will be replaced by full implementation
    return _build_response(
        status="error",
        query=query,
        validation_errors=["Explain query results not yet implemented"],
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point for Bedrock Agent action group invocations.

    Parses the Bedrock Agent event format, generates a correlation ID for
    log tracing, routes to the appropriate operation handler, and returns
    a structured response in the format Bedrock Agent expects.

    Args:
        event: Bedrock Agent action group event containing actionGroup,
               apiPath, httpMethod, parameters, etc.
        context: Lambda context object (unused but required by runtime).

    Returns:
        Structured response in Bedrock Agent action group response format.
    """
    correlation_id = _generate_correlation_id()

    # Extract routing information from the Bedrock Agent event
    api_path = event.get("apiPath", "")

    # Extract parameters from the event
    parameters = _extract_parameters(event)

    # Route to the appropriate handler
    response_body = _route_request(api_path, parameters, correlation_id)

    # Determine HTTP status code based on response status
    status_code = 200 if response_body.get("status") == "success" else 400

    # If this is an unknown operation, use 404
    if (
        response_body.get("status") == "error"
        and response_body.get("validation_errors")
        and any(
            "Unknown operation" in err
            for err in response_body["validation_errors"]
        )
    ):
        status_code = 404

    return _build_bedrock_agent_response(event, status_code, response_body)
