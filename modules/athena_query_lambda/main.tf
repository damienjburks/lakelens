# -----------------------------------------------------------------------------
# Athena Query Lambda Module
# SQL validator and query executor for the Bedrock Security Lake Agent
# -----------------------------------------------------------------------------

locals {
  function_name = "${var.name_prefix}-athena-query-${var.environment}"
  # Lambda timeout must exceed query_timeout_seconds to allow cleanup after
  # query cancellation (Requirement 7.3)
  lambda_timeout = var.query_timeout_seconds + 30
}

# -----------------------------------------------------------------------------
# Lambda Deployment Package
# -----------------------------------------------------------------------------

data "archive_file" "lambda_source" {
  type        = "zip"
  source_dir  = "${path.module}/src"
  output_path = "${path.module}/dist/lambda.zip"
}

# -----------------------------------------------------------------------------
# CloudWatch Log Group — configurable retention (Requirement 11.4)
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

# -----------------------------------------------------------------------------
# Lambda Function — Python 3.12, environment variables from config.py
# (Requirements 7.1, 7.2, 7.3)
# -----------------------------------------------------------------------------

resource "aws_lambda_function" "athena_query" {
  function_name    = local.function_name
  description      = "SQL validator and Athena query executor for Bedrock Security Lake Agent"
  role             = var.lambda_role_arn
  handler          = "lambda_handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = local.lambda_timeout
  filename         = data.archive_file.lambda_source.output_path
  source_code_hash = data.archive_file.lambda_source.output_base64sha256

  environment {
    variables = {
      ATHENA_WORKGROUP       = var.athena_workgroup_name
      ATHENA_OUTPUT_S3_BUCKET = var.athena_output_bucket_name
      SECURITY_LAKE_DATABASES = join(",", var.security_lake_databases)
      ALLOWED_TABLES          = join(",", var.allowed_tables)
      ALLOWED_TABLE_PREFIXES  = join(",", var.allowed_table_prefixes)
      MAX_QUERY_LIMIT         = tostring(var.max_query_limit)
      MAX_LOOKBACK_DAYS       = tostring(var.max_lookback_days)
      QUERY_TIMEOUT_SECONDS   = tostring(var.query_timeout_seconds)
    }
  }

  tags = var.tags

  depends_on = [aws_cloudwatch_log_group.lambda]
}

# -----------------------------------------------------------------------------
# Lambda Permission — allow Bedrock Agent invocation
# -----------------------------------------------------------------------------

resource "aws_lambda_permission" "bedrock" {
  statement_id  = "AllowBedrockAgentInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.athena_query.function_name
  principal     = "bedrock.amazonaws.com"
}
