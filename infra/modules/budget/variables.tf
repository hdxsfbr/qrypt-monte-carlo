variable "name" {
  description = "Name prefix, qmc-<environment>."
  type        = string
}

variable "limit_usd" {
  description = "Monthly limit in US dollars."
  type        = number
}

variable "alert_email" {
  description = "Address that receives budget emails directly."
  type        = string
}

variable "sns_topic_arn" {
  description = "Alerts topic the budget also publishes to."
  type        = string
}
