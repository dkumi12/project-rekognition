# --- Package all Python files in src/ into a zip ---
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/../lambda_function.zip"
}

# --- Lambda: General image analysis (triggered by S3 uploads) ---
resource "aws_lambda_function" "image_analyzer" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "ImageAnalysisHandler"
  role             = aws_iam_role.lambda_exec_role.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  timeout          = 60
  memory_size      = 256
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      OUTPUT_BUCKET = aws_s3_bucket.analysis_outputs.bucket
    }
  }
}

# --- Lambda: KYC verification (triggered by API Gateway POST /kyc) ---
resource "aws_lambda_function" "kyc_handler" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "KYCVerificationHandler"
  role             = aws_iam_role.lambda_exec_role.arn
  handler          = "kyc_handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 60
  memory_size      = 256
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      KYC_BUCKET = aws_s3_bucket.kyc_sessions.bucket
      KYC_TABLE  = aws_dynamodb_table.kyc_results.name
    }
  }
}
