import json
import os
import time
import urllib.parse
from datetime import datetime

import boto3
from botocore.exceptions import ClientError


rekognition = boto3.client("rekognition")
s3 = boto3.client("s3")

OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]
SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png"}
MAX_SIZE_BYTES = 5 * 1024 * 1024


def call_with_retry(operation, max_attempts=3):
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in {"ProvisionedThroughputExceededException", "ThrottlingException"}:
                raise
            if attempt == max_attempts:
                raise
            time.sleep(2 ** (attempt - 1))


def lambda_handler(event, context):
    try:
        record = event["Records"][0]
        input_bucket = record["s3"]["bucket"]["name"]
        image_key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        file_size = record["s3"]["object"].get("size", 0)

        print(f"Starting analysis for image: {image_key} from bucket: {input_bucket}")

        ext = os.path.splitext(image_key)[1].lower()
        if ext not in SUPPORTED_FORMATS:
            print(f"Unsupported format: {ext}")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": f"Unsupported format: {ext}. Use JPG or PNG."}),
            }

        if file_size > MAX_SIZE_BYTES:
            print(f"File too large: {file_size} bytes")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "File too large. Max allowed is 5MB."}),
            }

        image_reference = {"S3Object": {"Bucket": input_bucket, "Name": image_key}}

        labels_response = call_with_retry(
            lambda: rekognition.detect_labels(Image=image_reference, MaxLabels=15)
        )
        faces_response = call_with_retry(
            lambda: rekognition.detect_faces(Image=image_reference, Attributes=["ALL"])
        )
        text_response = call_with_retry(
            lambda: rekognition.detect_text(Image=image_reference)
        )

        analysis_results = {
            "image_name": image_key,
            "timestamp": datetime.utcnow().isoformat(),
            "labels": labels_response.get("Labels", []),
            "faces": faces_response.get("FaceDetails", []),
            "text_detections": text_response.get("TextDetections", []),
        }

        timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        clean_name = os.path.splitext(image_key)[0].replace("\\", "/")
        output_file_name = f"{clean_name}_{timestamp_str}_analysis.json"

        s3.put_object(
            Bucket=OUTPUT_BUCKET,
            Key=output_file_name,
            Body=json.dumps(analysis_results, indent=4),
            ContentType="application/json",
        )

        print(f"Successfully saved analysis to {OUTPUT_BUCKET}/{output_file_name}")

        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Image analysis complete."}),
        }

    except Exception as exc:
        failed_image = locals().get("image_key", "Unknown Image")
        print(f"Error processing image {failed_image}: {str(exc)}")
        print(f"The raw event data was: {json.dumps(event)}")
        raise
