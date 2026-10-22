output "topic_arn" {
  description = "Alerts topic ARN."
  value       = aws_sns_topic.alerts.arn
}

output "dashboard_name" {
  description = "Dashboard name."
  value       = aws_cloudwatch_dashboard.main.dashboard_name
}
