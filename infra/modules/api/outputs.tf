output "function_name" {
  description = "Api function name."
  value       = aws_lambda_function.api.function_name
}

output "function_url" {
  description = "HTTPS address of the API."
  value       = aws_lambda_function_url.api.function_url
}
