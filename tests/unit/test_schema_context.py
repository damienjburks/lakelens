"""Unit tests for the schema context operation.

Tests cover:
- Approved table validation (exact match and prefix match)
- Rejection of unapproved tables with structured error
- Successful schema metadata retrieval from Glue
- Graceful handling of Glue errors (EntityNotFound, AccessDenied)
- Correct formatting of columns and partition keys

Requirements: 4.4, 4.5
"""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from modules.athena_query_lambda.src.config import ValidatorConfig
from modules.athena_query_lambda.src.schema_context import (
    _is_table_approved,
    get_schema_context,
)


@pytest.fixture
def valid_config() -> ValidatorConfig:
    """Return a ValidatorConfig with standard test values."""
    return ValidatorConfig(
        athena_workgroup="primary",
        athena_output_s3_bucket="test-results-bucket",
        allowed_databases=["security_lake_db"],
        allowed_tables=[
            "amazon_security_lake_table_us_east_2_sh_findings_2_0",
            "another_approved_table",
        ],
        allowed_table_prefixes=["amazon_security_lake_table_"],
        max_query_limit=1000,
        max_lookback_days=90,
        query_timeout_seconds=60,
    )


@pytest.fixture
def mock_glue_client() -> MagicMock:
    """Return a mock Glue client."""
    return MagicMock()


@pytest.fixture
def glue_table_response() -> dict:
    """Return a sample Glue GetTable response."""
    return {
        "Table": {
            "Name": "amazon_security_lake_table_us_east_2_sh_findings_2_0",
            "DatabaseName": "security_lake_db",
            "StorageDescriptor": {
                "Columns": [
                    {"Name": "metadata", "Type": "struct<product:struct<name:string,version:string>>"},
                    {"Name": "severity_id", "Type": "int"},
                    {"Name": "severity", "Type": "string"},
                    {"Name": "finding_info", "Type": "struct<title:string,uid:string>"},
                    {"Name": "resources", "Type": "array<struct<uid:string,type:string>>"},
                    {"Name": "time", "Type": "bigint"},
                    {"Name": "time_dt", "Type": "timestamp"},
                ],
            },
            "PartitionKeys": [
                {"Name": "region", "Type": "string"},
                {"Name": "accountid", "Type": "string"},
                {"Name": "eventday", "Type": "string"},
            ],
        }
    }


class TestIsTableApproved:
    """Tests for the _is_table_approved helper."""

    def test_exact_match_returns_true(self, valid_config):
        assert _is_table_approved(
            "amazon_security_lake_table_us_east_2_sh_findings_2_0", valid_config
        ) is True

    def test_prefix_match_returns_true(self, valid_config):
        assert _is_table_approved(
            "amazon_security_lake_table_us_west_2_new_table", valid_config
        ) is True

    def test_unapproved_table_returns_false(self, valid_config):
        assert _is_table_approved("unauthorized_table", valid_config) is False

    def test_empty_string_returns_false(self, valid_config):
        assert _is_table_approved("", valid_config) is False

    def test_partial_name_no_prefix_match_returns_false(self, valid_config):
        assert _is_table_approved("amazon_security", valid_config) is False

    def test_second_approved_table_exact_match(self, valid_config):
        assert _is_table_approved("another_approved_table", valid_config) is True


