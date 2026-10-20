# S3 module - Knowledge Base documents bucket (conditional creation)
# If knowledge_base_bucket_name is provided, skip bucket creation (bring-your-own-bucket).
# Otherwise, create a new bucket with encryption, public access block, and TLS-only policy.

locals {
  create_bucket = var.knowledge_base_bucket_name == null
  bucket_name   = local.create_bucket ? "${var.name_prefix}-kb-docs-${var.environment}" : var.knowledge_base_bucket_name
}

# -----------------------------------------------------------------------------
# S3 Bucket — Created only when no external bucket is provided
# -----------------------------------------------------------------------------
resource "aws_s3_bucket" "kb_docs" {
  count = local.create_bucket ? 1 : 0

  bucket = local.bucket_name

  tags = merge(var.tags, {
    Name = local.bucket_name
  })
}

# -----------------------------------------------------------------------------
# Server-Side Encryption — AES-256
# -----------------------------------------------------------------------------
resource "aws_s3_bucket_server_side_encryption_configuration" "kb_docs" {
  count = local.create_bucket ? 1 : 0

  bucket = aws_s3_bucket.kb_docs[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# -----------------------------------------------------------------------------
# Public Access Block — All four settings enabled
# -----------------------------------------------------------------------------
resource "aws_s3_bucket_public_access_block" "kb_docs" {
  count = local.create_bucket ? 1 : 0

  bucket = aws_s3_bucket.kb_docs[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# -----------------------------------------------------------------------------
# Bucket Policy — TLS-only access enforcement
# -----------------------------------------------------------------------------
resource "aws_s3_bucket_policy" "kb_docs_tls" {
  count = local.create_bucket ? 1 : 0

  bucket = aws_s3_bucket.kb_docs[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.kb_docs[0].arn,
          "${aws_s3_bucket.kb_docs[0].arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.kb_docs]
}
