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
  description = "Base64 SHA-256 of the zip."
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

variable "queue_arn" {
  description = "Shard queue ARN."
  type        = string
}

variable "queue_url" {
  description = "Shard queue URL."
  type        = string
}

variable "ssm_parameter_arns" {
  description = "ARNs of the two SecureString parameters, built from their names."
  type        = list(string)
}

variable "qrypt_param_name" {
  description = "SSM name of the Qrypt token."
  type        = string
}

variable "api_key_param_name" {
  description = "SSM name of the bearer key."
  type        = string
}

variable "auth_type" {
  description = "BEARER or AWS_IAM."
  type        = string
}

variable "concurrency" {
  description = "Reserved concurrency when reserve_concurrency is true."
  type        = number
}

variable "reserve_concurrency" {
  description = "Whether to reserve concurrency for the api."
  type        = bool
}

variable "log_retention_days" {
  description = "Days to keep logs."
  type        = number
}

variable "max_paths" {
  description = "Paths limit per job."
  type        = number
}

variable "max_shards" {
  description = "Shards limit per job."
  type        = number
}

variable "max_paths_per_shard" {
  description = "Paths-per-shard limit."
  type        = number
}

variable "fault_injection" {
  description = "Whether the demo fail_shards field is accepted."
  type        = bool
}
