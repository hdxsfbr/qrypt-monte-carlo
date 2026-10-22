variable "region" {
  description = "AWS region. us-east-1 is closest to Qrypt's US East endpoint and is where Budgets live."
  type        = string
  default     = "us-east-1"
}

variable "allowed_account_ids" {
  description = "AWS accounts Terraform may touch. Stops a run that picked up the wrong CLI profile. Change it to deploy in another account."
  type        = list(string)
  default     = ["144249522427"]
}

variable "environment" {
  description = "Short environment name, used in resource names (qmc-<environment>-...)."
  type        = string
  default     = "dev"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,15}$", var.environment))
    error_message = "environment must be 1-16 lowercase letters, digits or hyphens, starting with a letter."
  }
}

variable "alert_email" {
  description = "Address that receives budget and alarm emails. Required, no default; AWS sends a confirmation link to it."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "alert_email must be an email address."
  }
}

variable "api_auth_type" {
  description = "BEARER: Function URL is public and the api checks a bearer key from SSM. AWS_IAM: callers must sign requests with AWS credentials."
  type        = string
  default     = "BEARER"

  validation {
    condition     = contains(["BEARER", "AWS_IAM"], var.api_auth_type)
    error_message = "api_auth_type must be BEARER or AWS_IAM."
  }
}

variable "qrypt_param_name" {
  description = "Name of the SSM SecureString holding the Qrypt token. Created out-of-band by scripts/put-secrets.sh; Terraform only uses the name."
  type        = string
  default     = "/qmc/dev/qrypt_api_key"
}

variable "api_key_param_name" {
  description = "Name of the SSM SecureString holding the bearer key callers must send. Created out-of-band."
  type        = string
  default     = "/qmc/dev/api_key"
}

variable "max_paths" {
  description = "Largest number of simulated paths one job may ask for."
  type        = number
  default     = 10000000
}

variable "max_shards" {
  description = "Largest number of shards (parallel pieces) one job may ask for."
  type        = number
  default     = 20
}

variable "max_paths_per_shard" {
  description = "Largest paths/shards ratio, so one shard stays far inside the worker timeout."
  type        = number
  default     = 500000
}

variable "api_concurrency" {
  description = "Reserved concurrency (copies running at once) for the api function, when reserve_concurrency is true."
  type        = number
  default     = 5
}

variable "worker_concurrency" {
  description = "Most worker copies the queue trigger may start at once; also the worker's reserved concurrency when reserve_concurrency is true. Use 5 while the account concurrency quota is 10."
  type        = number
  default     = 20

  validation {
    condition     = var.worker_concurrency >= 2 && var.worker_concurrency <= 1000
    error_message = "worker_concurrency must be between 2 and 1000 (SQS trigger limits)."
  }
}

variable "reserve_concurrency" {
  description = "Reserve concurrency for both functions. AWS needs 100 unreserved units, so set false while the account quota is 10."
  type        = bool
  default     = true
}

variable "worker_timeout_s" {
  description = "Worker function timeout in seconds."
  type        = number
  default     = 60
}

variable "max_receive_count" {
  description = "Attempts per shard message before SQS moves it to the dead-letter queue."
  type        = number
  default     = 3
}

variable "log_retention_days" {
  description = "Days to keep function logs."
  type        = number
  default     = 14
}

variable "budget_limit_usd" {
  description = "Monthly AWS Budget for the whole account, in US dollars."
  type        = number
  default     = 1
}

variable "enable_fault_injection" {
  description = "Demo switch: when true, a job may include fail_shards to make chosen shards fail on purpose. Off by default; when off the field is rejected."
  type        = bool
  default     = false
}
