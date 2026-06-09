# --- HTTP API: Entry point for KYC verification requests ---
resource "aws_apigatewayv2_api" "kyc_api" {
  name          = "kyc-demo-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["Content-Type"]
  }
}

# --- Integration: Wire API Gateway to the KYC Lambda ---
resource "aws_apigatewayv2_integration" "kyc_integration" {
  api_id                 = aws_apigatewayv2_api.kyc_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.kyc_handler.invoke_arn
  payload_format_version = "2.0"
}

# --- Route: POST /kyc ---
resource "aws_apigatewayv2_route" "kyc_route" {
  api_id    = aws_apigatewayv2_api.kyc_api.id
  route_key = "POST /kyc"
  target    = "integrations/${aws_apigatewayv2_integration.kyc_integration.id}"
}

# --- Route: GET /kyc/{session_id} ---
resource "aws_apigatewayv2_route" "kyc_lookup_route" {
  api_id    = aws_apigatewayv2_api.kyc_api.id
  route_key = "GET /kyc/{session_id}"
  target    = "integrations/${aws_apigatewayv2_integration.kyc_integration.id}"
}

# --- Stage: Auto-deploy to $default ---
resource "aws_apigatewayv2_stage" "kyc_stage" {
  api_id      = aws_apigatewayv2_api.kyc_api.id
  name        = "$default"
  auto_deploy = true
}

# --- Allow API Gateway to invoke the KYC Lambda ---
resource "aws_lambda_permission" "allow_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.kyc_handler.arn
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.kyc_api.execution_arn}/*/*"
}
