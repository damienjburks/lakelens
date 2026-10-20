"""Configuration loader for the Athena Query Lambda Validator.

Reads all configuration from environment variables and validates at initialization.
Implements fail-closed behavior: raises ConfigurationError on any missing or invalid
environment variable, preventing the Lambda from processing requests in an
unconfigured state.
"""

import os
from dataclasses import dataclass, field
from typing import ClassVar


class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid.

    This error prevents the Lambda from operating in a misconfigured state,
    enforcing fail-closed behavior per Requirement 7.6.
    """

    pass


@dataclass(frozen=True)
class ValidatorConfig:
    """SQL Validator configuration loaded from environment variables.

    All instance fields are derived from Lambda environment variables set by
    Terraform. Class variables define static validation constants used by the
    SQL validation pipeline.

    Raises ConfigurationError at construction if any required value is missing
    or invalid — the Lambda will fail closed and return structured errors for
    all requests until the configuration is corrected.
    """

    # Instance fields from environment variables
    athena_workgroup: str
    athena_output_s3_bucket: str
    allowed_databases: list[str] = field(default_factory=list)
    allowed_tables: list[str] = field(default_factory=list)
    allowed_table_prefixes: list[str] = field(default_factory=list)
    max_query_limit: int = 1000
    max_lookback_days: int = 90
    query_timeout_seconds: int = 60

    # Class variables — static validation constants
    FORBIDDEN_KEYWORDS: ClassVar[set[str]] = {
        "DROP",
        "DELETE",
        "INSERT",
        "UPDATE",
        "ALTER",
        "CREATE",
        "MERGE",
        "TRUNCATE",
        "UNLOAD",
        "MSCK",
        "CTAS",
    }

    AGGREGATE_INDICATORS: ClassVar[set[str]] = {
        "GROUP BY",
        "COUNT",
        "SUM",
        "AVG",
        "MIN",
        "MAX",
    }

    TIME_COLUMNS: ClassVar[set[str]] = {
        "time_dt",
        "time",
        "metadata.product.time",
    }

    @classmethod
    def from_environment(cls) -> "ValidatorConfig":
        """Load and validate configuration from environment variables.

        Reads the following environment variables:
        - ATHENA_WORKGROUP (required, non-empty string)
        - ATHENA_OUTPUT_S3_BUCKET (required, non-empty string)
        - SECURITY_LAKE_DATABASES (required, comma-separated list)
        - ALLOWED_TABLES (required, comma-separated list)
        - ALLOWED_TABLE_PREFIXES (optional, comma-separated list, default empty)
        - MAX_QUERY_LIMIT (optional, integer 1–10000, default 1000)
        - MAX_LOOKBACK_DAYS (optional, integer 1–365, default 90)
        - QUERY_TIMEOUT_SECONDS (optional, integer 1–900, default 60)

        Returns:
            ValidatorConfig: Validated configuration instance.

        Raises:
            ConfigurationError: If any required variable is missing, empty,
                or contains an invalid value.
        """
        errors: list[str] = []

        # Required string variables
        athena_workgroup = cls._get_required_str("ATHENA_WORKGROUP", errors)
        athena_output_s3_bucket = cls._get_required_str(
            "ATHENA_OUTPUT_S3_BUCKET", errors
        )

        # Required list variables (comma-separated)
        allowed_databases = cls._get_required_list("SECURITY_LAKE_DATABASES", errors)
        allowed_tables = cls._get_required_list("ALLOWED_TABLES", errors)

        # Optional list variable (comma-separated, default empty)
        allowed_table_prefixes = cls._get_optional_list("ALLOWED_TABLE_PREFIXES")

        # Optional numeric variables with range validation
        max_query_limit = cls._get_optional_int(
            "MAX_QUERY_LIMIT", default=1000, min_val=1, max_val=10000, errors=errors
        )
        max_lookback_days = cls._get_optional_int(
            "MAX_LOOKBACK_DAYS", default=90, min_val=1, max_val=365, errors=errors
        )
        query_timeout_seconds = cls._get_optional_int(
            "QUERY_TIMEOUT_SECONDS", default=60, min_val=1, max_val=900, errors=errors
        )

        # Fail closed if any validation errors accumulated
        if errors:
            raise ConfigurationError(
                f"Lambda configuration invalid — fail closed. Errors: {'; '.join(errors)}"
            )

        return cls(
            athena_workgroup=athena_workgroup,
            athena_output_s3_bucket=athena_output_s3_bucket,
            allowed_databases=allowed_databases,
            allowed_tables=allowed_tables,
            allowed_table_prefixes=allowed_table_prefixes,
            max_query_limit=max_query_limit,
            max_lookback_days=max_lookback_days,
            query_timeout_seconds=query_timeout_seconds,
        )

    @staticmethod
    def _get_required_str(var_name: str, errors: list[str]) -> str:
        """Read a required non-empty string environment variable."""
        value = os.environ.get(var_name)
        if not value or not value.strip():
            errors.append(f"Required environment variable '{var_name}' is missing or empty")
            return ""
        return value.strip()

    @staticmethod
    def _get_required_list(var_name: str, errors: list[str]) -> list[str]:
        """Read a required comma-separated list environment variable.

        The variable must be present and contain at least one non-empty item.
        """
        value = os.environ.get(var_name)
        if not value or not value.strip():
            errors.append(f"Required environment variable '{var_name}' is missing or empty")
            return []
        items = [item.strip() for item in value.split(",") if item.strip()]
        if not items:
            errors.append(
                f"Environment variable '{var_name}' contains no valid items after parsing"
            )
            return []
        return items

    @staticmethod
    def _get_optional_list(var_name: str) -> list[str]:
        """Read an optional comma-separated list environment variable.

        Returns an empty list if the variable is not set or empty.
        """
        value = os.environ.get(var_name, "")
        if not value.strip():
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def _get_optional_int(
        var_name: str,
        default: int,
        min_val: int,
        max_val: int,
        errors: list[str],
    ) -> int:
        """Read an optional integer environment variable with range validation.

        Returns the default if the variable is not set. Appends to errors if the
        value cannot be parsed as an integer or is outside [min_val, max_val].
        """
        value = os.environ.get(var_name)
        if value is None or not value.strip():
            return default
        try:
            parsed = int(value.strip())
        except ValueError:
            errors.append(
                f"Environment variable '{var_name}' has invalid integer value: '{value}'"
            )
            return default
        if parsed < min_val or parsed > max_val:
            errors.append(
                f"Environment variable '{var_name}' value {parsed} is outside "
                f"allowed range [{min_val}, {max_val}]"
            )
            return default
        return parsed
