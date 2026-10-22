output "budget_name" {
  description = "Budget name."
  value       = aws_budgets_budget.account.name
}