class TestGetSchemaContextApprovedTable:
    """Tests for get_schema_context with approved tables."""

    def test_returns_success_for_approved_table(
        self, valid_config, mock_glue_client, glue_table_response
    ):
        mock_glue_client.get_table.return_value = glue_table_response

        result = get_schema_context(
            config=valid_config,
            table_name="amazon_security_lake_table_us_east_2_sh_findings_2_0",
            glue_client=mock_glue_client,
        )

        assert result["status"] == "success"
        assert result["validation_errors"] == []

    def test_returns_columns_with_name_and_type(
        self, valid_config, mock_glue_client, glue_table_response
    ):
        mock_glue_client.get_table.return_value = glue_table_response

        result = get_schema_context(
            config=valid_config,
            table_name="amazon_security_lake_table_us_east_2_sh_findings_2_0",
            glue_client=mock_glue_client,
        )

        schema = result["results"][0]
        assert schema["table_name"] == "amazon_security_lake_table_us_east_2_sh_findings_2_0"
        assert len(schema["columns"]) == 7
        assert schema["columns"][0] == {
            "name": "metadata",
            "type": "struct<product:struct<name:string,version:string>>",
        }
        assert schema["columns"][1] == {"name": "severity_id", "type": "int"}

    def test_returns_partition_keys(
        self, valid_config, mock_glue_client, glue_table_response
    ):
        mock_glue_client.get_table.return_value = glue_table_response

        result = get_schema_context(
            config=valid_config,
            table_name="amazon_security_lake_table_us_east_2_sh_findings_2_0",
            glue_client=mock_glue_client,
        )

        schema = result["results"][0]
        assert len(schema["partition_keys"]) == 3
        assert schema["partition_keys"][0] == {"name": "region", "type": "string"}
        assert schema["partition_keys"][1] == {"name": "accountid", "type": "string"}
        assert schema["partition_keys"][2] == {"name": "eventday", "type": "string"}

    def test_returns_database_name(
        self, valid_config, mock_glue_client, glue_table_response
    ):
        mock_glue_client.get_table.return_value = glue_table_response

        result = get_schema_context(
            config=valid_config,
            table_name="amazon_security_lake_table_us_east_2_sh_findings_2_0",
            glue_client=mock_glue_client,
        )

        schema = result["results"][0]
        assert schema["database_name"] == "security_lake_db"

    def test_returns_summary_with_counts(
        self, valid_config, mock_glue_client, glue_table_response
    ):
        mock_glue_client.get_table.return_value = glue_table_response

        result = get_schema_context(
            config=valid_config,
            table_name="amazon_security_lake_table_us_east_2_sh_findings_2_0",
            glue_client=mock_glue_client,
        )

        assert "7 columns" in result["summary"]
        assert "3 partition keys" in result["summary"]

    def test_calls_glue_with_correct_params(
        self, valid_config, mock_glue_client, glue_table_response
    ):
        mock_glue_client.get_table.return_value = glue_table_response

        get_schema_context(
            config=valid_config,
            table_name="amazon_security_lake_table_us_east_2_sh_findings_2_0",
            glue_client=mock_glue_client,
        )

        mock_glue_client.get_table.assert_called_once_with(
            DatabaseName="security_lake_db",
            Name="amazon_security_lake_table_us_east_2_sh_findings_2_0",
        )

    def test_prefix_matched_table_also_succeeds(
        self, valid_config, mock_glue_client, glue_table_response
    ):
        mock_glue_client.get_table.return_value = glue_table_response

        result = get_schema_context(
            config=valid_config,
            table_name="amazon_security_lake_table_us_west_2_vpc_flow",
            glue_client=mock_glue_client,
        )

        assert result["status"] == "success"


class TestGetSchemaContextUnapprovedTable:
    """Tests for get_schema_context with unapproved tables."""

    def test_returns_error_for_unapproved_table(self, valid_config, mock_glue_client):
        result = get_schema_context(
            config=valid_config,
            table_name="unauthorized_table",
            glue_client=mock_glue_client,
        )

        assert result["status"] == "error"
        assert len(result["validation_errors"]) == 1
        assert "not in the approved tables list" in result["validation_errors"][0]
        assert "unauthorized_table" in result["validation_errors"][0]

    def test_does_not_call_glue_for_unapproved_table(
        self, valid_config, mock_glue_client
    ):
        get_schema_context(
            config=valid_config,
            table_name="unauthorized_table",
            glue_client=mock_glue_client,
        )

        mock_glue_client.get_table.assert_not_called()

    def test_returns_empty_results_for_unapproved_table(
        self, valid_config, mock_glue_client
    ):
        result = get_schema_context(
            config=valid_config,
            table_name="unauthorized_table",
            glue_client=mock_glue_client,
        )

        assert result["results"] == []
        assert result["query"] is None
        assert result["summary"] is None


