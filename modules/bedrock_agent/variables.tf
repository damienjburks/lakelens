variable "name_prefix" {
  description = "Prefix for resource naming"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "bedrock_agent_role_arn" {
  description = "ARN of the Bedrock Agent IAM role"
  type        = string
}

variable "foundation_model_id" {
  description = "Bedrock foundation model ID"
  type        = string
}

variable "lambda_function_arn" {
  description = "ARN of the Lambda function"
  type        = string
}

variable "lambda_function_invoke_arn" {
  description = "Invoke ARN of the Lambda function"
  type        = string
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
