import base64
import json
import os
import re
import uuid
from datetime import datetime

import boto3


rekognition = boto3.client("rekognition")
textract = boto3.client("textract")
dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

KYC_BUCKET = os.environ["KYC_BUCKET"]
KYC_TABLE = os.environ["KYC_TABLE"]
MAX_IMAGE_BYTES = 5 * 1024 * 1024

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Content-Type": "application/json",
}


def _response(status_code, payload):
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(payload),
    }


def _error_response(msg, status_code=400):
    return _response(status_code, {"error": msg})


def _decode_image(field_name, image_b64):
    if not image_b64:
        raise ValueError(f"Missing required field: {field_name}.")

    try:
        image_bytes = base64.b64decode(image_b64, validate=True)
    except Exception as exc:
        raise ValueError(f"{field_name} must be a valid base64 image.") from exc

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError(f"{field_name} is too large. Max allowed is 5MB.")

    is_jpeg = image_bytes.startswith(b"\xff\xd8\xff")
    is_png = image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    if not (is_jpeg or is_png):
        raise ValueError(f"{field_name} must be a JPEG or PNG image.")

    return image_bytes


def _largest_face(face_details):
    return max(
        face_details,
        key=lambda face: face.get("BoundingBox", {}).get("Width", 0)
        * face.get("BoundingBox", {}).get("Height", 0),
    )


def _check(label, passed, value):
    return {"label": label, "passed": bool(passed), "value": str(value)}


def _assess_passive_liveness(face_details):
    if len(face_details) != 1:
        return {
            "status": "FAIL",
            "score": "0",
            "checks": [
                _check("Single face in selfie", False, f"{len(face_details)} faces detected")
            ],
        }

    face = _largest_face(face_details)
    quality = face.get("Quality", {})
    pose = face.get("Pose", {})
    confidence = face.get("Confidence", 0)
    eyes_open = face.get("EyesOpen", {})
    sunglasses = face.get("Sunglasses", {})
    face_occluded = face.get("FaceOccluded", {})

    checks = [
        _check("Single face in selfie", True, "1 face detected"),
        _check("Face detection confidence", confidence >= 95, round(confidence, 2)),
        _check("Eyes open", eyes_open.get("Value") is True and eyes_open.get("Confidence", 0) >= 80, eyes_open.get("Value")),
        _check("No sunglasses", sunglasses.get("Value") is not True, sunglasses.get("Value")),
        _check("Sharpness", quality.get("Sharpness", 0) >= 40, round(quality.get("Sharpness", 0), 2)),
        _check("Brightness", 35 <= quality.get("Brightness", 0) <= 95, round(quality.get("Brightness", 0), 2)),
        _check("Face centered", abs(pose.get("Yaw", 0)) <= 30 and abs(pose.get("Pitch", 0)) <= 25, f"yaw {round(pose.get('Yaw', 0), 2)}, pitch {round(pose.get('Pitch', 0), 2)}"),
        _check("Not heavily tilted", abs(pose.get("Roll", 0)) <= 25, round(pose.get("Roll", 0), 2)),
    ]

    if face_occluded:
        checks.append(
            _check(
                "Face not occluded",
                face_occluded.get("Value") is not True,
                face_occluded.get("Value"),
            )
        )

    passed_count = sum(1 for item in checks if item["passed"])
    score = round((passed_count / len(checks)) * 100)
    required_pass = all(item["passed"] for item in checks)

    return {
        "status": "PASS" if required_pass else "FAIL",
        "score": str(score),
        "checks": checks,
    }


def _get_session(session_id):
    item = dynamodb.Table(KYC_TABLE).get_item(Key={"session_id": session_id}).get("Item")
    if not item:
        return _error_response("Session not found.", 404)
    return _response(200, item)


