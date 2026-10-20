variable "name_prefix" {
  description = "Prefix for resource naming"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "kb_role_arn" {
  description = "ARN of the Knowledge Base IAM role"
  type        = string
}

variable "kb_docs_bucket_arn" {
  description = "ARN of the Knowledge Base documents bucket"
  type        = string
}

variable "kb_docs_bucket_name" {
  description = "Name of the Knowledge Base documents bucket"
  type        = string
}

variable "embedding_model_id" {
  description = "Bedrock embedding model ID for vector embeddings"
  type        = string
  default     = "amazon.titan-embed-text-v2:0"
}

variable "chunking_max_tokens" {
  description = "Maximum number of tokens per chunk for fixed-size chunking strategy"
  type        = number
  default     = 512
}

variable "chunking_overlap_tokens" {
  description = "Number of overlap tokens between adjacent chunks (expressed as percentage for the provider)"
  type        = number
  default     = 64
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
