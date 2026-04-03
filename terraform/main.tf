# Infrastructure has been split into focused files:
#
#   providers.tf    - AWS provider + local variables
#   s3.tf           - S3 buckets + event trigger + Lambda permission
#   iam.tf          - IAM role, policies, and attachments
#   lambda.tf       - Lambda functions + zip packaging
#   dynamodb.tf     - DynamoDB table for KYC results
#   api_gateway.tf  - API Gateway HTTP API + Lambda permission
#   outputs.tf      - Terraform output values
#
# Application logic lives in:
#   src/app.py          - Image analysis Lambda handler
#   src/kyc_handler.py  - KYC verification Lambda handler
#   frontend/index.html - Demo UI