def _extract_identity_fields(text_response, allow_document_fallback=True):
    detected_lines = [
        t["DetectedText"]
        for t in text_response["TextDetections"]
        if t["Type"] == "LINE" and t["Confidence"] > 80
    ]
    all_lines = [
        t["DetectedText"]
        for t in text_response["TextDetections"]
        if t["Type"] == "LINE" and t["Confidence"] > 50
    ]
    all_words = [
        t["DetectedText"]
        for t in text_response["TextDetections"]
        if t["Type"] == "WORD" and t["Confidence"] > 40
    ]

    print(f"Detected lines (80%+): {detected_lines}")
    print(f"All lines (50%+): {all_lines}")
    print(f"All words (40%+): {all_words}")

    skip_keywords = [
        "GHANA", "CARD", "REPUBLIC", "ECOWAS", "IDENTIT", "CEDEAO",
        "BILREV", "IDENTIDADE", "NATIONAL", "IDENTIFICATION", "AUTHORITY",
        "SURNAME", "FORENAME", "PERSONAL ID", "DOCUMENT NUMBER", "NATIONALITY", "DATE OF",
        "PLACE OF", "DATE OF BIRTH", "DATE OF ISSUE", "DATE OF EXPIRY",
        "DIGITAL SIGNATURE", "NIA", "SEX", "PIN", "GHA)", "ACCRA",
        "PREVIOUS", "NOMS", "PRECEDENT", "NOM DE", "PRENOM",
        "LIEU", "SIGNATURE", "HEIGHT", "WEIGHT", "ISSUANCE",
        "RESIDENT", "PROFESSION", "MARITAL", "RELIGION", "CARTE",
    ]

    def is_header(line):
        upper = line.upper()
        return "/" in line or any(kw in upper for kw in skip_keywords)

    def is_date(line):
        return bool(re.search(r"\d{2}/\d{2}/\d{4}", line.strip()))

    def is_height_or_noise(line):
        stripped = line.strip()
        return bool(re.search(r"^\d+\.\d+$", stripped) or re.search(r"^\d{5,}$", stripped) or len(stripped) <= 1)

    def is_id_number(line):
        clean = re.sub(r"[^A-Z0-9]", "", line.upper().strip().replace("O", "0"))
        return bool(
            clean.startswith("GHA") and re.search(r"\d{8,}", clean)
            or re.search(r"^[A-Z]{2}\d{5,9}$", clean)
        )

    def canonicalize_gha(text):
        upper = text.upper().replace("O", "0")
        spaced_match = re.search(r"GHA[\W_]*([0-9]{8,10})(?:[\W_]*([0-9]))?", upper)
        if spaced_match:
            digits = spaced_match.group(1) + (spaced_match.group(2) or "")
            if len(digits) >= 10:
                return f"GHA-{digits[:9]}-{digits[9]}"
            if len(digits) == 9:
                return f"GHA-{digits}"

        compact = re.sub(r"[^A-Z0-9]", "", upper)
        compact_match = re.search(r"GHA([0-9]{9,10})", compact)
        if compact_match:
            digits = compact_match.group(1)
            if len(digits) >= 10:
                return f"GHA-{digits[:9]}-{digits[9]}"
            return f"GHA-{digits}"

        return None

    def find_gha_value(values, window_size=6):
        for value in values:
            gha_value = canonicalize_gha(value)
            if gha_value:
                return gha_value

        for i in range(len(values)):
            combined = " ".join(values[i : i + window_size])
            gha_value = canonicalize_gha(combined)
            if gha_value:
                return gha_value

        return None

    def is_name_line(line):
        stripped = line.strip()
        if len(stripped) < 2 or is_header(line) or is_date(line) or is_height_or_noise(line) or is_id_number(line):
            return False
        return sum(c.isalpha() for c in stripped) / len(stripped) >= 0.8

    name_lines = [line for line in detected_lines if is_name_line(line)]
    print(f"Name candidate lines: {name_lines}")

    if len(name_lines) >= 2:
        extracted_name = f"{name_lines[1]} {name_lines[0]}"
    elif len(name_lines) == 1:
        extracted_name = name_lines[0]
    else:
        fallback = [
            line
            for line in all_lines
            if not is_header(line)
            and not is_date(line)
            and not is_height_or_noise(line)
            and "/" not in line
            and sum(c.isalpha() for c in line) >= 4
        ]
        fallback.sort(key=lambda line: sum(c.isalpha() for c in line), reverse=True)
        extracted_name = fallback[0] if fallback else "NOT FOUND"

    extracted_id = "NOT FOUND"
    personal_id_label_keywords = ["PERSONAL ID", "ID NUMBER", "HUMERO"]
    document_label_keywords = ["DOCUMENT NUMBER", "NUMERO"]

    def find_gha_after_label(lines):
        for i, line in enumerate(lines):
            if any(kw in line.upper() for kw in personal_id_label_keywords):
                nearby_lines = lines[i + 1 : min(i + 8, len(lines))]
                gha_value = find_gha_value(nearby_lines)
                if gha_value:
                    return gha_value
        return None

    def find_document_number_after_label(lines):
        for i, line in enumerate(lines):
            if any(kw in line.upper() for kw in document_label_keywords):
                for candidate in lines[i + 1 : min(i + 5, len(lines))]:
                    if is_date(candidate) or is_height_or_noise(candidate) or "/" in candidate:
                        continue
                    clean = re.sub(r"[^A-Z0-9]", "", candidate.upper().replace("O", "0"))
                    if re.search(r"^[A-Z]{1,3}\d{5,}$", clean):
                        return candidate.strip()
        return None

    extracted_id = find_gha_value(all_lines) or "NOT FOUND"
    if extracted_id == "NOT FOUND":
        extracted_id = find_gha_value(detected_lines) or "NOT FOUND"
    if extracted_id == "NOT FOUND":
        extracted_id = find_gha_value(all_words) or "NOT FOUND"

    if extracted_id == "NOT FOUND":
        extracted_id = find_gha_after_label(detected_lines) or "NOT FOUND"
    if extracted_id == "NOT FOUND":
        extracted_id = find_gha_after_label(all_lines) or "NOT FOUND"

    # Last resort: use the non-GHA document number only when the card's personal
    # ID could not be reconstructed from the OCR output.
    if allow_document_fallback and extracted_id == "NOT FOUND":
        extracted_id = find_document_number_after_label(detected_lines) or "NOT FOUND"
    if allow_document_fallback and extracted_id == "NOT FOUND":
        extracted_id = find_document_number_after_label(all_lines) or "NOT FOUND"

    print(f"Extracted ID: {extracted_id}")
    return extracted_name, extracted_id, detected_lines


