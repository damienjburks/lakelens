variable "name_prefix" {
  description = "Prefix for resource naming"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID"
  type        = string
}

variable "bedrock_foundation_model_id" {
  description = "Bedrock foundation model ID"
  type        = string
}

variable "lambda_function_arn" {
  description = "ARN of the Lambda function"
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

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
