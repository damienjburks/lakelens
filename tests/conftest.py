"""Shared pytest fixtures and hypothesis strategies for property-based tests.

Provides:
- ValidatorConfig fixture with default test settings
- Custom hypothesis strategies for SQL generation (valid and invalid)
- Mocked boto3 Athena and Glue clients
- Hypothesis settings profile (max_examples=200, deadline=None)

Used by property-based tests in tasks 11.2–11.15.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import HealthCheck, settings, strategies as st

from modules.athena_query_lambda.src.config import ValidatorConfig


# ---------------------------------------------------------------------------
# Hypothesis settings profile: 200 examples per test, no deadline
# ---------------------------------------------------------------------------

settings.register_profile(
    "pbt",
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("pbt")


# ---------------------------------------------------------------------------
# Approved table/database constants for test strategies
# ---------------------------------------------------------------------------

APPROVED_TABLES = [
    "amazon_security_lake_table_us_east_2_sh_findings_2_0",
    "test_approved_table",
]
APPROVED_TABLE_PREFIXES = ["amazon_security_lake_table_"]
APPROVED_DATABASES = ["security_lake_db", "test_db"]
MAX_QUERY_LIMIT = 1000
MAX_LOOKBACK_DAYS = 90


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def validator_config() -> ValidatorConfig:
    """Create a ValidatorConfig with default test settings.

    Config matches the task specification:
    - allowed_tables: approved Security Lake table + test table
    - allowed_table_prefixes: ["amazon_security_lake_table_"]
    - allowed_databases: ["security_lake_db", "test_db"]
    - max_query_limit: 1000
    - max_lookback_days: 90
    - query_timeout_seconds: 60
    - athena_workgroup: "test-workgroup"
    - athena_output_s3_bucket: "test-results-bucket"
    """
    return ValidatorConfig(
        athena_workgroup="test-workgroup",
        athena_output_s3_bucket="test-results-bucket",
        allowed_databases=list(APPROVED_DATABASES),
        allowed_tables=list(APPROVED_TABLES),
        allowed_table_prefixes=list(APPROVED_TABLE_PREFIXES),
        max_query_limit=MAX_QUERY_LIMIT,
        max_lookback_days=MAX_LOOKBACK_DAYS,
        query_timeout_seconds=60,
    )


@pytest.fixture
def mock_athena_client() -> MagicMock:
    """Mocked boto3 Athena client for query execution tests.

    Provides mock responses for:
    - start_query_execution
    - get_query_execution
    - get_query_results
    - stop_query_execution
    """
    client = MagicMock()

    # Default: successful query execution
    client.start_query_execution.return_value = {
        "QueryExecutionId": "test-query-id-12345"
    }
    client.get_query_execution.return_value = {
        "QueryExecution": {
            "QueryExecutionId": "test-query-id-12345",
            "Status": {"State": "SUCCEEDED"},
            "Statistics": {"EngineExecutionTimeInMillis": 1234},
        }
    }
    client.get_query_results.return_value = {
        "ResultSet": {
            "Rows": [
                {"Data": [{"VarCharValue": "col1"}, {"VarCharValue": "col2"}]},
                {"Data": [{"VarCharValue": "val1"}, {"VarCharValue": "val2"}]},
            ],
            "ResultSetMetadata": {
                "ColumnInfo": [
                    {"Name": "col1", "Type": "varchar"},
                    {"Name": "col2", "Type": "varchar"},
                ]
            },
        }
    }
    client.stop_query_execution.return_value = {}

    return client


@pytest.fixture
def mock_glue_client() -> MagicMock:
    """Mocked boto3 Glue client for schema context tests.

    Provides a mock response for get_table with sample columns and partition keys.
    """
    client = MagicMock()

    client.get_table.return_value = {
        "Table": {
            "Name": "amazon_security_lake_table_us_east_2_sh_findings_2_0",
            "DatabaseName": "security_lake_db",
            "StorageDescriptor": {
                "Columns": [
                    {"Name": "time_dt", "Type": "timestamp"},
                    {"Name": "severity", "Type": "string"},
                    {"Name": "finding_type", "Type": "string"},
                    {"Name": "resource_uid", "Type": "string"},
                    {"Name": "account_uid", "Type": "string"},
                    {"Name": "region", "Type": "string"},
                    {"Name": "status", "Type": "string"},
                ]
            },
            "PartitionKeys": [
                {"Name": "region", "Type": "string"},
                {"Name": "accountid", "Type": "string"},
                {"Name": "eventday", "Type": "string"},
            ],
        }
    }

    return client


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def _recent_date_literal() -> st.SearchStrategy[str]:
    """Generate a date literal within the allowed lookback window."""
    now = datetime.now(timezone.utc)
    return st.integers(min_value=1, max_value=MAX_LOOKBACK_DAYS - 1).map(
        lambda days: (now - timedelta(days=days)).strftime("'%Y-%m-%d'")
    )


def _approved_table() -> st.SearchStrategy[str]:
    """Pick a table from the approved tables list."""
    return st.sampled_from(APPROVED_TABLES)


def _approved_database() -> st.SearchStrategy[str]:
    """Pick a database from the approved databases list."""
    return st.sampled_from(APPROVED_DATABASES)


def _column_name() -> st.SearchStrategy[str]:
    """Generate a plausible column name."""
    return st.sampled_from([
        "severity", "finding_type", "resource_uid", "account_uid",
        "region", "status", "time_dt", "compliance_status",
    ])


@st.composite
def valid_select_query(draw: st.DrawFn) -> str:
    """Generate valid SELECT queries with approved tables, time filters, and LIMIT.

    These queries should pass all validation steps:
    - SELECT statement
    - Approved table
    - Has time filter (time_dt)
    - Has LIMIT within [1, 1000]
    """
    table = draw(_approved_table())
    column = draw(_column_name())
    limit = draw(st.integers(min_value=1, max_value=MAX_QUERY_LIMIT))
    date_literal = draw(_recent_date_literal())

    # Choose from a few valid query patterns
    pattern = draw(st.integers(min_value=0, max_value=3))

    if pattern == 0:
        # Simple select with WHERE time filter
        return (
            f"SELECT {column} FROM {table} "
            f"WHERE time_dt >= {date_literal} "
            f"LIMIT {limit}"
        )
    elif pattern == 1:
        # Select with database prefix
        db = draw(_approved_database())
        return (
            f"SELECT {column} FROM {db}.{table} "
            f"WHERE time_dt >= {date_literal} "
            f"LIMIT {limit}"
        )
    elif pattern == 2:
        # Select * with multiple conditions
        return (
            f"SELECT * FROM {table} "
            f"WHERE time_dt >= {date_literal} "
            f"AND severity = 'HIGH' "
            f"LIMIT {limit}"
        )
    else:
        # Select with count (aggregate — no LIMIT required, but we include one)
        return (
            f"SELECT {column}, COUNT(*) FROM {table} "
            f"WHERE time_dt >= {date_literal} "
            f"GROUP BY {column} "
            f"LIMIT {limit}"
        )


@st.composite
def invalid_sql_with_forbidden_keywords(draw: st.DrawFn) -> str:
    """Generate SQL starting with forbidden keywords (DROP, DELETE, INSERT, etc.).

    These queries should be rejected at the statement safety step.
    """
    keyword = draw(st.sampled_from([
        "DROP", "DELETE", "INSERT", "UPDATE", "ALTER",
        "CREATE", "MERGE", "TRUNCATE", "UNLOAD", "MSCK", "CTAS",
    ]))

    # Vary the case to test case-insensitive matching
    case_variant = draw(st.sampled_from([
        keyword.upper(),
        keyword.lower(),
        keyword.capitalize(),
    ]))

    table = draw(_approved_table())

    # Generate different patterns for each keyword
    if keyword in ("DROP", "ALTER"):
        return f"{case_variant} TABLE {table}"
    elif keyword in ("DELETE", "TRUNCATE"):
        return f"{case_variant} FROM {table}"
    elif keyword == "INSERT":
        return f"{case_variant} INTO {table} VALUES (1, 2, 3)"
    elif keyword == "UPDATE":
        return f"{case_variant} {table} SET col = 'value'"
    elif keyword == "CREATE":
        return f"{case_variant} TABLE new_table (id INT)"
    elif keyword == "MERGE":
        return f"{case_variant} INTO {table} USING source ON id = id"
    elif keyword == "UNLOAD":
        return f"{case_variant} (SELECT * FROM {table}) TO 's3://bucket/'"
    elif keyword == "MSCK":
        return f"{case_variant} REPAIR TABLE {table}"
    elif keyword == "CTAS":
        return f"{case_variant} new_table AS SELECT * FROM {table}"
    else:
        return f"{case_variant} {table}"


@st.composite
def invalid_multiple_statements(draw: st.DrawFn) -> str:
    """Generate SQL with multiple statements separated by semicolons.

    A single trailing semicolon is allowed, but internal semicolons are not.
    """
    table = draw(_approved_table())
    date_literal = draw(_recent_date_literal())
    limit = draw(st.integers(min_value=1, max_value=MAX_QUERY_LIMIT))

    # Build two distinct statements separated by a semicolon
    first_stmt = (
        f"SELECT * FROM {table} "
        f"WHERE time_dt >= {date_literal} LIMIT {limit}"
    )

    second_pattern = draw(st.integers(min_value=0, max_value=2))
    if second_pattern == 0:
        second_stmt = f"SELECT COUNT(*) FROM {table} WHERE time_dt >= {date_literal}"
    elif second_pattern == 1:
        second_stmt = f"DROP TABLE {table}"
    else:
        second_stmt = f"DELETE FROM {table}"

    return f"{first_stmt}; {second_stmt}"


@st.composite
def invalid_sql_with_comments(draw: st.DrawFn) -> str:
    """Generate SQL containing -- or /* */ comments.

    Comments are not permitted regardless of their position.
    """
    table = draw(_approved_table())
    date_literal = draw(_recent_date_literal())
    limit = draw(st.integers(min_value=1, max_value=MAX_QUERY_LIMIT))

    comment_style = draw(st.integers(min_value=0, max_value=3))

    base_query = (
        f"SELECT * FROM {table} "
        f"WHERE time_dt >= {date_literal} LIMIT {limit}"
    )

    if comment_style == 0:
        # Single-line comment at end
        return f"{base_query} -- this is a comment"
    elif comment_style == 1:
        # Single-line comment before query
        return f"-- comment\n{base_query}"
    elif comment_style == 2:
        # Multi-line comment inline
        return (
            f"SELECT /* hidden */ * FROM {table} "
            f"WHERE time_dt >= {date_literal} LIMIT {limit}"
        )
    else:
        # Multi-line comment wrapping filter
        return (
            f"SELECT * FROM {table} "
            f"WHERE /* start */ time_dt >= {date_literal} /* end */ "
            f"LIMIT {limit}"
        )


@st.composite
def unapproved_table_name(draw: st.DrawFn) -> str:
    """Generate table names NOT in the approved list and NOT matching prefixes.

    Avoids names starting with 'amazon_security_lake_table_' (the approved prefix)
    and avoids the exact names in APPROVED_TABLES.
    """
    # Use a limited alphabet to produce identifiers that won't match prefixes
    name = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Ll",), whitelist_characters="_"),
        min_size=3,
        max_size=40,
    ).filter(
        lambda n: (
            n not in APPROVED_TABLES
            and not n.startswith("amazon_security_lake_table_")
            and n.isidentifier()
        )
    ))
    return name


@st.composite
def unapproved_database_name(draw: st.DrawFn) -> str:
    """Generate database names NOT in the approved databases list.

    Avoids the exact names in APPROVED_DATABASES.
    """
    name = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Ll",), whitelist_characters="_"),
        min_size=3,
        max_size=30,
    ).filter(
        lambda n: n not in APPROVED_DATABASES and n.isidentifier()
    ))
    return name


@st.composite
def valid_limit_value(draw: st.DrawFn) -> int:
    """Generate integers in [1, 1000] (valid LIMIT range)."""
    return draw(st.integers(min_value=1, max_value=MAX_QUERY_LIMIT))


@st.composite
def invalid_limit_value(draw: st.DrawFn) -> int:
    """Generate integers outside [1, 1000] (invalid LIMIT range).

    Produces either values <= 0 or values > MAX_QUERY_LIMIT.
    """
    return draw(st.one_of(
        st.integers(min_value=-10000, max_value=0),
        st.integers(min_value=MAX_QUERY_LIMIT + 1, max_value=100000),
    ))


@st.composite
def malformed_input(draw: st.DrawFn) -> str:
    """Generate malformed inputs: empty strings, random bytes, partial SQL.

    These should all fail closed at the parse step.
    """
    kind = draw(st.integers(min_value=0, max_value=4))

    if kind == 0:
        # Empty string
        return ""
    elif kind == 1:
        # Only whitespace
        return draw(st.text(
            alphabet=st.characters(whitelist_characters=" \t\n\r"),
            min_size=1,
            max_size=20,
        ))
    elif kind == 2:
        # Random bytes (non-SQL text)
        return draw(st.binary(min_size=1, max_size=50).map(
            lambda b: b.decode("utf-8", errors="replace")
        ))
    elif kind == 3:
        # Partial SQL fragments
        fragment = draw(st.sampled_from([
            "SELECT",
            "FROM",
            "WHERE",
            "LIMIT",
            "SELECT FROM",
            "SELECT * FROM",
            "(",
            ")",
            ";;;",
            "SELECT 'unclosed string",
        ]))
        return fragment
    else:
        # Random text that's not SQL
        return draw(st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "P")),
            min_size=1,
            max_size=100,
        ).filter(
            lambda t: not t.strip().upper().startswith("SELECT")
            and not t.strip().upper().startswith("WITH")
        ))
