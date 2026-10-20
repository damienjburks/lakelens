output "knowledge_base_id" {
  description = "ID of the Bedrock Knowledge Base"
  value       = aws_bedrockagent_knowledge_base.this.id
}

output "knowledge_base_arn" {
  description = "ARN of the Bedrock Knowledge Base"
  value       = aws_bedrockagent_knowledge_base.this.arn
}

output "data_source_id" {
  description = "ID of the Knowledge Base S3 data source"
  value       = aws_bedrockagent_data_source.s3.data_source_id
}
