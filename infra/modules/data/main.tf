# One table for jobs, shard results and rate-limit counters (docs/DESIGN.md section 4).
# Provisioned 10/10 plus 5/5 on the index = 15 of the 25 always-free capacity units.
resource "aws_dynamodb_table" "jobs" {
  #checkov:skip=CKV_AWS_119:Encrypted at rest with the AWS-owned key (the default). A customer key costs $1/month and adds KMS calls; the table holds no secrets.
  #checkov:skip=CKV2_AWS_16:Capacity is fixed at 15 of the 25 always-free units on purpose; auto scaling could raise it past the free allowance.
  #checkov:skip=CKV_AWS_28:Point-in-time recovery is billed per GB and not in the free tier. Every result can be recomputed from its stored seed.
  name                        = "${var.name}-jobs"
  billing_mode                = "PROVISIONED"
  read_capacity               = 10
  write_capacity              = 10
  hash_key                    = "pk"
  range_key                   = "sk"
  deletion_protection_enabled = false # terraform destroy must remove everything (EC-8)

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  attribute {
    name = "gsi1pk"
    type = "S"
  }

  attribute {
    name = "gsi1sk"
    type = "S"
  }

  global_secondary_index {
    name            = "by_created"
    projection_type = "ALL"
    read_capacity   = 5
    write_capacity  = 5

    key_schema {
      attribute_name = "gsi1pk"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "gsi1sk"
      key_type       = "RANGE"
    }
  }

  ttl {
    attribute_name = "ttl" # only rate-limit items carry it; they expire after about a minute
    enabled        = true
  }
}
