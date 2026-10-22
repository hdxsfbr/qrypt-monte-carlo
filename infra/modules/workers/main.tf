# Shard queue, dead-letter queue and the worker function (docs/DESIGN.md sections 2 and 6).

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name}-shards-dlq"
  sqs_managed_sse_enabled   = true
  message_retention_seconds = 1209600 # 14 days, the maximum, so failed shards can be inspected
}

resource "aws_sqs_queue" "shards" {
  name                       = "${var.name}-shards"
  sqs_managed_sse_enabled    = true
  visibility_timeout_seconds = var.timeout_s * 6 # AWS guidance for Lambda triggers; the worker shortens it on failure
  receive_wait_time_seconds  = 20                # long polling: fewer empty receives
  message_retention_seconds  = 86400

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.shards.arn]
  })
}

resource "aws_cloudwatch_log_group" "worker" {
  #checkov:skip=CKV_AWS_158:Logs use CloudWatch's default encryption; a customer KMS key costs $1/month. Logs never contain secrets.
  #checkov:skip=CKV_AWS_338:Short retention (14 days by default) keeps storage inside the free allowance; this is a demo platform.
  name              = "/aws/lambda/${var.name}-worker"
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "worker" {
  name               = "${var.name}-worker"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# Least privilege: only this table, this queue and this log group. No SSM, no Qrypt.
data "aws_iam_policy_document" "worker" {
  statement {
    sid = "Table"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:ConditionCheckItem",
    ]
    resources = [var.table_arn]
  }

  statement {
    sid = "Queue"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ChangeMessageVisibility",
    ]
    resources = [aws_sqs_queue.shards.arn]
  }

  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.worker.arn}:*"]
  }
}

resource "aws_iam_role_policy" "worker" {
  name   = "worker"
  role   = aws_iam_role.worker.id
  policy = data.aws_iam_policy_document.worker.json
}

resource "aws_lambda_function" "worker" {
  #checkov:skip=CKV_AWS_117:No VPC. The function only calls AWS service endpoints; a VPC would need NAT or endpoints, which are not free.
  #checkov:skip=CKV_AWS_272:Code signing needs AWS Signer profiles and adds no protection for a single-operator deploy from git.
  #checkov:skip=CKV_AWS_173:Environment variables hold only names and limits, no secrets; the default Lambda encryption applies.
  #checkov:skip=CKV_AWS_116:The function is triggered by SQS; failed messages go to the queue's dead-letter queue, not a function DLQ.
  #checkov:skip=CKV_AWS_50:X-Ray tracing is not needed; structured logs carry job and shard ids.
  #checkov:skip=CKV_AWS_115:Reserved concurrency is set when reserve_concurrency is true; while the account quota is 10 the queue trigger's maximum_concurrency caps workers instead.
  function_name                  = "${var.name}-worker"
  role                           = aws_iam_role.worker.arn
  runtime                        = "python3.13"
  handler                        = "handlers.worker.handler"
  filename                       = var.package_path
  source_code_hash               = var.package_hash
  memory_size                    = 1769 # one full vCPU
  timeout                        = var.timeout_s
  reserved_concurrent_executions = var.reserve_concurrency ? var.concurrency : -1

  environment {
    variables = {
      QMC_ENV                = var.environment
      TABLE_NAME             = var.table_name
      MAX_RECEIVE_COUNT      = tostring(var.max_receive_count)
      ENABLE_FAULT_INJECTION = var.fault_injection ? "true" : "false"
    }
  }

  logging_config {
    log_format = "JSON"
    log_group  = aws_cloudwatch_log_group.worker.name
  }

  depends_on = [aws_iam_role_policy.worker]
}

resource "aws_lambda_event_source_mapping" "shards" {
  event_source_arn = aws_sqs_queue.shards.arn
  function_name    = aws_lambda_function.worker.arn
  batch_size       = 1

  scaling_config {
    maximum_concurrency = var.concurrency
  }
}
