# --- Shared Lambda execution role ---
resource "aws_iam_role" "lambda_exec_role" {
  name = "rekognition_lambda_role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

# --- Policy: image analysis Lambda (CloudWatch + S3 + Rekognition) ---
resource "aws_iam_policy" "lambda_policy" {
  name        = "rekognition_lambda_policy"
  description = "Permissions for Lambda to read/write S3 and call Rekognition"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject"]
        Resource = [
          "${aws_s3_bucket.image_inputs.arn}/*",
          "${aws_s3_bucket.analysis_outputs.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "rekognition:DetectLabels",
          "rekognition:DetectFaces",
          "rekognition:DetectText"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_attach" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}

# --- Policy: KYC Lambda (face checks + KYC S3 bucket + DynamoDB) ---
resource "aws_iam_policy" "kyc_policy" {
  name        = "rekognition_kyc_policy"
  description = "Permissions for KYC Lambda: CompareFaces, KYC S3 bucket, DynamoDB"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "rekognition:CompareFaces",
          "rekognition:DetectFaces",
          "rekognition:DetectText"
        ]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["textract:DetectDocumentText"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${aws_s3_bucket.kyc_sessions.arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Scan"]
        Resource = aws_dynamodb_table.kyc_results.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "kyc_attach" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.kyc_policy.arn
}
