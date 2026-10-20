variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-2"
}

variable "environment" {
  description = "Deployment environment (e.g. dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "name_prefix" {
  description = "Prefix for resource naming"
  type        = string
  default     = "security-lake-bedrock"
}

variable "bedrock_foundation_model_id" {
  description = "Bedrock foundation model ID for the agent"
  type        = string
  default     = "arn:aws:bedrock:us-east-2:748355717020:inference-profile/us.anthropic.claude-sonnet-4-6"
}

variable "security_lake_database_names" {
  description = "List of Security Lake Glue database names the agent is permitted to query"
  type        = list(string)
  default     = ["amazon_security_lake_glue_db_us_east_2"]
}

variable "allowed_security_lake_tables" {
  description = "List of Security Lake table names the agent is permitted to query"
  type        = list(string)
  default     = ["amazon_security_lake_table_us_east_2_sh_findings_2_0"]
}

variable "allowed_security_lake_table_prefixes" {
  description = "List of table name prefixes the agent is permitted to query"
  type        = list(string)
  default     = []
}

variable "athena_workgroup_name" {
  description = "Name of the existing Athena workgroup to use for query execution"
  type        = string
  default     = "primary"
}

variable "athena_output_bucket_name" {
  description = "Name of the existing S3 bucket for Athena query results"
  type        = string
  default     = "athena-query-results-748355717020-us-east-2-an"
}

variable "max_query_limit" {
  description = "Maximum LIMIT value allowed in non-aggregate queries"
  type        = number
  default     = 1000

  validation {
    condition     = var.max_query_limit >= 1 && var.max_query_limit <= 10000
    error_message = "max_query_limit must be between 1 and 10000."
  }
}

variable "max_lookback_days" {
  description = "Maximum number of days a query time filter can look back"
  type        = number
  default     = 90

  validation {
    condition     = var.max_lookback_days >= 1 && var.max_lookback_days <= 365
    error_message = "max_lookback_days must be between 1 and 365."
  }
}

variable "query_timeout_seconds" {
  description = "Maximum time in seconds for Athena query execution before cancellation"
  type        = number
  default     = 300

  validation {
    condition     = var.query_timeout_seconds >= 1 && var.query_timeout_seconds <= 900
    error_message = "query_timeout_seconds must be between 1 and 900."
  }
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention period in days for the Lambda function"
  type        = number
  default     = 90
}

variable "tags" {
  description = "Tags to apply to all taggable resources"
  type        = map(string)
  default     = {}
}
