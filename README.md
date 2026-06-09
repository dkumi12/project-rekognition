# Amazon Rekognition Image Analysis Pipeline

A serverless image analysis and identity verification pipeline built on AWS. The system processes uploaded images through Amazon Rekognition for object detection, facial analysis, and OCR text extraction, storing structured JSON results in S3. Includes a Ghana Card KYC (Know Your Customer) verification system that matches faces and extracts identity information from government-issued ID cards.

## Architecture

```
                        +---------------------------+
                        |   Frontend (index.html)   |
                        |   Hosted on S3 Bucket     |
                        +-------------+-------------+
                                      |
                                      | POST /kyc (Base64 images)
                                      v
                        +---------------------------+
                        |      API Gateway          |
                        |      HTTP API             |
                        +-------------+-------------+
                                      |
                                      v
              +----------------------------------------------+
              |       Lambda: KYCVerificationHandler         |
              |                                              |
              |  1. Upload ID card + selfie to S3            |
              |  2. DetectFaces on both images               |
              |  3. DetectText on ID card (OCR)              |
              |  4. CompareFaces (ID vs selfie)              |
              |  5. Store result in DynamoDB                 |
              +----------------------------------------------+
                    |                |                |
                    v                v                v
              +---------+    +-------------+   +-----------+
              |   S3    |    | Rekognition |   | DynamoDB  |
              | Sessions|    |   Service   |   | kyc_results|
              +---------+    +-------------+   +-----------+


              +---------------------------+
              |  S3 Bucket: image-inputs  |
              +-------------+-------------+
                            |
                            | S3 Event (ObjectCreated .jpg/.png)
                            v
              +----------------------------------------------+
              |       Lambda: ImageAnalysisHandler           |
              |                                              |
              |  1. DetectLabels (objects, scenes)            |
              |  2. DetectFaces (emotions, age, gender)       |
              |  3. DetectText (OCR)                          |
              |  4. Save JSON result to output bucket         |
              +----------------------------------------------+
                    |                |
                    v                v
              +---------+    +-------------+
              |   S3    |    | Rekognition |
              | Outputs |    |   Service   |
              +---------+    +-------------+
```

## AWS Services Used

| Service | Role |
|---------|------|
| Amazon Rekognition | Core AI/ML service. Calls DetectLabels, DetectFaces, DetectText, and CompareFaces |
| AWS Lambda | Two serverless functions: ImageAnalysisHandler and KYCVerificationHandler |
| Amazon S3 | Four buckets for image inputs, analysis outputs, KYC sessions, and frontend hosting |
| Amazon DynamoDB | Stores KYC verification results with session tracking |
| API Gateway | HTTP API exposing POST /kyc and GET /kyc/{session_id} endpoints with CORS |
| AWS IAM | Least-privilege execution role for Lambda functions |
| Amazon CloudWatch | Log groups with 14-day retention and error alarms for both Lambda functions |

## Project Structure

```
rekognition/
|-- .github/
|   `-- workflows/
|       `-- deploy.yml            # CI/CD pipeline (GitHub Actions)
|-- docs/
|   |-- guides/                   # Demo script and build guide artifacts
|   |-- marketing/                # LinkedIn and marketing presentation content
|   `-- presentations/            # Project presentation exports
|-- src/
|   |-- app.py                    # Lambda: general image analysis handler
|   `-- kyc_handler.py            # Lambda: KYC identity verification handler
|-- frontend/
|   `-- index.html                # Web UI for Ghana Card verification
|-- terraform/
|   |-- providers.tf              # AWS provider configuration (us-east-1)
|   |-- lambda.tf                 # Lambda function definitions
|   |-- api_gateway.tf            # HTTP API and route configuration
|   |-- s3.tf                     # S3 bucket definitions and event triggers
|   |-- dynamodb.tf               # KYC results table
|   |-- iam.tf                    # IAM roles and policies
|   |-- cloudwatch.tf             # Log groups and error alarms
|   `-- outputs.tf                # API URL and frontend URL outputs
`-- README.md                     # This file
```

## Prerequisites

Before deploying this project, ensure the following tools are installed and configured:

| Tool | Version | Purpose |
|------|---------|---------|
| AWS CLI | v2+ | Interacting with AWS services |
| Terraform | v1.0+ | Infrastructure provisioning |
| Python | 3.12+ | Lambda runtime |
| Git | Any | Version control |

You also need an AWS account with access to Rekognition, S3, Lambda, DynamoDB, API Gateway, IAM, and CloudWatch.

## Deployment Guide

### Step 1: Clone the Repository

```bash
git clone https://github.com/dkumi12/project-rekognition.git
cd project-rekognition
```

### Step 2: Configure AWS Credentials

```bash
aws configure
```

Enter your Access Key ID, Secret Access Key, and set the default region to `us-east-1`.

Verify your identity:

```bash
aws sts get-caller-identity
```

### Step 3: Deploy Infrastructure with Terraform

```bash
cd terraform
terraform init
terraform apply
```

Review the plan and type `yes` to confirm. Terraform will create all AWS resources: S3 buckets, Lambda functions, API Gateway, DynamoDB table, IAM roles, and CloudWatch alarms.

### Step 4: Note the Output Values

After Terraform completes, it prints two values:

```
kyc_api_endpoint = "https://xxxxxxxx.execute-api.us-east-1.amazonaws.com/kyc"
frontend_url     = "http://rekkyc-frontend.s3-website-us-east-1.amazonaws.com"
```

### Step 5: Update the Frontend API URL

Open `frontend/index.html` and update line 213 with the `kyc_api_endpoint` value from Step 4:

```javascript
const API_URL = 'https://xxxxxxxx.execute-api.us-east-1.amazonaws.com/kyc';
```

### Step 6: Upload the Frontend to S3

```bash
aws s3 cp frontend/index.html s3://rekkyc-frontend/index.html \
  --content-type "text/html" \
  --cache-control "no-cache"
