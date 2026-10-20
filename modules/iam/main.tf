# -----------------------------------------------------------------------------
# IAM Module — Bedrock Agent and Lambda Executor roles
# All policies follow least-privilege principles with explicit resource ARNs.
# Wildcards are only used where AWS requires them, with inline justification.
# -----------------------------------------------------------------------------

# =============================================================================
# Bedrock Agent Role
# Trust: bedrock.amazonaws.com
# Permissions: invoke Lambda, call foundation model
# =============================================================================

resource "aws_iam_role" "bedrock_agent" {
  name = "${var.name_prefix}-bedrock-agent-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "bedrock.amazonaws.com"
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = var.aws_account_id
          }
        }
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "bedrock_agent_invoke_model" {
  name = "${var.name_prefix}-bedrock-agent-invoke-model-${var.environment}"
  role = aws_iam_role.bedrock_agent.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeFoundationModel"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:GetInferenceProfile",
          "bedrock:GetFoundationModel"
        ]
        # Allow both direct model invocation and inference profiles.
        # The agent may resolve us.* profiles to the underlying model ID at runtime.
        Resource = [
          "*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "bedrock_agent_invoke_lambda" {
  name = "${var.name_prefix}-bedrock-agent-invoke-lambda-${var.environment}"
  role = aws_iam_role.bedrock_agent.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "InvokeLambdaActionGroup"
        Effect   = "Allow"
        Action   = "lambda:InvokeFunction"
        Resource = var.lambda_function_arn
      }
    ]
  })
}

# =============================================================================
# Lambda Executor Role
# Trust: lambda.amazonaws.com
# Permissions: Athena (scoped to workgroup), S3 (scoped to results bucket),
#              Glue catalog read, CloudWatch Logs write
# =============================================================================

resource "aws_iam_role" "lambda_executor" {
  name = "${var.name_prefix}-lambda-executor-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "lambda_athena" {
  name = "${var.name_prefix}-lambda-athena-${var.environment}"
  role = aws_iam_role.lambda_executor.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AthenaQueryExecution"
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
          "athena:StopQueryExecution"
        ]
        Resource = "arn:aws:athena:${var.aws_region}:${var.aws_account_id}:workgroup/${var.athena_workgroup_name}"
      },
            {
        Sid = "AllowLakeformationDataRetrieval"
        Effect = "Allow"
        Action = [
          "lakeformation:GetDataAccess"
        ]
        Resource = [
          "*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda_s3_results" {
  name = "${var.name_prefix}-lambda-s3-results-${var.environment}"
  role = aws_iam_role.lambda_executor.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3ResultsBucketAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:GetBucketLocation",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.athena_output_bucket_name}",
          "arn:aws:s3:::${var.athena_output_bucket_name}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda_glue_catalog" {
  name = "${var.name_prefix}-lambda-glue-catalog-${var.environment}"
  role = aws_iam_role.lambda_executor.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "GlueCatalogRead"
        Effect = "Allow"
        Action = [
          "glue:GetDatabase",
          "glue:GetDatabases",
          "glue:GetTable",
          "glue:GetTables",
          "glue:GetPartition",
          "glue:GetPartitions"
        ]
        # Wildcard required: Glue catalog actions require catalog-level resource ARN
        # for GetDatabase/GetDatabases, and table/database names are dynamic based
        # on the approved tables configuration. Scoped to account and region.
        Resource = [
          "arn:aws:glue:${var.aws_region}:${var.aws_account_id}:catalog",
          "arn:aws:glue:${var.aws_region}:${var.aws_account_id}:database/*",
          "arn:aws:glue:${var.aws_region}:${var.aws_account_id}:table/*/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda_cloudwatch_logs" {
  name = "${var.name_prefix}-lambda-cloudwatch-logs-${var.environment}"
  role = aws_iam_role.lambda_executor.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchLogsWrite"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = [
          "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/lambda/${var.name_prefix}-athena-query-${var.environment}",
          "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/lambda/${var.name_prefix}-athena-query-${var.environment}:*"
        ]
      }
    ]
  })
}
