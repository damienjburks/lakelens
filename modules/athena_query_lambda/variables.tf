variable "name_prefix" {
  description = "Prefix for resource naming"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "lambda_role_arn" {
  description = "ARN of the Lambda executor IAM role"
  type        = string
}

variable "athena_workgroup_name" {
  description = "Athena workgroup name"
  type        = string
}

variable "athena_output_bucket_name" {
  description = "Athena results bucket name"
  type        = string
}

variable "security_lake_databases" {
  description = "List of Security Lake database names"
  type        = list(string)
}

variable "allowed_tables" {
  description = "List of allowed Security Lake table names"
  type        = list(string)
}

variable "allowed_table_prefixes" {
  description = "List of allowed table name prefixes"
  type        = list(string)
  default     = []
}

variable "max_query_limit" {
  description = "Maximum LIMIT value for non-aggregate queries"
  type        = number
  default     = 1000
}

variable "max_lookback_days" {
  description = "Maximum lookback period in days"
  type        = number
  default     = 90
}

variable "query_timeout_seconds" {
  description = "Query execution timeout in seconds"
  type        = number
  default     = 60
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention in days"
  type        = number
  default     = 90
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