```

### Step 7: Test the Pipeline

**Test 1 - General image analysis:**

Upload any JPEG or PNG image to the input bucket:

```bash
aws s3 cp sample-image.jpg s3://rekimage-inputs/sample-image.jpg
```

Verify the output JSON appears in the output bucket:

```bash
aws s3 ls s3://rekanalysis-outputs/
```

**Test 2 - KYC verification:**

Open the `frontend_url` from Step 4 in a browser. Upload a Ghana Card image and a selfie. The system should return a PASS or FAIL verdict with the extracted name, ID number, face match confidence, and liveness check result.

## CI/CD Pipeline

The project uses GitHub Actions for continuous deployment. On every push to `main`, the pipeline automatically:

1. Packages the `src/` folder into `lambda_function.zip`
2. Deploys the updated code to both Lambda functions
3. Uploads the latest frontend to S3

### Setup

Add the following secrets to your GitHub repository under Settings > Secrets and variables > Actions:

| Secret Name | Value |
|-------------|-------|
| `AWS_ACCESS_KEY_ID` | Your IAM user access key |
| `AWS_SECRET_ACCESS_KEY` | Your IAM user secret key |

Infrastructure changes (adding new resources, modifying settings) are managed separately via `terraform apply` run locally.

## Usage

### General Image Analysis

Upload a JPEG or PNG image (max 5MB) to the `rekimage-inputs` S3 bucket. The Lambda function is triggered automatically by the S3 event and produces a JSON output file containing:

- **Labels**: Objects and scenes detected in the image with confidence scores
- **Faces**: Facial attributes including emotions, age range, gender, smile detection, and eyeglasses
- **Text**: Any visible text extracted via OCR

Output files are stored in `rekanalysis-outputs` with the naming convention: `{image-name}_{timestamp}_analysis.json`

### KYC Identity Verification

The web frontend accepts two images:

1. **Ghana Card** - a photo of the front of the card
2. **Live Selfie** - a photo of the cardholder's face, uploaded from file or captured from the device camera when the browser allows it

The system performs the following checks:

1. Validates that both images contain detectable faces
2. Extracts the cardholder's name and ID number from the card via OCR
3. Compares the face on the card with the selfie using a 70% similarity threshold
4. Runs a passive liveness/quality check on the selfie: one face, eyes open, no sunglasses, adequate sharpness and brightness, and a reasonable face angle
5. Returns PASS only when both the face match and liveness checks pass
6. Stores the result in DynamoDB for audit purposes

You can retrieve a stored result with:

```bash
curl https://xxxxxxxx.execute-api.us-east-1.amazonaws.com/kyc/{session_id}
```

The liveness check is a passive heuristic based on Rekognition `DetectFaces` attributes. It is useful for testing and demos, but it is not the same as AWS's dedicated Face Liveness workflow.

**Camera note:** Browser webcam capture requires a secure context, usually HTTPS or localhost. The default S3 static website endpoint is HTTP, so desktop live camera capture is blocked there by the browser. Mobile users can still use the selfie upload field to open the camera, and desktop live capture will work after hosting the frontend behind HTTPS, such as through CloudFront.

**Note on image quality:** The Personal ID Number (GHA-XXXXXXXXX-X) is printed on the holographic section of the Ghana Card. For best results, photograph the card in good lighting and avoid flash glare on the holographic area. If the GHA number is unreadable, the system falls back to the Document Number printed below it.

## Output Format

### Image Analysis JSON

```json
{
    "image_name": "sample.jpg",
    "timestamp": "2026-04-03T14:30:00.000000",
    "labels": [
        {"Name": "Person", "Confidence": 99.2},
        {"Name": "Outdoors", "Confidence": 95.1}
    ],
    "faces": [
        {
            "AgeRange": {"Low": 25, "High": 35},
            "Gender": {"Value": "Male", "Confidence": 99.5},
            "Emotions": [{"Type": "HAPPY", "Confidence": 97.3}],
            "Smile": {"Value": true, "Confidence": 98.1}
        }
    ],
    "text_detections": [
        {"DetectedText": "HELLO WORLD", "Confidence": 99.8, "Type": "LINE"}
    ]
}
```

### KYC Verification Response

```json
{
    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "timestamp": "2026-04-03T14:30:00.000000",
    "status": "PASS",
    "face_match_status": "PASS",
    "face_confidence": "98.39",
    "liveness_status": "PASS",
    "liveness_score": "100",
    "liveness_checks": [
        {"label": "Single face in selfie", "passed": true, "value": "1 face detected"},
        {"label": "Eyes open", "passed": true, "value": "True"}
    ],
    "extracted_name": "DAVID OSEI KUMI",
    "extracted_id_number": "GHA0010763780",
    "detected_text_lines": ["ECOWAS IDENTITY CARD", "KUMI", "DAVID OSEI", "..."]
}
```

## Error Handling

The system handles the following error conditions:

| Error | How It Is Handled |
|-------|-------------------|
| Unsupported image format (not JPEG/PNG) | Returns 400 with message: "Unsupported format. Please use JPEG or PNG." |
| File exceeds 5MB size limit | Returns 400 with message: "File too large. Max allowed is 5MB." |
| No face detected in ID card image | Returns error: "No face detected in ID card image. Use a clear photo ID." |
| No face detected in selfie | Returns error: "No face detected in selfie. Ensure your face is clearly visible." |
| Rekognition API throttling | Automatic retry with 2-second delay, up to 3 attempts |
| Any unhandled exception | Logged to CloudWatch with full context, returns 500 to client |

## Monitoring

### CloudWatch Logs

Both Lambda functions log to CloudWatch with 14-day retention:

- `/aws/lambda/ImageAnalysisHandler`
- `/aws/lambda/KYCVerificationHandler`

View recent logs:

```bash
aws logs tail /aws/lambda/ImageAnalysisHandler --follow
aws logs tail /aws/lambda/KYCVerificationHandler --follow
```

### CloudWatch Alarms

Two alarms are configured to trigger when either Lambda function throws an error:

- `image-analyzer-lambda-errors`
- `kyc-handler-lambda-errors`

Check alarm status:

```bash
aws cloudwatch describe-alarms \
  --alarm-names image-analyzer-lambda-errors kyc-handler-lambda-errors \
  --query "MetricAlarms[*].[AlarmName,StateValue]" \
  --output table
