# -----------------------------------------------------------------------------
# Bedrock Knowledge Base Module
# Creates the Knowledge Base with Bedrock-managed vector store (OpenSearch
# Serverless), S3 data source, and uploads starter documentation.
# -----------------------------------------------------------------------------

locals {
  kb_name         = "${var.name_prefix}-security-kb-${var.environment}"
  collection_name = "${var.name_prefix}-kb-${var.environment}"

  # Calculate overlap percentage from token values
  # The provider expects overlap_percentage (0-99), so we calculate it from tokens
  overlap_percentage = min(floor((var.chunking_overlap_tokens / var.chunking_max_tokens) * 100), 99)

  # Discover all .md files in the docs/ directory for upload
  docs_path = "${path.module}/docs"
  doc_files = fileset(local.docs_path, "*.md")
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# -----------------------------------------------------------------------------
# OpenSearch Serverless — Bedrock-managed vector store
# When creating a Knowledge Base via the console with "Quick create", Bedrock
# provisions an OpenSearch Serverless collection. We replicate that here.
# -----------------------------------------------------------------------------

resource "aws_opensearchserverless_security_policy" "encryption" {
  name = local.collection_name
  type = "encryption"

  policy = jsonencode({
    Rules = [
      {
        Resource     = ["collection/${local.collection_name}"]
        ResourceType = "collection"
      }
    ]
    AWSOwnedKey = true
  })
}

resource "aws_opensearchserverless_security_policy" "network" {
  name = local.collection_name
  type = "network"

  policy = jsonencode([
    {
      Rules = [
        {
          Resource     = ["collection/${local.collection_name}"]
          ResourceType = "collection"
        }
      ]
      AllowFromPublic = true
    }
  ])
}

resource "aws_opensearchserverless_access_policy" "kb_access" {
  name = local.collection_name
  type = "data"

  policy = jsonencode([
    {
      Rules = [
        {
          Resource     = ["collection/${local.collection_name}"]
          ResourceType = "collection"
          Permission = [
            "aoss:CreateCollectionItems",
            "aoss:DeleteCollectionItems",
            "aoss:UpdateCollectionItems",
            "aoss:DescribeCollectionItems"
          ]
        },
        {
          Resource     = ["index/${local.collection_name}/*"]
          ResourceType = "index"
          Permission = [
            "aoss:CreateIndex",
            "aoss:DeleteIndex",
            "aoss:UpdateIndex",
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
            "aoss:WriteDocument"
          ]
        }
      ]
      Principal = [
        var.kb_role_arn,
        data.aws_caller_identity.current.arn
      ]
    }
  ])
}

resource "aws_opensearchserverless_collection" "kb_vector_store" {
  name = local.collection_name
  type = "VECTORSEARCH"

  tags = var.tags

  depends_on = [
    aws_opensearchserverless_security_policy.encryption,
    aws_opensearchserverless_security_policy.network,
    aws_opensearchserverless_access_policy.kb_access
  ]
}

# -----------------------------------------------------------------------------
# Bedrock Knowledge Base
# IMPORTANT: Before applying this resource, you must create the vector index
# on the OpenSearch Serverless collection. Run:
#   python3 scripts/create_opensearch_index.py
# See README.md for details.
# -----------------------------------------------------------------------------

resource "aws_bedrockagent_knowledge_base" "this" {
  name     = local.kb_name
  role_arn = var.kb_role_arn

  depends_on = [aws_opensearchserverless_collection.kb_vector_store]

  knowledge_base_configuration {
    type = "VECTOR"

    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/${var.embedding_model_id}"
    }
  }

  storage_configuration {
    type = "OPENSEARCH_SERVERLESS"

    opensearch_serverless_configuration {
      collection_arn    = aws_opensearchserverless_collection.kb_vector_store.arn
      vector_index_name = "bedrock-knowledge-base-default-index"

      field_mapping {
        vector_field   = "bedrock-knowledge-base-default-vector"
        text_field     = "AMAZON_BEDROCK_TEXT_CHUNK"
        metadata_field = "AMAZON_BEDROCK_METADATA"
      }
    }
  }

  tags = var.tags
}

# -----------------------------------------------------------------------------
# Bedrock Data Source — S3 bucket with starter documents
# -----------------------------------------------------------------------------

resource "aws_bedrockagent_data_source" "s3" {
  knowledge_base_id = aws_bedrockagent_knowledge_base.this.id
  name              = "${var.name_prefix}-kb-docs-${var.environment}"

  data_source_configuration {
    type = "S3"

    s3_configuration {
      bucket_arn = var.kb_docs_bucket_arn
    }
  }

  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = "FIXED_SIZE"

      fixed_size_chunking_configuration {
        max_tokens         = var.chunking_max_tokens
        overlap_percentage = local.overlap_percentage
      }
    }
  }
}

# -----------------------------------------------------------------------------
# Starter Documents — Upload all .md files from docs/ directory
# These 7 documents provide the Knowledge Base with security context:
#   1. security-lake-schema-overview.md
#   2. ocsf-field-mapping.md
#   3. athena-query-examples.md
#   4. security-investigation-playbook.md
#   5. mitre-control-mapping.md
#   6. cis-aws-foundations-mapping.md
#   7. nist-800-53-mapping.md
# -----------------------------------------------------------------------------

resource "aws_s3_object" "starter_docs" {
  for_each = local.doc_files

  bucket       = var.kb_docs_bucket_name
  key          = "knowledge-base-docs/${each.value}"
  source       = "${local.docs_path}/${each.value}"
  etag         = filemd5("${local.docs_path}/${each.value}")
  content_type = "text/markdown"

  tags = var.tags
}
