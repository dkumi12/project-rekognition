# --- S3 Bucket: General image analysis input ---
resource "aws_s3_bucket" "image_inputs" {
  bucket = "${local.bucket_prefix}image-inputs"
}

# --- S3 Bucket: General image analysis output (JSON results) ---
resource "aws_s3_bucket" "analysis_outputs" {
  bucket = "${local.bucket_prefix}analysis-outputs"
}

# --- S3 Bucket: KYC session images (ID card + selfie pairs) ---
resource "aws_s3_bucket" "kyc_sessions" {
  bucket = "${local.bucket_prefix}kyc-sessions"
}

# --- S3 Bucket: Frontend static website hosting ---
resource "aws_s3_bucket" "frontend" {
  bucket = "${local.bucket_prefix}kyc-frontend"
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  index_document {
    suffix = "index.html"
  }
}

resource "aws_s3_bucket_policy" "frontend_public_read" {
  bucket     = aws_s3_bucket.frontend.id
  depends_on = [aws_s3_bucket_public_access_block.frontend]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.frontend.arn}/*"
    }]
  })
}

# --- Allow S3 to invoke the image analysis Lambda ---
resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.image_analyzer.arn
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.image_inputs.arn
}

# --- Trigger image analysis Lambda on .jpg and .png uploads ---
resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = aws_s3_bucket.image_inputs.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.image_analyzer.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".jpg"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.image_analyzer.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".png"
  }

  depends_on = [aws_lambda_permission.allow_s3]
}
