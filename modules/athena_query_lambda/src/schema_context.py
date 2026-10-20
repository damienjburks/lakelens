"""Schema context operation for Security Lake table metadata lookup.

Validates that the requested table is in the approved list or matches an
approved prefix, then retrieves schema metadata from the AWS Glue Data Catalog.

Implements Requirements 4.4 and 4.5:
- Return schema metadata for approved tables
- Return error for unapproved tables
"""

import boto3
from botocore.exceptions import ClientError
from typing import Any

from config import ValidatorConfig


def _is_table_approved(table_name: str, config: ValidatorConfig) -> bool:
    """Check if a table name is in the approved list or matches an approved prefix.

    Args:
        table_name: The table name to validate.
        config: ValidatorConfig containing allowed_tables and allowed_table_prefixes.

    Returns:
        True if the table is approved, False otherwise.
    """
    # Check exact match against allowed tables
    if table_name in config.allowed_tables:
        return True

    # Check prefix match against allowed table prefixes
    for prefix in config.allowed_table_prefixes:
        if table_name.startswith(prefix):
            return True

    return False


def get_schema_context(
    config: ValidatorConfig,
    table_name: str,
    glue_client: Any | None = None,
) -> dict[str, Any]:
    """Retrieve schema metadata for a Security Lake table.

    Validates the table name against the approved list/prefixes, then queries
    the AWS Glue Data Catalog for column names, types, and partition keys.

    Args:
        config: ValidatorConfig with allowed tables, prefixes, and databases.
        table_name: The table name to look up schema for.
        glue_client: Optional boto3 Glue client (for testing injection).
            If None, a new client is created.

    Returns:
        A structured response dict with:
        - status: "success" or "error"
        - results: schema metadata (on success) or empty list (on error)
        - validation_errors: list of error messages (on error) or empty list
    """
    # Validate table name against approved list/prefixes
    if not _is_table_approved(table_name, config):
        return {
            "status": "error",
            "query": None,
            "results": [],
            "summary": None,
            "validation_errors": [
                f"Table '{table_name}' is not in the approved tables list"
            ],
        }

    # Determine the database name for the Glue lookup
    # Use the first configured database as the default
    database_name = config.allowed_databases[0] if config.allowed_databases else ""

    if not database_name:
        return {
            "status": "error",
            "query": None,
            "results": [],
            "summary": None,
            "validation_errors": [
                "No database configured for schema lookup"
            ],
        }

    # Create Glue client if not provided (allows test injection)
    if glue_client is None:
        glue_client = boto3.client("glue")

    try:
        response = glue_client.get_table(
            DatabaseName=database_name,
            Name=table_name,
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))

        if error_code == "EntityNotFoundException":
            return {
                "status": "error",
                "query": None,
                "results": [],
                "summary": None,
                "validation_errors": [
                    f"Table '{table_name}' not found in Glue database '{database_name}'"
                ],
            }
        elif error_code == "AccessDeniedException":
            return {
                "status": "error",
                "query": None,
                "results": [],
                "summary": None,
                "validation_errors": [
                    f"Access denied when retrieving schema for table '{table_name}': {error_message}"
                ],
            }
        else:
            return {
                "status": "error",
                "query": None,
                "results": [],
                "summary": None,
                "validation_errors": [
                    f"Error retrieving schema for table '{table_name}': {error_code} - {error_message}"
                ],
            }

    # Extract schema metadata from the Glue response
    table_info = response.get("Table", {})
    storage_descriptor = table_info.get("StorageDescriptor", {})
    columns = storage_descriptor.get("Columns", [])
    partition_keys = table_info.get("PartitionKeys", [])

    # Format columns as list of {name, type}
    formatted_columns = [
        {"name": col.get("Name", ""), "type": col.get("Type", "")}
        for col in columns
    ]

    # Format partition keys as list of {name, type}
    formatted_partition_keys = [
        {"name": pk.get("Name", ""), "type": pk.get("Type", "")}
        for pk in partition_keys
    ]

    schema_metadata = {
        "table_name": table_name,
        "database_name": database_name,
        "columns": formatted_columns,
        "partition_keys": formatted_partition_keys,
    }

    return {
        "status": "success",
        "query": None,
        "results": [schema_metadata],
        "summary": f"Schema for table '{table_name}' with {len(formatted_columns)} columns and {len(formatted_partition_keys)} partition keys",
        "validation_errors": [],
    }
