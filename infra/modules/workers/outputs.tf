output "function_name" {
  description = "Worker function name."
  value       = aws_lambda_function.worker.function_name
}

output "queue_arn" {
  description = "Shard queue ARN."
  value       = aws_sqs_queue.shards.arn
}

output "queue_url" {
  description = "Shard queue URL."
  value       = aws_sqs_queue.shards.id
}

output "queue_name" {
  description = "Shard queue name."
  value       = aws_sqs_queue.shards.name
}

output "dlq_name" {
  description = "Dead-letter queue name."
  value       = aws_sqs_queue.dlq.name
}
