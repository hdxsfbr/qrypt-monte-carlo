variable "name" {
  description = "Name prefix, qmc-<environment>."
  type        = string
}

variable "environment" {
  description = "Environment name; the custom metrics' dimension value."
  type        = string
}

variable "region" {
  description = "Region shown in dashboard widgets."
  type        = string
}

variable "alert_email" {
  description = "Address subscribed to the alerts topic."
  type        = string
}

variable "worker_function" {
  description = "Worker function name."
  type        = string
}

variable "api_function" {
  description = "Api function name."
  type        = string
}

variable "dlq_name" {
  description = "Dead-letter queue name."
  type        = string
}

variable "metrics_namespace" {
  description = "CloudWatch namespace of the custom metrics."
  type        = string
}
