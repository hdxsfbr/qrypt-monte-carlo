# The api function behind one Function URL (docs/DESIGN.md sections 2 and 8).

resource "aws_cloudwatch_log_group" "api" {
  #checkov:skip=CKV_AWS_158:Logs use CloudWatch's default encryption; a customer KMS key costs $1/month. Logs never contain secrets.
  #checkov:skip=CKV_AWS_338:Short retention (14 days by default) keeps storage inside the free allowance; this is a demo platform.
  name              = "/aws/lambda/${var.name}-api"
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

resource "aws_iam_role" "api" {
  name               = "${var.name}-api"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# Least privilege: this table and its index, this queue, the two named parameters, this log group.
data "aws_iam_policy_document" "api" {
  statement {
    sid = "Table"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:DescribeTable",
    ]
    resources = [var.table_arn, "${var.table_arn}/index/by_created"]
  }

  statement {
    sid       = "Queue"
    actions   = ["sqs:SendMessage"]
    resources = [var.queue_arn]
  }

  # GetParameter with decryption uses the AWS-managed aws/ssm key through SSM, so no KMS grant is needed.
  statement {
    sid       = "Secrets"
    actions   = ["ssm:GetParameter"]
    resources = var.ssm_parameter_arns
  }

  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.api.arn}:*"]
  }
}

resource "aws_iam_role_policy" "api" {
  name   = "api"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

resource "aws_lambda_function" "api" {
  #checkov:skip=CKV_AWS_117:No VPC. The function calls AWS service endpoints and Qrypt over HTTPS; a VPC would need a NAT gateway, which is not free.
  #checkov:skip=CKV_AWS_272:Code signing needs AWS Signer profiles and adds no protection for a single-operator deploy from git.
  #checkov:skip=CKV_AWS_173:Environment variables hold only names and limits; secrets are read from SSM at run time.
  #checkov:skip=CKV_AWS_116:Invoked synchronously through the Function URL; a function DLQ only applies to asynchronous calls.
  #checkov:skip=CKV_AWS_50:X-Ray tracing is not needed; structured logs carry job and request ids.
  #checkov:skip=CKV_AWS_115:Reserved concurrency is set when reserve_concurrency is true; it cannot be reserved while the account quota is 10.
  function_name                  = "${var.name}-api"
  role                           = aws_iam_role.api.arn
  runtime                        = "python3.13"
  handler                        = "handlers.api.handler"
  filename                       = var.package_path
  source_code_hash               = var.package_hash
  memory_size                    = 512
  timeout                        = 10
  reserved_concurrent_executions = var.reserve_concurrency ? var.concurrency : -1

  environment {
    variables = {
      QMC_ENV                = var.environment
      TABLE_NAME             = var.table_name
      QUEUE_URL              = var.queue_url
      QRYPT_PARAM_NAME       = var.qrypt_param_name
      API_KEY_PARAM_NAME     = var.api_key_param_name
      AUTH_TYPE              = var.auth_type
      MAX_PATHS              = tostring(var.max_paths)
      MAX_SHARDS             = tostring(var.max_shards)
      MAX_PATHS_PER_SHARD    = tostring(var.max_paths_per_shard)
      ENABLE_FAULT_INJECTION = var.fault_injection ? "true" : "false"
    }
  }

  logging_config {
    log_format = "JSON"
    log_group  = aws_cloudwatch_log_group.api.name
  }

  depends_on = [aws_iam_role_policy.api]
}

resource "aws_lambda_function_url" "api" {
  #checkov:skip=CKV_AWS_258:With the default BEARER mode the URL is public by design so graders can use curl; every route checks the bearer key. AWS_IAM is available as a switch.
  function_name      = aws_lambda_function.api.function_name
  authorization_type = var.auth_type == "AWS_IAM" ? "AWS_IAM" : "NONE"
}

# A public Function URL needs both permissions (AWS changed this in October 2025).
resource "aws_lambda_permission" "url_invoke_url" {
  #checkov:skip=CKV_AWS_301:Public by design in BEARER mode, and only through the Function URL (function_url_auth_type NONE); the bearer key is checked in code.
  count                  = var.auth_type == "AWS_IAM" ? 0 : 1
  statement_id           = "FunctionUrlPublicInvokeUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "url_invoke_function" {
  #checkov:skip=CKV_AWS_301:Public invoke is limited to calls that arrive through the Function URL (invoked_via_function_url); the bearer key is checked in code.
  count                    = var.auth_type == "AWS_IAM" ? 0 : 1
  statement_id             = "FunctionUrlPublicInvokeFunction"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.api.function_name
  principal                = "*"
  invoked_via_function_url = true
}
