import json
import boto3
import os
import base64
import uuid
from datetime import datetime

rekognition = boto3.client('rekognition')
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')

KYC_BUCKET = os.environ['KYC_BUCKET']
KYC_TABLE = os.environ['KYC_TABLE']


def _error_response(msg):
    return {
        'statusCode': 200,
        'headers': {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'},
        'body': json.dumps({'error': msg})
    }


def lambda_handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        id_image_b64 = body['id_image']
        selfie_b64 = body['selfie']

        id_bytes = base64.b64decode(id_image_b64)
        selfie_bytes = base64.b64decode(selfie_b64)

        # Upload both images to KYC S3 bucket under a unique session folder
        session_id = str(uuid.uuid4())
        id_key = f"sessions/{session_id}/id.jpg"
        selfie_key = f"sessions/{session_id}/selfie.jpg"

        s3.put_object(Bucket=KYC_BUCKET, Key=id_key, Body=id_bytes)
        s3.put_object(Bucket=KYC_BUCKET, Key=selfie_key, Body=selfie_bytes)

        # Validate faces exist in both images before comparing
        id_faces = rekognition.detect_faces(
            Image={'S3Object': {'Bucket': KYC_BUCKET, 'Name': id_key}}
        )
        selfie_faces = rekognition.detect_faces(
            Image={'S3Object': {'Bucket': KYC_BUCKET, 'Name': selfie_key}}
        )
        if not id_faces['FaceDetails']:
            return _error_response("No face detected in ID card image. Use a clear photo ID.")
        if not selfie_faces['FaceDetails']:
            return _error_response("No face detected in selfie. Ensure your face is clearly visible.")

        # Extract text from Ghana Card (name, ID number)
        text_response = rekognition.detect_text(
            Image={'S3Object': {'Bucket': KYC_BUCKET, 'Name': id_key}}
        )
        detected_lines = [
            t['DetectedText']
            for t in text_response['TextDetections']
            if t['Type'] == 'LINE' and t['Confidence'] > 80
        ]
        print(f"Detected lines (80%+): {detected_lines}")

        # Lower-confidence LINE pool
        all_lines = [
            t['DetectedText']
            for t in text_response['TextDetections']
            if t['Type'] == 'LINE' and t['Confidence'] > 50
        ]
        print(f"All lines (50%+): {all_lines}")

        # WORD-level detections — used specifically to reconstruct the GHA number
        # which may be split across multiple words or missed at LINE level
        all_words = [
            t['DetectedText']
            for t in text_response['TextDetections']
            if t['Type'] == 'WORD' and t['Confidence'] > 40
        ]
        print(f"All words (40%+): {all_words}")

        import re

        # Skip card headers and bilingual field labels — Ghana/ECOWAS Card specific
        skip_keywords = [
            'GHANA', 'CARD', 'REPUBLIC', 'ECOWAS', 'IDENTIT', 'CEDEAO',
            'BILREV', 'IDENTIDADE', 'NATIONAL', 'IDENTIFICATION', 'AUTHORITY',
            'SURNAME', 'FORENAME', 'PERSONAL ID', 'NATIONALITY', 'DATE OF',
            'PLACE OF', 'DATE OF BIRTH', 'DATE OF ISSUE', 'DATE OF EXPIRY',
            'DIGITAL SIGNATURE', 'NIA', 'SEX', 'PIN', 'GHA)', 'ACCRA',
            'PREVIOUS', 'NOMS', 'PRECEDENT', 'NOM DE', 'PRENOM',
            'LIEU', 'SIGNATURE', 'HEIGHT', 'WEIGHT', 'ISSUANCE',
            'RESIDENT', 'PROFESSION', 'MARITAL', 'RELIGION', 'CARTE'
        ]

        def is_header(line):
            upper = line.upper()
            # Also treat bilingual lines (containing /) as headers
            if '/' in line:
                return True
            return any(kw in upper for kw in skip_keywords)

        def is_date(line):
            return bool(re.search(r'\d{2}/\d{2}/\d{4}', line.strip()))

        def is_height_or_noise(line):
            # Catch values like '1.84', '082139', single letters
            stripped = line.strip()
            if re.search(r'^\d+\.\d+$', stripped):
                return True
            if re.search(r'^\d{5,}$', stripped):
                return True
            if len(stripped) <= 1:
                return True
            return False

        def is_id_number(line):
            upper = line.upper().strip()
            clean = re.sub(r'[^A-Z0-9]', '', upper.replace('O', '0'))
            # Ghana NIA format: GHA + 8-10 digits
            if clean.startswith('GHA') and re.search(r'\d{8,}', clean):
                return True
            # ECOWAS / other Ghana card format: 2 letters + 5-9 digits
            if re.search(r'^[A-Z]{2}\d{5,9}$', clean):
                return True
            return False

        # ── Name Extraction ──────────────────────────────────────────────────
        # Rekognition returns surname and forenames as standalone lines
        # without labels on this card layout. The order on the card is:
        # card headers → SURNAME → FORENAMES → other fields
        # So the first two clean name-like lines are surname then forenames.

        def is_name_line(line):
            stripped = line.strip()
            if len(stripped) < 2:
                return False
            if is_header(line) or is_date(line) or is_height_or_noise(line):
                return False
            if is_id_number(line):
                return False
            # Must be mostly letters (names are letters, not mixed with numbers)
            alpha_ratio = sum(c.isalpha() for c in stripped) / len(stripped)
            return alpha_ratio >= 0.8

        name_lines = [l for l in detected_lines if is_name_line(l)]
        print(f"Name candidate lines: {name_lines}")

        if len(name_lines) >= 2:
            # Ghana/ECOWAS card order: surname first line, forenames second line
            # Combined as: forenames + surname = "DAVID OSEI KUMI"
            surname_val  = name_lines[0]
            forename_val = name_lines[1]
            extracted_name = forename_val + ' ' + surname_val
        elif len(name_lines) == 1:
            extracted_name = name_lines[0]
        else:
            # Last resort: take longest alpha line from all_lines pool
            fallback = [
                l for l in all_lines
                if not is_header(l) and not is_date(l)
                and not is_height_or_noise(l) and '/' not in l
                and sum(c.isalpha() for c in l) >= 4
            ]
            fallback.sort(key=lambda l: sum(c.isalpha() for c in l), reverse=True)
            extracted_name = fallback[0] if fallback else 'NOT FOUND'

        # ── ID Number Extraction ─────────────────────────────────────────────
        # The Personal ID Number (GHA-XXXXXXXXX-X) sits next to the height
        # field on the card. Rekognition sometimes misses it at high confidence.
        # We use 4 strategies in order of reliability.

        extracted_id = 'NOT FOUND'
        # Labels that precede ID values on the Ghana/ECOWAS card
        id_label_keywords = ['PERSONAL ID', 'ID NUMBER', 'DOCUMENT NUMBER', 'NUMERO', 'HUMERO']

        def find_id_after_label(lines):
            for i, line in enumerate(lines):
                upper = line.upper()
                if any(kw in upper for kw in id_label_keywords):
                    for j in range(i + 1, min(i + 8, len(lines))):
                        candidate = lines[j]
                        if is_date(candidate) or is_height_or_noise(candidate):
                            continue
                        # Skip if it's another label line (contains /)
                        if '/' in candidate:
                            continue
                        clean = re.sub(r'[^A-Z0-9]', '', candidate.upper().replace('O', '0'))
                        # Prefer GHA format
                        if clean.startswith('GHA') and re.search(r'\d{6,}', clean):
                            return candidate.strip()
                        # Accept alphanumeric document number (e.g. AR7437976)
                        if re.search(r'^[A-Z]{1,3}\d{5,}$', clean):
                            return candidate.strip()
            return None

        # Strategy 1: GHA number from WORD-level detections
        gha_word = None
        for i, word in enumerate(all_words):
            clean = re.sub(r'[^A-Z0-9]', '', word.upper().replace('O', '0'))
            if clean.startswith('GHA') and re.search(r'\d{4,}', clean):
                # Strip any trailing letters that are not digits (e.g. "DOCUMENT")
                gha_word = re.match(r'(GHA[\d]+)', clean)
                if gha_word:
                    gha_word = gha_word.group(1)
                else:
                    gha_word = clean
                break
        extracted_id = gha_word if gha_word else 'NOT FOUND'

        # Strategy 2: Direct GHA regex scan across all LINE detections
        if extracted_id == 'NOT FOUND':
            for line in all_lines:
                clean = re.sub(r'[^A-Z0-9]', '', line.upper().replace('O', '0'))
                if clean.startswith('GHA') and re.search(r'\d{8,}', clean):
                    extracted_id = line.strip()
                    break

        # Strategy 3: Personal ID Number label search — high confidence lines first
        if extracted_id == 'NOT FOUND':
            extracted_id = find_id_after_label(detected_lines) or 'NOT FOUND'

        # Strategy 4: Personal ID Number label search — lower confidence lines
        if extracted_id == 'NOT FOUND':
            extracted_id = find_id_after_label(all_lines) or 'NOT FOUND'

        # Strategy 5: Document Number label fallback — last resort
        if extracted_id == 'NOT FOUND':
            id_number_lines = [l for l in detected_lines if is_id_number(l)]
            if id_number_lines:
                extracted_id = id_number_lines[0]

        print(f"Extracted ID: {extracted_id}")

        # Compare face on Ghana Card vs selfie
        compare_response = rekognition.compare_faces(
            SourceImage={'S3Object': {'Bucket': KYC_BUCKET, 'Name': id_key}},
            TargetImage={'S3Object': {'Bucket': KYC_BUCKET, 'Name': selfie_key}},
            SimilarityThreshold=70
        )
        face_matches = compare_response.get('FaceMatches', [])
        face_confidence = round(face_matches[0]['Similarity'], 2) if face_matches else 0.0

        # PASS if confidence >= 70% (matches Rekognition's SimilarityThreshold minimum)
        status = 'PASS' if face_confidence >= 70.0 else 'FAIL'

        result = {
            'session_id': session_id,
            'timestamp': datetime.utcnow().isoformat(),
            'status': status,
            'face_confidence': str(face_confidence),
            'extracted_name': extracted_name,
            'extracted_id_number': extracted_id,
            'detected_text_lines': detected_lines,
        }

        dynamodb.Table(KYC_TABLE).put_item(Item=result)

        print(f"KYC complete. Session: {session_id} | Status: {status} | Confidence: {face_confidence}%")

        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps(result)
        }

    except rekognition.exceptions.InvalidImageFormatException:
        print("KYC error: Invalid image format submitted")
        return {
            'statusCode': 400,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'Unsupported format. Please use JPEG or PNG.'})
        }

    except Exception as e:
        print(f"KYC error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }
