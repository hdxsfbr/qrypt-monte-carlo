output "function_url" {
  description = "HTTPS address of the API."
  value       = module.api.function_url
}

output "table_name" {
  description = "DynamoDB table holding jobs, shard results and rate-limit counters."
  value       = module.data.table_name
}

output "queue_name" {
  description = "SQS queue carrying one message per shard."
  value       = module.workers.queue_name
}

output "dlq_name" {
  description = "Dead-letter queue: shard messages that failed every attempt."
  value       = module.workers.dlq_name
}

output "alerts_topic_arn" {
  description = "SNS topic that alarms and the budget publish to."
  value       = module.observability.topic_arn
}

output "dashboard_name" {
  description = "CloudWatch dashboard."
  value       = module.observability.dashboard_name
}