class TestGetSchemaContextGlueErrors:
    """Tests for get_schema_context handling Glue errors."""

    def test_handles_entity_not_found(self, valid_config, mock_glue_client):
        mock_glue_client.get_table.side_effect = ClientError(
            {"Error": {"Code": "EntityNotFoundException", "Message": "Table not found"}},
            "GetTable",
        )

        result = get_schema_context(
            config=valid_config,
            table_name="amazon_security_lake_table_us_east_2_sh_findings_2_0",
            glue_client=mock_glue_client,
        )

        assert result["status"] == "error"
        assert "not found" in result["validation_errors"][0]

    def test_handles_access_denied(self, valid_config, mock_glue_client):
        mock_glue_client.get_table.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Access denied to table"}},
            "GetTable",
        )

        result = get_schema_context(
            config=valid_config,
            table_name="amazon_security_lake_table_us_east_2_sh_findings_2_0",
            glue_client=mock_glue_client,
        )

        assert result["status"] == "error"
        assert "Access denied" in result["validation_errors"][0]

    def test_handles_unknown_glue_error(self, valid_config, mock_glue_client):
        mock_glue_client.get_table.side_effect = ClientError(
            {"Error": {"Code": "InternalServiceException", "Message": "Service failure"}},
            "GetTable",
        )

        result = get_schema_context(
            config=valid_config,
            table_name="amazon_security_lake_table_us_east_2_sh_findings_2_0",
            glue_client=mock_glue_client,
        )

        assert result["status"] == "error"
        assert "InternalServiceException" in result["validation_errors"][0]


class TestGetSchemaContextEdgeCases:
    """Tests for edge cases in get_schema_context."""

    def test_empty_columns_returns_success(self, valid_config, mock_glue_client):
        mock_glue_client.get_table.return_value = {
            "Table": {
                "Name": "amazon_security_lake_table_us_east_2_sh_findings_2_0",
                "StorageDescriptor": {"Columns": []},
                "PartitionKeys": [],
            }
        }

        result = get_schema_context(
            config=valid_config,
            table_name="amazon_security_lake_table_us_east_2_sh_findings_2_0",
            glue_client=mock_glue_client,
        )

        assert result["status"] == "success"
        assert result["results"][0]["columns"] == []
        assert result["results"][0]["partition_keys"] == []

    def test_no_databases_configured_returns_error(self, mock_glue_client):
        config = ValidatorConfig(
            athena_workgroup="primary",
            athena_output_s3_bucket="test-bucket",
            allowed_databases=[],
            allowed_tables=["my_table"],
            allowed_table_prefixes=[],
            max_query_limit=1000,
            max_lookback_days=90,
            query_timeout_seconds=60,
        )

        result = get_schema_context(
            config=config,
            table_name="my_table",
            glue_client=mock_glue_client,
        )

        assert result["status"] == "error"
        assert "No database configured" in result["validation_errors"][0]

    def test_response_has_all_required_fields_on_success(
        self, valid_config, mock_glue_client, glue_table_response
    ):
        mock_glue_client.get_table.return_value = glue_table_response

        result = get_schema_context(
            config=valid_config,
            table_name="amazon_security_lake_table_us_east_2_sh_findings_2_0",
            glue_client=mock_glue_client,
        )

        assert "status" in result
        assert "query" in result
        assert "results" in result
        assert "summary" in result
        assert "validation_errors" in result

    def test_response_has_all_required_fields_on_error(
        self, valid_config, mock_glue_client
    ):
        result = get_schema_context(
            config=valid_config,
            table_name="unauthorized_table",
            glue_client=mock_glue_client,
        )

        assert "status" in result
        assert "query" in result
        assert "results" in result
        assert "summary" in result
        assert "validation_errors" in result
