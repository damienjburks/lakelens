locals {
  aws_account_id       = data.aws_caller_identity.current.account_id
  lambda_function_name = "${var.name_prefix}-athena-query-${var.environment}"
  lambda_function_arn  = "arn:aws:lambda:${var.aws_region}:${local.aws_account_id}:function:${local.lambda_function_name}"
  common_tags = merge(var.tags, {
    Environment = var.environment
    ManagedBy   = "terraform"
    Module      = "bedrock-security-lake-agent"
  })
}

data "aws_caller_identity" "current" {}

# -----------------------------------------------------------------------------
# IAM Module — Bedrock Agent and Lambda roles
# -----------------------------------------------------------------------------
module "iam" {
  source = "./modules/iam"

  name_prefix                 = var.name_prefix
  environment                 = var.environment
  aws_region                  = var.aws_region
  aws_account_id              = local.aws_account_id
  bedrock_foundation_model_id = var.bedrock_foundation_model_id
  lambda_function_arn         = local.lambda_function_arn
  athena_workgroup_name       = var.athena_workgroup_name
  athena_output_bucket_name   = var.athena_output_bucket_name
  tags                        = local.common_tags
}

# -----------------------------------------------------------------------------
# Athena Query Lambda Module — SQL validator and query executor
# -----------------------------------------------------------------------------
module "athena_query_lambda" {
  source = "./modules/athena_query_lambda"

  name_prefix           = var.name_prefix
  environment           = var.environment
  lambda_role_arn       = module.iam.lambda_role_arn
  athena_workgroup_name = var.athena_workgroup_name
  athena_output_bucket_name = var.athena_output_bucket_name
  security_lake_databases   = var.security_lake_database_names
  allowed_tables            = var.allowed_security_lake_tables
  allowed_table_prefixes    = var.allowed_security_lake_table_prefixes
  max_query_limit           = var.max_query_limit
  max_lookback_days         = var.max_lookback_days
  query_timeout_seconds     = var.query_timeout_seconds
  log_retention_days        = var.log_retention_days
  tags                      = local.common_tags

  depends_on = [module.iam]
}

# -----------------------------------------------------------------------------
# Bedrock Agent Module — Agent, alias, action group
# -----------------------------------------------------------------------------
module "bedrock_agent" {
  source = "./modules/bedrock_agent"

  name_prefix            = var.name_prefix
  environment            = var.environment
  bedrock_agent_role_arn = module.iam.bedrock_agent_role_arn
  foundation_model_id    = var.bedrock_foundation_model_id
  lambda_function_arn    = module.athena_query_lambda.lambda_function_arn
  lambda_function_invoke_arn = module.athena_query_lambda.lambda_function_invoke_arn
  tags                   = local.common_tags

  depends_on = [module.athena_query_lambda, module.iam]
}
