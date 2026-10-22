variable "name" {
  description = "Name prefix, qmc-<environment>."
  type        = string
}

variable "environment" {
  description = "Environment name, passed to the function."
  type        = string
}

variable "package_path" {
  description = "Path of the Lambda zip."
  type        = string
}

variable "package_hash" {
  description = "Base64 SHA-256 of the zip, so code changes redeploy and unchanged code does not."
  type        = string
}

variable "table_arn" {
  description = "DynamoDB table ARN."
  type        = string
}

variable "table_name" {
  description = "DynamoDB table name."
  type        = string
}

variable "concurrency" {
  description = "Queue trigger maximum concurrency, and reserved concurrency when reserve_concurrency is true."
  type        = number
}

variable "reserve_concurrency" {
  description = "Whether to reserve concurrency for the worker."
  type        = bool
}

variable "timeout_s" {
  description = "Worker timeout in seconds."
  type        = number
}

variable "max_receive_count" {
  description = "Attempts before a shard message moves to the dead-letter queue."
  type        = number
}

variable "log_retention_days" {
  description = "Days to keep logs."
  type        = number
}

variable "fault_injection" {
  description = "Whether the demo fail_shards field is honoured."
  type        = bool
}
