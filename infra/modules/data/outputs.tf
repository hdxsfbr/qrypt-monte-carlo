output "table_name" {
  description = "Table name."
  value       = aws_dynamodb_table.jobs.name
}

output "table_arn" {
  description = "Table ARN (its AWS address)."
  value       = aws_dynamodb_table.jobs.arn
}
