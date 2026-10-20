"""SQL Validation Pipeline for the Athena Query Lambda.

Implements an ordered 8-step validation pipeline that ensures all SQL queries
are safe, scoped to approved resources, and bounded in time/result size before
reaching Athena.

Pipeline Steps:
    1. Parse & Classify — identify SELECT, CTE+SELECT, or reject
    2. Statement Safety — reject forbidden keywords, comments, multiple statements
    3. Table Extraction — extract all referenced table names
    4. Database Validation — verify databases in approved list
    5. Table Validation — verify tables in approved list or match prefixes
    6. Limit Check — verify LIMIT exists for non-aggregate queries (1 ≤ limit ≤ MAX_QUERY_LIMIT)
    7. Time Filter Check — verify time filter on time-filterable tables
    8. Lookback Check — verify time range ≤ MAX_LOOKBACK_DAYS

The pipeline accumulates all validation errors and short-circuits on parse failure.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from config import ValidatorConfig


@dataclass
class ValidationResult:
    """Structured result of the SQL validation pipeline.

    Attributes:
        is_valid: True if the query passed all validation steps.
        errors: List of human-readable validation error messages.
        query: The original SQL query string that was validated.
    """

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    query: str = ""


def validate_query(sql: str, config: ValidatorConfig) -> ValidationResult:
    """Run the full SQL validation pipeline against a query.

    Processes the query through all 8 validation steps in order.
    Short-circuits on parse failure (step 1) since subsequent steps
    depend on a parseable statement. All other steps accumulate errors.

    Args:
        sql: The raw SQL query string to validate.
        config: ValidatorConfig instance with approved tables, databases, limits.

    Returns:
        ValidationResult with is_valid=True if all checks pass, otherwise
        is_valid=False with a list of specific error messages.
    """
    errors: list[str] = []

    # Step 1: Parse & Classify — short-circuit on failure
    parse_ok = _check_parse_and_classify(sql, errors)
    if not parse_ok:
        return ValidationResult(is_valid=False, errors=errors, query=sql)

    # Step 2: Statement Safety — forbidden keywords, comments, multiple statements
    _check_statement_safety(sql, errors, config)

    # Step 3: Table Extraction
    tables, databases = _extract_tables_and_databases(sql)

    # Step 4: Database Validation
    _check_databases(databases, config, errors)

    # Step 5: Table Validation
    _check_tables(tables, config, errors)

    # Step 6: Limit Check
    _check_limit(sql, config, errors)

    # Step 7: Time Filter Check
    _check_time_filter(sql, tables, config, errors)

    # Step 8: Lookback Check
    _check_lookback(sql, config, errors)

    is_valid = len(errors) == 0
    return ValidationResult(is_valid=is_valid, errors=errors, query=sql)


# ---------------------------------------------------------------------------
# Step 1: Parse & Classify
# ---------------------------------------------------------------------------

def _check_parse_and_classify(sql: str, errors: list[str]) -> bool:
    """Identify the statement as SELECT, CTE+SELECT, or reject.

    Returns True if the statement can be parsed and classified as a valid
    SELECT or CTE (WITH...AS) followed by SELECT. Returns False if the
    statement is unparseable or not a permitted statement type.
    """
    if not sql or not sql.strip():
        errors.append("Unable to parse SQL statement")
        return False

    cleaned = sql.strip()

    # Remove a single trailing semicolon for classification purposes
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()

    if not cleaned:
        errors.append("Unable to parse SQL statement")
        return False

    # Normalize whitespace for keyword detection
    normalized = re.sub(r"\s+", " ", cleaned).strip()
    upper = normalized.upper()

    # Check for CTE (WITH ... SELECT)
    if upper.startswith("WITH "):
        # Verify the final statement after the CTE is a SELECT
        if _cte_ends_with_select(upper):
            return True
        else:
            errors.append("Only SELECT statements are permitted")
            return False

    # Check for SELECT
    if upper.startswith("SELECT ") or upper == "SELECT":
        return True

    # Check if it starts with a forbidden keyword — will be caught in step 2
    # but here we mark it as a non-SELECT statement
    errors.append("Only SELECT statements are permitted")
    return False


def _cte_ends_with_select(upper_sql: str) -> bool:
    """Check that a CTE (WITH clause) ends with a SELECT statement.

    Uses a simple heuristic: find the last top-level SELECT keyword
    that isn't inside parentheses (i.e., not a subquery within the CTE definition).
    """
    # Find all occurrences of SELECT at the top level (outside parentheses)
    depth = 0
    last_select_pos = -1
    i = 0
    while i < len(upper_sql):
        if upper_sql[i] == "(":
            depth += 1
        elif upper_sql[i] == ")":
            depth -= 1
        elif depth == 0 and upper_sql[i:i + 7] == "SELECT " or (depth == 0 and upper_sql[i:i + 6] == "SELECT" and i + 6 == len(upper_sql)):
            last_select_pos = i
        i += 1

    # The final top-level SELECT should exist and not be at position 0
    # (position 0 would mean WITH wasn't actually there)
    return last_select_pos > 0


# ---------------------------------------------------------------------------
# Step 2: Statement Safety
# ---------------------------------------------------------------------------

def _check_statement_safety(sql: str, errors: list[str], config: ValidatorConfig) -> None:
    """Check for forbidden keywords, SQL comments, and multiple statements."""
    # Check for SQL comments
    if "--" in sql:
        errors.append("SQL comments are not permitted")
    if "/*" in sql or "*/" in sql:
        errors.append("SQL comments are not permitted")

    # Check for multiple statements (semicolons separating statements)
    _check_multiple_statements(sql, errors)

    # Check for forbidden keywords
    _check_forbidden_keywords(sql, errors, config)


def _check_multiple_statements(sql: str, errors: list[str]) -> None:
    """Reject queries with multiple statements separated by semicolons.

    A single trailing semicolon is permitted; internal semicolons indicate
    multiple statements and are rejected.
    """
    cleaned = sql.strip()

    # Remove a single trailing semicolon
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()

    # If there are still semicolons, we have multiple statements
    if ";" in cleaned:
        errors.append("Multiple SQL statements not permitted")


def _check_forbidden_keywords(
    sql: str, errors: list[str], config: ValidatorConfig
) -> None:
    """Reject queries containing forbidden keywords as statement initiators.

    Uses word-boundary matching to avoid false positives on column/table names
    that happen to contain forbidden words as substrings.
    """
    # Normalize the SQL for keyword checking
    normalized = re.sub(r"\s+", " ", sql.strip()).upper()

    for keyword in config.FORBIDDEN_KEYWORDS:
        # Match the keyword as a word boundary — it should appear as a standalone word
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, normalized):
            errors.append(f"Forbidden keyword '{keyword}' detected")


# ---------------------------------------------------------------------------
# Step 3: Table Extraction
# ---------------------------------------------------------------------------

def _extract_tables_and_databases(sql: str) -> tuple[list[str], list[str]]:
    """Extract all referenced table names and database names from the query.

    Handles patterns:
    - FROM table_name
    - FROM database.table_name
    - JOIN table_name
    - JOIN database.table_name

    CTE aliases (names defined in WITH clauses) are excluded from the
    returned table list since they are not real tables.

    Returns:
        Tuple of (table_names, database_names) with duplicates removed.
    """
    tables: list[str] = []
    databases: list[str] = []

    # Normalize whitespace
    normalized = re.sub(r"\s+", " ", sql.strip())

    # Extract CTE alias names to exclude them from table references
    cte_aliases = _extract_cte_aliases(normalized)

    # Match FROM and JOIN clauses (case-insensitive)
    # Pattern captures: optional_db.table_name or just table_name
    # Also handles backticks and double quotes around identifiers
    table_pattern = re.compile(
        r"(?:FROM|JOIN)\s+"
        r"(?:[`\"]?(\w+)[`\"]?\s*\.\s*)?"  # optional database name
        r"[`\"]?(\w+)[`\"]?"               # table name
        r"(?:\s+(?:AS\s+)?(\w+))?",         # optional alias
        re.IGNORECASE,
    )

    for match in table_pattern.finditer(normalized):
        db_name = match.group(1)
        table_name = match.group(2)

        if table_name:
            # Skip CTE aliases — they're not real tables
            if table_name.lower() not in cte_aliases:
                tables.append(table_name.lower())
        if db_name:
            databases.append(db_name.lower())

    # Deduplicate while preserving order
    tables = list(dict.fromkeys(tables))
    databases = list(dict.fromkeys(databases))

    return tables, databases


def _extract_cte_aliases(normalized_sql: str) -> set[str]:
    """Extract CTE (Common Table Expression) alias names from a WITH clause.

    Parses patterns like:
        WITH alias1 AS (...), alias2 AS (...)
    and returns a set of the alias names in lowercase.
    """
    aliases: set[str] = set()

    # Match WITH clause CTE definitions: alias AS (
    cte_pattern = re.compile(
        r"\bWITH\b\s+(.+?)(?=\bSELECT\b)",
        re.IGNORECASE | re.DOTALL,
    )

    match = cte_pattern.search(normalized_sql)
    if not match:
        return aliases

    cte_section = match.group(1)

    # Extract alias names: each CTE is "alias_name AS ("
    alias_pattern = re.compile(
        r"(\w+)\s+AS\s*\(",
        re.IGNORECASE,
    )

    for alias_match in alias_pattern.finditer(cte_section):
        aliases.add(alias_match.group(1).lower())

    return aliases


# ---------------------------------------------------------------------------
# Step 4: Database Validation
# ---------------------------------------------------------------------------

def _check_databases(
    databases: list[str], config: ValidatorConfig, errors: list[str]
) -> None:
    """Verify all referenced databases are in the approved list."""
    if not databases:
        return

    allowed_lower = {db.lower() for db in config.allowed_databases}

    for db in databases:
        if db.lower() not in allowed_lower:
            errors.append(f"Database '{db}' is not in the approved databases list")


# ---------------------------------------------------------------------------
# Step 5: Table Validation
# ---------------------------------------------------------------------------

def _check_tables(
    tables: list[str], config: ValidatorConfig, errors: list[str]
) -> None:
    """Verify all tables are in approved list or match approved prefixes."""
    if not tables:
        return

    allowed_lower = {t.lower() for t in config.allowed_tables}
    prefixes_lower = [p.lower() for p in config.allowed_table_prefixes]

    for table in tables:
        table_lower = table.lower()
        if table_lower in allowed_lower:
            continue
        if any(table_lower.startswith(prefix) for prefix in prefixes_lower):
            continue
        errors.append(f"Table '{table}' is not in the approved tables list")


# ---------------------------------------------------------------------------
# Step 6: Limit Check
# ---------------------------------------------------------------------------

def _check_limit(sql: str, config: ValidatorConfig, errors: list[str]) -> None:
    """Verify LIMIT clause exists for non-aggregate queries.

    Aggregate queries (containing GROUP BY, COUNT, SUM, AVG, MIN, MAX)
    are exempt from the LIMIT requirement.
    """
    normalized = re.sub(r"\s+", " ", sql.strip()).upper()

    # Check if this is an aggregate query
    if _is_aggregate_query(normalized):
        return

    # Look for LIMIT clause
    limit_match = re.search(r"\bLIMIT\s+(\d+)\b", normalized)

    if not limit_match:
        errors.append("Non-aggregate queries require a LIMIT clause")
        return

    limit_value = int(limit_match.group(1))

    if limit_value < 1:
        errors.append(f"LIMIT value {limit_value} is below minimum of 1")
    elif limit_value > config.max_query_limit:
        errors.append(
            f"LIMIT value {limit_value} exceeds maximum of {config.max_query_limit}"
        )


def _is_aggregate_query(upper_sql: str) -> bool:
    """Determine if a query is an aggregate query.

    A query is aggregate if it contains GROUP BY or aggregate functions
    (COUNT, SUM, AVG, MIN, MAX) used as function calls.
    """
    # Check for GROUP BY
    if re.search(r"\bGROUP\s+BY\b", upper_sql):
        return True

    # Check for aggregate functions (must be followed by open paren to be a function call)
    aggregate_functions = ["COUNT", "SUM", "AVG", "MIN", "MAX"]
    for func in aggregate_functions:
        if re.search(r"\b" + func + r"\s*\(", upper_sql):
            return True

    return False


# ---------------------------------------------------------------------------
# Step 7: Time Filter Check
# ---------------------------------------------------------------------------

def _check_time_filter(
    sql: str,
    tables: list[str],
    config: ValidatorConfig,
    errors: list[str],
) -> None:
    """Verify time filter presence on time-filterable tables.

    All tables in the approved list or matching prefixes are time-filterable
    and require a WHERE condition on a recognized time column.
    """
    if not tables:
        return

    # Determine which tables are time-filterable (all approved tables)
    allowed_lower = {t.lower() for t in config.allowed_tables}
    prefixes_lower = [p.lower() for p in config.allowed_table_prefixes]

    time_filterable_tables = []
    for table in tables:
        table_lower = table.lower()
        if table_lower in allowed_lower or any(
            table_lower.startswith(p) for p in prefixes_lower
        ):
            time_filterable_tables.append(table)

    if not time_filterable_tables:
        return

    # Check if any recognized time column appears in a WHERE clause
    normalized = re.sub(r"\s+", " ", sql.strip())

    has_time_filter = False
    for col in config.TIME_COLUMNS:
        # Look for time column referenced after WHERE or AND/OR
        pattern = re.compile(
            r"\bWHERE\b.*\b" + re.escape(col) + r"\b"
            + r"|\bAND\b.*\b" + re.escape(col) + r"\b"
            + r"|\bOR\b.*\b" + re.escape(col) + r"\b",
            re.IGNORECASE | re.DOTALL,
        )
        if pattern.search(normalized):
            has_time_filter = True
            break

    if not has_time_filter:
        errors.append(
            "Query missing required time filter on recognized time column"
        )


# ---------------------------------------------------------------------------
# Step 8: Lookback Check
# ---------------------------------------------------------------------------

def _check_lookback(
    sql: str, config: ValidatorConfig, errors: list[str]
) -> None:
    """Verify time range does not exceed MAX_LOOKBACK_DAYS.

    Extracts date/timestamp literals from the query and checks that the
    earliest referenced date is within MAX_LOOKBACK_DAYS of today.
    """
    now = datetime.now(timezone.utc)

    # Find date literals in various formats
    # ISO format: 2024-01-15, 2024-01-15T10:30:00
    date_pattern = re.compile(
        r"'(\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}:\d{2})?(?:\.\d+)?(?:Z)?)'",
    )

    dates_found: list[datetime] = []
    for match in date_pattern.finditer(sql):
        date_str = match.group(1)
        parsed = _parse_date(date_str)
        if parsed:
            dates_found.append(parsed)

    # Also check for date() or timestamp() function calls
    func_date_pattern = re.compile(
        r"(?:date|timestamp)\s*\(\s*'(\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}:\d{2})?(?:\.\d+)?(?:Z)?)'\s*\)",
        re.IGNORECASE,
    )
    for match in func_date_pattern.finditer(sql):
        date_str = match.group(1)
        parsed = _parse_date(date_str)
        if parsed:
            dates_found.append(parsed)

    # Also check for current_date/current_timestamp - interval patterns
    interval_pattern = re.compile(
        r"(?:current_date|current_timestamp|now\(\))\s*-\s*interval\s+'(\d+)'\s+day",
        re.IGNORECASE,
    )
    for match in interval_pattern.finditer(sql):
        days = int(match.group(1))
        if days > config.max_lookback_days:
            errors.append(
                f"Time range exceeds maximum lookback of {config.max_lookback_days} days"
            )
            return

    if not dates_found:
        return

    # Find the earliest date and check against max lookback
    earliest = min(dates_found)
    days_diff = (now - earliest).days

    if days_diff > config.max_lookback_days:
        errors.append(
            f"Time range exceeds maximum lookback of {config.max_lookback_days} days"
        )


def _parse_date(date_str: str) -> datetime | None:
    """Parse a date string into a datetime object.

    Supports formats:
    - 2024-01-15
    - 2024-01-15T10:30:00
    - 2024-01-15 10:30:00
    - 2024-01-15T10:30:00Z
    - 2024-01-15T10:30:00.000
    """
    formats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
