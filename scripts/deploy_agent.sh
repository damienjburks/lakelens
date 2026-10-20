#!/bin/bash
# Deploy script: applies Terraform, prepares the agent, and updates the alias
# to point to the latest version.
#
# Usage: ./scripts/deploy_agent.sh

set -euo pipefail

REGION="us-east-2"

echo "==> Running terraform apply..."
terraform apply -auto-approve

AGENT_ID=$(terraform output -raw bedrock_agent_id)
ALIAS_ID=$(terraform output -raw bedrock_agent_alias_id)

echo "==> Preparing agent ${AGENT_ID}..."
aws bedrock-agent prepare-agent --agent-id "$AGENT_ID" --region "$REGION"

echo "==> Waiting for agent to be prepared..."
sleep 15

echo "==> Creating new agent version..."
LATEST_VERSION=$(aws bedrock-agent create-agent-version \
  --agent-id "$AGENT_ID" \
  --region "$REGION" \
  --query "agentVersion.version" \
  --output text)

echo "==> Created version: ${LATEST_VERSION}"

echo "==> Latest version: ${LATEST_VERSION}"

# Get the alias name
ALIAS_NAME=$(aws bedrock-agent get-agent-alias \
  --agent-id "$AGENT_ID" \
  --agent-alias-id "$ALIAS_ID" \
  --region "$REGION" \
  --query "agentAlias.agentAliasName" \
  --output text)

echo "==> Updating alias ${ALIAS_ID} (${ALIAS_NAME}) to version ${LATEST_VERSION}..."
aws bedrock-agent update-agent-alias \
  --agent-id "$AGENT_ID" \
  --agent-alias-id "$ALIAS_ID" \
  --agent-alias-name "$ALIAS_NAME" \
  --routing-configuration "[{\"agentVersion\": \"${LATEST_VERSION}\"}]" \
  --region "$REGION"

echo "==> Done! Alias now points to version ${LATEST_VERSION}"
