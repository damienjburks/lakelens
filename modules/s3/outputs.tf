output "kb_docs_bucket_name" {
  description = "Name of the Knowledge Base documents bucket"
  value       = local.create_bucket ? aws_s3_bucket.kb_docs[0].id : var.knowledge_base_bucket_name
}

output "kb_docs_bucket_arn" {
  description = "ARN of the Knowledge Base documents bucket"
  value       = local.create_bucket ? aws_s3_bucket.kb_docs[0].arn : "arn:aws:s3:::${var.knowledge_base_bucket_name}"
}
