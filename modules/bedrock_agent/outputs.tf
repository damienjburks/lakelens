output "agent_id" {
  description = "ID of the Bedrock Agent"
  value       = aws_bedrockagent_agent.this.agent_id
}

output "agent_arn" {
  description = "ARN of the Bedrock Agent"
  value       = aws_bedrockagent_agent.this.agent_arn
}

output "agent_alias_id" {
  description = "ID of the Bedrock Agent alias"
  value       = aws_bedrockagent_agent_alias.this.agent_alias_id
}
