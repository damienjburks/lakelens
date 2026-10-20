"""Unit tests for the Lambda Validator configuration loader.

Tests cover:
- Successful loading from valid environment variables
- Fail-closed behavior on missing required variables
- Fail-closed behavior on invalid numeric values
- Parsing of comma-separated list variables
- Default values for optional variables
- Range validation for numeric variables
"""

import os
from unittest.mock import patch

import pytest

from modules.athena_query_lambda.src.config import ConfigurationError, ValidatorConfig


def _valid_env() -> dict[str, str]:
    """Return a complete set of valid environment variables."""
    return {
        "ATHENA_WORKGROUP": "primary",
        "ATHENA_OUTPUT_S3_BUCKET": "my-results-bucket",
        "SECURITY_LAKE_DATABASES": "security_lake_db",
        "ALLOWED_TABLES": "amazon_security_lake_table_us_east_2_sh_findings_2_0",
        "ALLOWED_TABLE_PREFIXES": "amazon_security_lake_table_",
        "MAX_QUERY_LIMIT": "1000",
        "MAX_LOOKBACK_DAYS": "90",
        "QUERY_TIMEOUT_SECONDS": "60",
    }


class TestFromEnvironmentSuccess:
    """Tests for successful configuration loading."""

    def test_loads_all_required_variables(self):
        with patch.dict(os.environ, _valid_env(), clear=True):
            config = ValidatorConfig.from_environment()

        assert config.athena_workgroup == "primary"
        assert config.athena_output_s3_bucket == "my-results-bucket"
        assert config.allowed_databases == ["security_lake_db"]
        assert config.allowed_tables == [
            "amazon_security_lake_table_us_east_2_sh_findings_2_0"
        ]
        assert config.allowed_table_prefixes == ["amazon_security_lake_table_"]
        assert config.max_query_limit == 1000
        assert config.max_lookback_days == 90
        assert config.query_timeout_seconds == 60

    def test_parses_multiple_databases(self):
        env = _valid_env()
        env["SECURITY_LAKE_DATABASES"] = "db_one, db_two, db_three"
        with patch.dict(os.environ, env, clear=True):
            config = ValidatorConfig.from_environment()

        assert config.allowed_databases == ["db_one", "db_two", "db_three"]

    def test_parses_multiple_tables(self):
        env = _valid_env()
        env["ALLOWED_TABLES"] = "table_a,table_b,table_c"
        with patch.dict(os.environ, env, clear=True):
            config = ValidatorConfig.from_environment()

        assert config.allowed_tables == ["table_a", "table_b", "table_c"]

    def test_strips_whitespace_from_list_items(self):
        env = _valid_env()
        env["ALLOWED_TABLES"] = "  table_a , table_b , table_c  "
        with patch.dict(os.environ, env, clear=True):
            config = ValidatorConfig.from_environment()

        assert config.allowed_tables == ["table_a", "table_b", "table_c"]

    def test_strips_whitespace_from_string_values(self):
        env = _valid_env()
        env["ATHENA_WORKGROUP"] = "  my-workgroup  "
        with patch.dict(os.environ, env, clear=True):
            config = ValidatorConfig.from_environment()

        assert config.athena_workgroup == "my-workgroup"

    def test_uses_defaults_when_optional_vars_missing(self):
        env = {
            "ATHENA_WORKGROUP": "primary",
            "ATHENA_OUTPUT_S3_BUCKET": "my-results-bucket",
            "SECURITY_LAKE_DATABASES": "security_lake_db",
            "ALLOWED_TABLES": "table_a",
        }
        with patch.dict(os.environ, env, clear=True):
            config = ValidatorConfig.from_environment()

        assert config.allowed_table_prefixes == []
        assert config.max_query_limit == 1000
        assert config.max_lookback_days == 90
        assert config.query_timeout_seconds == 60

    def test_empty_prefixes_returns_empty_list(self):
        env = _valid_env()
        env["ALLOWED_TABLE_PREFIXES"] = ""
        with patch.dict(os.environ, env, clear=True):
            config = ValidatorConfig.from_environment()

        assert config.allowed_table_prefixes == []

    def test_boundary_max_query_limit_min(self):
        env = _valid_env()
        env["MAX_QUERY_LIMIT"] = "1"
        with patch.dict(os.environ, env, clear=True):
            config = ValidatorConfig.from_environment()

        assert config.max_query_limit == 1

    def test_boundary_max_query_limit_max(self):
        env = _valid_env()
        env["MAX_QUERY_LIMIT"] = "10000"
        with patch.dict(os.environ, env, clear=True):
            config = ValidatorConfig.from_environment()

        assert config.max_query_limit == 10000

    def test_boundary_max_lookback_days_min(self):
        env = _valid_env()
        env["MAX_LOOKBACK_DAYS"] = "1"
        with patch.dict(os.environ, env, clear=True):
            config = ValidatorConfig.from_environment()

        assert config.max_lookback_days == 1

    def test_boundary_max_lookback_days_max(self):
        env = _valid_env()
        env["MAX_LOOKBACK_DAYS"] = "365"
        with patch.dict(os.environ, env, clear=True):
            config = ValidatorConfig.from_environment()

        assert config.max_lookback_days == 365

    def test_boundary_query_timeout_min(self):
        env = _valid_env()
        env["QUERY_TIMEOUT_SECONDS"] = "1"
        with patch.dict(os.environ, env, clear=True):
            config = ValidatorConfig.from_environment()

        assert config.query_timeout_seconds == 1

    def test_boundary_query_timeout_max(self):
        env = _valid_env()
        env["QUERY_TIMEOUT_SECONDS"] = "900"
        with patch.dict(os.environ, env, clear=True):
            config = ValidatorConfig.from_environment()

        assert config.query_timeout_seconds == 900