```

## Troubleshooting

### Lambda function not triggering on S3 upload

**Symptom:** You upload an image to `rekimage-inputs` but no output JSON appears in `rekanalysis-outputs`.

**Fix:**
1. Check that the file extension is `.jpg`, `.jpeg`, or `.png` (case sensitive)
2. Verify the S3 event notification is configured: `aws s3api get-bucket-notification-configuration --bucket rekimage-inputs`
3. Check Lambda logs for errors: `aws logs tail /aws/lambda/ImageAnalysisHandler --follow`

### KYC frontend returns CORS error

**Symptom:** The browser console shows "Access-Control-Allow-Origin" errors when clicking Verify Identity.

**Fix:**
1. Verify the API Gateway has CORS enabled: check `terraform/api_gateway.tf` for the `cors_configuration` block
2. Ensure the API URL in `frontend/index.html` matches the actual API Gateway endpoint
3. Redeploy: `terraform apply` then update the frontend

### KYC returns "NOT FOUND" for name or ID number

**Symptom:** Face match works but the extracted name or ID number shows NOT FOUND.

**Fix:**
1. Check the image quality. The Ghana Card should be well-lit with no glare on the holographic area
2. Check CloudWatch logs for the `Detected lines` output to see what Rekognition actually read
3. If the Personal ID Number (GHA format) is unreadable due to holographic glare, the system falls back to the Document Number

### CI/CD pipeline fails

**Symptom:** GitHub Actions workflow shows a red X.

**Fix:**
1. Go to the Actions tab on GitHub and click the failed run to see the error
2. Most common cause: missing or expired AWS credentials in GitHub Secrets
3. Verify secrets exist at: Settings > Secrets and variables > Actions
4. Ensure the IAM user has permissions for `lambda:UpdateFunctionCode` and `s3:PutObject`

### Terraform "already exists" errors

**Symptom:** Running `terraform apply` locally gives "ResourceAlreadyExistsException" errors.

**Fix:**
Import the existing resources into Terraform state:

```bash
terraform import aws_cloudwatch_log_group.image_analyzer_logs /aws/lambda/ImageAnalysisHandler
terraform import aws_cloudwatch_log_group.kyc_handler_logs /aws/lambda/KYCVerificationHandler
```

Then run `terraform apply` again.

## Cleanup

To delete all AWS resources and avoid ongoing charges:

```bash
cd terraform
terraform destroy
```

Type `yes` to confirm. This removes all S3 buckets, Lambda functions, DynamoDB tables, API Gateway, IAM roles, and CloudWatch resources.

## Cost

Amazon Rekognition provides 5,000 free image analyses per month for the first 12 months under the AWS Free Tier. After the free tier, pricing is $0.001 per image for DetectLabels and DetectFaces. S3, Lambda, and DynamoDB also have free tiers that are more than sufficient for this project.