def _is_ghana_personal_id(value):
    return bool(re.match(r"^GHA-\d{9}(?:-\d)?$", value or ""))


def _textract_to_text_response(textract_response):
    text_detections = []
    for block in textract_response.get("Blocks", []):
        block_type = block.get("BlockType")
        text = block.get("Text")
        if block_type not in {"LINE", "WORD"} or not text:
            continue
        text_detections.append(
            {
                "DetectedText": text,
                "Type": block_type,
                "Confidence": block.get("Confidence", 0),
            }
        )
    return {"TextDetections": text_detections}


def _verify_kyc(event):
    body = json.loads(event.get("body") or "{}")
    id_bytes = _decode_image("id_image", body.get("id_image"))
    selfie_bytes = _decode_image("selfie", body.get("selfie"))

    session_id = str(uuid.uuid4())
    id_key = f"sessions/{session_id}/id.jpg"
    selfie_key = f"sessions/{session_id}/selfie.jpg"

    s3.put_object(Bucket=KYC_BUCKET, Key=id_key, Body=id_bytes)
    s3.put_object(Bucket=KYC_BUCKET, Key=selfie_key, Body=selfie_bytes)

    id_image = {"S3Object": {"Bucket": KYC_BUCKET, "Name": id_key}}
    selfie_image = {"S3Object": {"Bucket": KYC_BUCKET, "Name": selfie_key}}

    id_faces = rekognition.detect_faces(Image=id_image, Attributes=["ALL"])
    selfie_faces = rekognition.detect_faces(Image=selfie_image, Attributes=["ALL"])

    if not id_faces["FaceDetails"]:
        return _error_response("No face detected in ID card image. Use a clear photo ID.")
    if not selfie_faces["FaceDetails"]:
        return _error_response("No face detected in selfie. Ensure your face is clearly visible.")

    liveness = _assess_passive_liveness(selfie_faces["FaceDetails"])

    text_response = rekognition.detect_text(Image=id_image)
    extracted_name, extracted_id, detected_lines = _extract_identity_fields(text_response)

    if not _is_ghana_personal_id(extracted_id):
        try:
            textract_response = textract.detect_document_text(
                Document={"S3Object": {"Bucket": KYC_BUCKET, "Name": id_key}}
            )
            textract_text_response = _textract_to_text_response(textract_response)
            textract_name, textract_id, textract_lines = _extract_identity_fields(
                textract_text_response,
                allow_document_fallback=False,
            )
            if _is_ghana_personal_id(textract_id):
                extracted_id = textract_id
                detected_lines = textract_lines or detected_lines
                if extracted_name == "NOT FOUND" and textract_name != "NOT FOUND":
                    extracted_name = textract_name
                print(f"Using Textract Personal ID fallback: {extracted_id}")
        except Exception as exc:
            print(f"Textract Personal ID fallback failed: {str(exc)}")

    compare_response = rekognition.compare_faces(
        SourceImage=id_image,
        TargetImage=selfie_image,
        SimilarityThreshold=70,
    )
    face_matches = compare_response.get("FaceMatches", [])
    face_confidence = round(face_matches[0]["Similarity"], 2) if face_matches else 0.0
    face_match_status = "PASS" if face_confidence >= 70.0 else "FAIL"
    status = "PASS" if face_match_status == "PASS" and liveness["status"] == "PASS" else "FAIL"

    result = {
        "session_id": session_id,
        "timestamp": datetime.utcnow().isoformat(),
        "status": status,
        "face_match_status": face_match_status,
        "face_confidence": str(face_confidence),
        "liveness_status": liveness["status"],
        "liveness_score": liveness["score"],
        "liveness_checks": liveness["checks"],
        "extracted_name": extracted_name,
        "extracted_id_number": extracted_id,
        "detected_text_lines": detected_lines,
    }

    dynamodb.Table(KYC_TABLE).put_item(Item=result)
    print(
        f"KYC complete. Session: {session_id} | Status: {status} | "
        f"Face: {face_confidence}% | Liveness: {liveness['status']} ({liveness['score']}%)"
    )

    return _response(200, result)


def lambda_handler(event, context):
    try:
        method = event.get("requestContext", {}).get("http", {}).get("method")

        if method == "OPTIONS":
            return _response(200, {})

        if method == "GET":
            session_id = (event.get("pathParameters") or {}).get("session_id")
            if not session_id:
                return _error_response("Missing session_id path parameter.")
            return _get_session(session_id)

        return _verify_kyc(event)

    except ValueError as exc:
        print(f"KYC validation error: {str(exc)}")
        return _error_response(str(exc))
    except rekognition.exceptions.InvalidImageFormatException:
        print("KYC error: Invalid image format submitted")
        return _error_response("Unsupported format. Please use JPEG or PNG.")
    except Exception as exc:
        print(f"KYC error: {str(exc)}")
        return _error_response("Verification failed. Check Lambda logs for details.", 500)
