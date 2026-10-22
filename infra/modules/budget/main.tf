# A $1 monthly budget on the whole account (docs/DESIGN.md section 1).
# Credits are excluded, so the budget counts what usage would cost before the Free plan credits apply:
# it warns before any of the $100 is spent.

data "aws_caller_identity" "current" {}

# Replaces the topic's default policy, so it repeats the owner's rights and adds the two AWS services
# that publish alerts.
data "aws_iam_policy_document" "topic" {
  statement {
    sid = "Owner"
    actions = [
      "SNS:GetTopicAttributes",
      "SNS:SetTopicAttributes",
      "SNS:AddPermission",
      "SNS:RemovePermission",
      "SNS:DeleteTopic",
      "SNS:Subscribe",
      "SNS:ListSubscriptionsByTopic",
      "SNS:Publish",
    ]
    resources = [var.sns_topic_arn]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }

  statement {
    sid       = "CloudWatchAlarms"
    actions   = ["SNS:Publish"]
    resources = [var.sns_topic_arn]
    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }

  statement {
    sid       = "Budgets"
    actions   = ["SNS:Publish"]
    resources = [var.sns_topic_arn]
    principals {
      type        = "Service"
      identifiers = ["budgets.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_sns_topic_policy" "alerts" {
  arn    = var.sns_topic_arn
  policy = data.aws_iam_policy_document.topic.json
}

resource "aws_budgets_budget" "account" {
  name         = "${var.name}-monthly"
  budget_type  = "COST"
  limit_amount = format("%.2f", var.limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_types {
    include_credit = false
    include_refund = false
  }

  # Early warning at half the limit, then at the limit, then when AWS forecasts the month will pass it.
  dynamic "notification" {
    for_each = [
      { type = "ACTUAL", threshold = 50 },
      { type = "ACTUAL", threshold = 100 },
      { type = "FORECASTED", threshold = 100 },
    ]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value.threshold
      threshold_type             = "PERCENTAGE"
      notification_type          = notification.value.type
      subscriber_email_addresses = [var.alert_email]
      subscriber_sns_topic_arns  = [var.sns_topic_arn]
    }
  }

  depends_on = [aws_sns_topic_policy.alerts]
}
