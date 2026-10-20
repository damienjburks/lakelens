output "bedrock_agent_role_arn" {
  description = "ARN of the Bedrock Agent IAM role"
  value       = aws_iam_role.bedrock_agent.arn
}

output "lambda_role_arn" {
  description = "ARN of the Lambda executor IAM role"
  value       = aws_iam_role.lambda_executor.arn
}
