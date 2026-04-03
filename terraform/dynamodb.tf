# --- DynamoDB: Store KYC verification results ---
resource "aws_dynamodb_table" "kyc_results" {
  name         = "kyc_results"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "session_id"

  attribute {
    name = "session_id"
    type = "S"
  }
}
