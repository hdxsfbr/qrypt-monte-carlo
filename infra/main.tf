provider "aws" {
  region              = var.region
  allowed_account_ids = var.allowed_account_ids

  default_tags {
    tags = {
      project = "qrypt-monte-carlo"
      env     = var.environment
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  name       = "qmc-${var.environment}"
  account_id = data.aws_caller_identity.current.account_id

  # SSM parameter addresses built from the names only. Reading the parameters with the
  # aws_ssm_parameter data source would copy the secret values into Terraform state.
  ssm_arns = [
    for n in [var.qrypt_param_name, var.api_key_param_name] :
    "arn:aws:ssm:${var.region}:${local.account_id}:parameter/${trimprefix(n, "/")}"
  ]
}

# One zip of src/ (the qmc package and the handlers) for both functions. archive_file gives the
# same bytes for the same files, so an unchanged repo shows no drift.
data "archive_file" "lambda" {
  type             = "zip"
  source_dir       = "${path.root}/../src"
  output_path      = "${path.root}/../build/lambda.zip"
  output_file_mode = "0644"
  excludes         = ["**/__pycache__/**", "**/*.pyc"]
}

module "data" {
  source         = "./modules/data"
  name           = local.name
  table_capacity = var.table_capacity
  index_capacity = var.index_capacity
}

module "observability" {
  source            = "./modules/observability"
  name              = local.name
  region            = var.region
  alert_email       = var.alert_email
  worker_function   = module.workers.function_name
  api_function      = module.api.function_name
  dlq_name          = module.workers.dlq_name
  metrics_namespace = "QMC"
  environment       = var.environment
}

module "workers" {
  source              = "./modules/workers"
  name                = local.name
  package_path        = data.archive_file.lambda.output_path
  package_hash        = data.archive_file.lambda.output_base64sha256
  table_arn           = module.data.table_arn
  table_name          = module.data.table_name
  concurrency         = var.worker_concurrency
  reserve_concurrency = var.reserve_concurrency
  timeout_s           = var.worker_timeout_s
  max_receive_count   = var.max_receive_count
  log_retention_days  = var.log_retention_days
  fault_injection     = var.enable_fault_injection
  environment         = var.environment
}

module "api" {
  source              = "./modules/api"
  name                = local.name
  package_path        = data.archive_file.lambda.output_path
  package_hash        = data.archive_file.lambda.output_base64sha256
  table_arn           = module.data.table_arn
  table_name          = module.data.table_name
  queue_arn           = module.workers.queue_arn
  queue_url           = module.workers.queue_url
  ssm_parameter_arns  = local.ssm_arns
  qrypt_param_name    = var.qrypt_param_name
  api_key_param_name  = var.api_key_param_name
  auth_type           = var.api_auth_type
  concurrency         = var.api_concurrency
  reserve_concurrency = var.reserve_concurrency
  log_retention_days  = var.log_retention_days
  max_paths           = var.max_paths
  max_shards          = var.max_shards
  max_paths_per_shard = var.max_paths_per_shard
  fault_injection     = var.enable_fault_injection
  environment         = var.environment
}

module "budget" {
  source        = "./modules/budget"
  name          = local.name
  limit_usd     = var.budget_limit_usd
  alert_email   = var.alert_email
  sns_topic_arn = module.observability.topic_arn
}
