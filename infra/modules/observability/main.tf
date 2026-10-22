# Alerts and the dashboard (docs/DESIGN.md sections 2 and 12).
# Custom metrics are written by the functions as Embedded Metric Format log lines (structured log
# lines CloudWatch turns into metrics) in namespace var.metrics_namespace with one dimension,
# Environment. The six names: JobsSubmitted, PathsSimulated, EntropyKiB, ShardFailures, QryptErrors,
# ShardDurationMs.

resource "aws_sns_topic" "alerts" {
  #checkov:skip=CKV_AWS_26:CloudWatch alarms and AWS Budgets cannot publish to a topic encrypted with the default aws/sns key, and a customer key costs $1/month. Alert messages hold no secrets.
  name = "${var.name}-alerts"
}

# AWS emails a confirmation link; alerts arrive only after it is clicked.
resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

locals {
  alarms = {
    worker-errors = {
      description = "A worker run failed (it will retry; repeated failures end in the dead-letter queue)."
      namespace   = "AWS/Lambda"
      metric      = "Errors"
      dimensions  = { FunctionName = var.worker_function }
    }
    dlq-depth = {
      description = "Shard messages are in the dead-letter queue: a job has failed shards and is PARTIAL."
      namespace   = "AWS/SQS"
      metric      = "ApproximateNumberOfMessagesVisible"
      dimensions  = { QueueName = var.dlq_name }
    }
    api-errors = {
      description = "The api function raised an unhandled error."
      namespace   = "AWS/Lambda"
      metric      = "Errors"
      dimensions  = { FunctionName = var.api_function }
    }
    qrypt-errors = {
      description = "Calls to Qrypt failed (bad token, quota, rate limit or outage); new jobs are being refused."
      namespace   = var.metrics_namespace
      metric      = "QryptErrors"
      dimensions  = { Environment = var.environment }
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "this" {
  for_each = local.alarms

  alarm_name          = "${var.name}-${each.key}"
  alarm_description   = each.value.description
  namespace           = each.value.namespace
  metric_name         = each.value.metric
  dimensions          = each.value.dimensions
  statistic           = each.key == "dlq-depth" ? "Maximum" : "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = var.name
  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric", x = 0, y = 0, width = 12, height = 6
        properties = {
          title   = "Jobs submitted and shard failures"
          region  = var.region
          stat    = "Sum"
          period  = 300
          metrics = [for m in ["JobsSubmitted", "ShardFailures"] : [var.metrics_namespace, m, "Environment", var.environment]]
        }
      },
      {
        type = "metric", x = 12, y = 0, width = 12, height = 6
        properties = {
          title   = "Paths simulated"
          region  = var.region
          stat    = "Sum"
          period  = 300
          metrics = [[var.metrics_namespace, "PathsSimulated", "Environment", var.environment]]
        }
      },
      {
        type = "metric", x = 0, y = 6, width = 12, height = 6
        properties = {
          title   = "Qrypt entropy used (KiB) and Qrypt errors"
          region  = var.region
          stat    = "Sum"
          period  = 300
          metrics = [for m in ["EntropyKiB", "QryptErrors"] : [var.metrics_namespace, m, "Environment", var.environment]]
        }
      },
      {
        type = "metric", x = 12, y = 6, width = 12, height = 6
        properties = {
          title  = "Duration (p95, milliseconds)"
          region = var.region
          stat   = "p95"
          period = 300
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", var.api_function],
            ["AWS/Lambda", "Duration", "FunctionName", var.worker_function],
            [var.metrics_namespace, "ShardDurationMs", "Environment", var.environment],
          ]
        }
      },
      {
        type = "metric", x = 0, y = 12, width = 24, height = 6
        properties = {
          title  = "Errors, throttles and dead-letter queue depth"
          region = var.region
          period = 60
          metrics = [
            ["AWS/Lambda", "Errors", "FunctionName", var.api_function, { stat = "Sum" }],
            ["AWS/Lambda", "Errors", "FunctionName", var.worker_function, { stat = "Sum" }],
            ["AWS/Lambda", "Throttles", "FunctionName", var.worker_function, { stat = "Sum" }],
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.dlq_name, { stat = "Maximum" }],
          ]
        }
      },
    ]
  })
}
