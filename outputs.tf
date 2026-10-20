output "bedrock_agent_id" {
  description = "The ID of the Bedrock Agent"
  value       = module.bedrock_agent.agent_id
}

output "bedrock_agent_arn" {
  description = "The ARN of the Bedrock Agent"
  value       = module.bedrock_agent.agent_arn
}

output "bedrock_agent_alias_id" {
  description = "The ID of the Bedrock Agent alias"
  value       = module.bedrock_agent.agent_alias_id
}

output "lambda_function_name" {
  description = "The name of the Lambda query validator function"
  value       = module.athena_query_lambda.lambda_function_name
}

output "lambda_function_arn" {
  description = "The ARN of the Lambda query validator function"
  value       = module.athena_query_lambda.lambda_function_arn
}

output "athena_output_bucket_name" {
  description = "The name of the Athena results S3 bucket (pass-through from input)"
  value       = var.athena_output_bucket_name
}