class TestFromEnvironmentFailClosed:
    """Tests for fail-closed behavior on invalid configuration."""

    def test_missing_athena_workgroup_raises(self):
        env = _valid_env()
        del env["ATHENA_WORKGROUP"]
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                ValidatorConfig.from_environment()

        assert "ATHENA_WORKGROUP" in str(exc_info.value)

    def test_empty_athena_workgroup_raises(self):
        env = _valid_env()
        env["ATHENA_WORKGROUP"] = "   "
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                ValidatorConfig.from_environment()

        assert "ATHENA_WORKGROUP" in str(exc_info.value)

    def test_missing_athena_output_bucket_raises(self):
        env = _valid_env()
        del env["ATHENA_OUTPUT_S3_BUCKET"]
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                ValidatorConfig.from_environment()

        assert "ATHENA_OUTPUT_S3_BUCKET" in str(exc_info.value)

    def test_missing_security_lake_databases_raises(self):
        env = _valid_env()
        del env["SECURITY_LAKE_DATABASES"]
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                ValidatorConfig.from_environment()

        assert "SECURITY_LAKE_DATABASES" in str(exc_info.value)

    def test_empty_security_lake_databases_raises(self):
        env = _valid_env()
        env["SECURITY_LAKE_DATABASES"] = "  ,  ,  "
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                ValidatorConfig.from_environment()

        assert "SECURITY_LAKE_DATABASES" in str(exc_info.value)

    def test_missing_allowed_tables_raises(self):
        env = _valid_env()
        del env["ALLOWED_TABLES"]
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                ValidatorConfig.from_environment()

        assert "ALLOWED_TABLES" in str(exc_info.value)

    def test_invalid_max_query_limit_non_integer_raises(self):
        env = _valid_env()
        env["MAX_QUERY_LIMIT"] = "not_a_number"
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                ValidatorConfig.from_environment()

        assert "MAX_QUERY_LIMIT" in str(exc_info.value)
        assert "invalid integer" in str(exc_info.value)

    def test_max_query_limit_below_range_raises(self):
        env = _valid_env()
        env["MAX_QUERY_LIMIT"] = "0"
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                ValidatorConfig.from_environment()

        assert "MAX_QUERY_LIMIT" in str(exc_info.value)
        assert "outside allowed range" in str(exc_info.value)

    def test_max_query_limit_above_range_raises(self):
        env = _valid_env()
        env["MAX_QUERY_LIMIT"] = "10001"
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                ValidatorConfig.from_environment()

        assert "MAX_QUERY_LIMIT" in str(exc_info.value)

    def test_max_lookback_days_below_range_raises(self):
        env = _valid_env()
        env["MAX_LOOKBACK_DAYS"] = "0"
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                ValidatorConfig.from_environment()

        assert "MAX_LOOKBACK_DAYS" in str(exc_info.value)

    def test_max_lookback_days_above_range_raises(self):
        env = _valid_env()
        env["MAX_LOOKBACK_DAYS"] = "366"
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                ValidatorConfig.from_environment()

        assert "MAX_LOOKBACK_DAYS" in str(exc_info.value)

    def test_query_timeout_below_range_raises(self):
        env = _valid_env()
        env["QUERY_TIMEOUT_SECONDS"] = "0"
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                ValidatorConfig.from_environment()

        assert "QUERY_TIMEOUT_SECONDS" in str(exc_info.value)

    def test_query_timeout_above_range_raises(self):
        env = _valid_env()
        env["QUERY_TIMEOUT_SECONDS"] = "901"
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                ValidatorConfig.from_environment()

        assert "QUERY_TIMEOUT_SECONDS" in str(exc_info.value)

    def test_multiple_errors_accumulated(self):
        """Multiple missing/invalid vars should all appear in the error message."""
        env = {
            "ALLOWED_TABLE_PREFIXES": "",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                ValidatorConfig.from_environment()

        error_msg = str(exc_info.value)
        assert "ATHENA_WORKGROUP" in error_msg
        assert "ATHENA_OUTPUT_S3_BUCKET" in error_msg
        assert "SECURITY_LAKE_DATABASES" in error_msg
        assert "ALLOWED_TABLES" in error_msg

    def test_negative_max_query_limit_raises(self):
        env = _valid_env()
        env["MAX_QUERY_LIMIT"] = "-5"
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                ValidatorConfig.from_environment()

        assert "MAX_QUERY_LIMIT" in str(exc_info.value)


class TestClassVariables:
    """Tests for the static class variable constants."""

    def test_forbidden_keywords_contains_expected(self):
        expected = {
            "DROP", "DELETE", "INSERT", "UPDATE", "ALTER",
            "CREATE", "MERGE", "TRUNCATE", "UNLOAD", "MSCK", "CTAS",
        }
        assert ValidatorConfig.FORBIDDEN_KEYWORDS == expected

    def test_aggregate_indicators_contains_expected(self):
        expected = {"GROUP BY", "COUNT", "SUM", "AVG", "MIN", "MAX"}
        assert ValidatorConfig.AGGREGATE_INDICATORS == expected

    def test_time_columns_contains_expected(self):
        expected = {"time_dt", "time", "metadata.product.time"}
        assert ValidatorConfig.TIME_COLUMNS == expected

    def test_config_is_frozen(self):
        """ValidatorConfig instances should be immutable."""
        with patch.dict(os.environ, _valid_env(), clear=True):
            config = ValidatorConfig.from_environment()

        with pytest.raises(Exception):
            config.athena_workgroup = "changed"  # type: ignore[misc]
