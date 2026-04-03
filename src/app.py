import json
import boto3
import os
import urllib.parse
from datetime import datetime

# Initialize AWS clients
rekognition = boto3.client('rekognition')
s3 = boto3.client('s3')

# Pull the output bucket name from Terraform's environment variables
OUTPUT_BUCKET = os.environ['OUTPUT_BUCKET']

def lambda_handler(event, context):
    try:
        # 1. Extract the bucket name and image key from the S3 event
        input_bucket = event['Records'][0]['s3']['bucket']['name']
        image_key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'])
        
        print(f"Starting analysis for image: {image_key} from bucket: {input_bucket}")

        image_reference = {'S3Object': {'Bucket': input_bucket, 'Name': image_key}}
	
	# --- Paste here: between image_key line and image_reference line ---

	SUPPORTED_FORMATS = ['.jpg', '.jpeg', '.png']
	MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5MB

	ext = os.path.splitext(image_key)[1].lower()
	if ext not in SUPPORTED_FORMATS:
    	print(f"Unsupported format: {ext}")
    	return {'statusCode': 400, 'body': f'Unsupported format: {ext}. Use JPG or PNG.'}

	file_size = event['Records'][0]['s3']['object']['size']
	if file_size > MAX_SIZE_BYTES:
    	print(f"File too large: {file_size} bytes")
    	return {'statusCode': 400, 'body': f'File too large. Max allowed is 5MB.'}

	
        # 2. Call Amazon Rekognition APIs
        labels_response = call_with_retry(lambda: rekognition.detect_labels(Image=image_reference, MaxLabels=15))
	faces_response  = call_with_retry(lambda: rekognition.detect_faces(Image=image_reference, Attributes=['ALL']))
	text_response   = call_with_retry(lambda: rekognition.detect_text(Image=image_reference))


        # 3. Structure the final JSON output
        analysis_results = {
            "image_name": image_key,
            "timestamp": datetime.utcnow().isoformat(),
            "labels": labels_response.get('Labels', []),
            "faces": faces_response.get('FaceDetails', []),
            "text_detections": text_response.get('TextDetections', [])
        }

        # 4. Save the results to the Output S3 Bucket
        timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        # This creates a clean file name like: myphoto_20260320_100230_analysis.json
        clean_name = image_key.split('.')[0]
        output_file_name = f"{clean_name}_{timestamp_str}_analysis.json"
        
        s3.put_object(
            Bucket=OUTPUT_BUCKET,
            Key=output_file_name,
            Body=json.dumps(analysis_results, indent=4),
            ContentType='application/json'
        )

        print(f"Successfully saved analysis to {OUTPUT_BUCKET}/{output_file_name}")
        
        return {
            'statusCode': 200,
            'body': json.dumps('Image analysis complete!')
        }

    except Exception as e:
        # This safely checks if image_key exists yet, and defaults to "Unknown Image" if it doesn't
        failed_image = locals().get('image_key', 'Unknown Image')
        print(f"Error processing image {failed_image}: {str(e)}")
        print(f"The raw event data was: {json.dumps(event)}") # Prints the bad data for debugging
        raise e