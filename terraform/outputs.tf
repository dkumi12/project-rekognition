# --- Printed after `terraform apply` ---
output "kyc_api_endpoint" {
  value       = "${trimsuffix(aws_apigatewayv2_stage.kyc_stage.invoke_url, "/")}/kyc"
  description = "Paste this URL into frontend/index.html as API_URL"
}

output "frontend_url" {
  value       = "http://${aws_s3_bucket_website_configuration.frontend.website_endpoint}"
  description = "Public URL for the KYC demo frontend"
}
