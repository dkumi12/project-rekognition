# --- CloudWatch Log Groups ---
# Explicitly define log groups so logs are retained for 14 days
# and not deleted when terraform destroy is run

resource "aws_cloudwatch_log_group" "image_analyzer_logs" {
  name              = "/aws/lambda/${aws_lambda_function.image_analyzer.function_name}"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "kyc_handler_logs" {
  name              = "/aws/lambda/${aws_lambda_function.kyc_handler.function_name}"
  retention_in_days = 14
}


# --- CloudWatch Alarms ---
# Triggers when either Lambda throws 1 or more errors within a 60 second window

resource "aws_cloudwatch_metric_alarm" "image_analyzer_errors" {
  alarm_name          = "image-analyzer-lambda-errors"
  alarm_description   = "Triggers when ImageAnalysisHandler throws an error"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.image_analyzer.function_name
  }
}

resource "aws_cloudwatch_metric_alarm" "kyc_handler_errors" {
  alarm_name          = "kyc-handler-lambda-errors"
  alarm_description   = "Triggers when KYCVerificationHandler throws an error"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.kyc_handler.function_name
  }
}
