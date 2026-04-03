# KYC Verification System — Demo Script
**Duration: ~3 minutes | Presenter: [Your Name]**

---

## Before You Start (Setup Checklist)
- [ ] Frontend open in browser: `http://rekkyc-frontend.s3-website-us-east-1.amazonaws.com`
- [ ] AWS Console open in second tab → DynamoDB → `kyc_results` table
- [ ] Two test image pairs ready:
  - **PASS pair**: Ghana Card + matching selfie
  - **FAIL pair**: Ghana Card + a different person's photo
- [ ] Architecture diagram on standby (slide or drawn)

---

## Scene 1 — Architecture Overview (30 seconds)

> *"Let me quickly walk you through what we built."*

Point to the architecture diagram:

```
Frontend (S3)  →  API Gateway  →  Lambda (KYCVerificationHandler)
                                      ↓               ↓
                               Rekognition       DynamoDB
                             DetectText          kyc_results
                             CompareFaces
```

> *"A user uploads two things — their Ghana Card and a live selfie.
> Our Lambda function extracts the name and ID number from the card,
> then compares the face on the card to the selfie using Amazon Rekognition.
> The result — PASS or FAIL — comes back in under 3 seconds,
> and every verification is logged to DynamoDB as an audit record."*

---

## Scene 2 — PASS Case (45 seconds)

> *"Let me show you a live verification."*

1. Open the frontend in the browser
2. Upload the Ghana Card image → file name appears in green
3. Upload the matching selfie → file name appears in green
4. Click **"Verify Identity"**
5. Result card appears — point to each field:

> *"92.17% face match confidence — PASS.*
> *The system correctly extracted the name — KUMI —*
> *and the ID number — AR7437976 — directly from the Ghana Card.*
> *No manual data entry. No human agent. Under 3 seconds."*

---

## Scene 3 — FAIL Case (30 seconds)

> *"Now watch what happens when the selfie doesn't match the card."*

1. Keep the same Ghana Card uploaded
2. Replace the selfie with a **different person's photo**
3. Click **"Verify Identity"**
4. Red FAIL card appears with low confidence score (~10–15%)

> *"The system correctly rejected a mismatched identity.*
> *This is exactly the fraud prevention layer that Ghana's*
> *SIM re-registration exercise needs — catching people*
> *attempting to register a SIM using someone else's card."*

---

## Scene 4 — DynamoDB Audit Trail (30 seconds)

Switch to the AWS Console tab → DynamoDB → `kyc_results`

> *"Every single verification — pass or fail — is written here automatically.*
> *Session ID, timestamp, status, confidence score, extracted name and ID.*
> *This is the audit trail. For telecoms and regulators,*
> *this record is as important as the verification itself.*
> *It proves who was verified, when, and with what confidence."*

Scroll to show both records just created (PASS and FAIL).

---

## Scene 5 — Original Pipeline Still Running (20 seconds)

> *"One more thing — our KYC system is built as an extension,*
> *not a replacement. The original image analysis pipeline*
> *is still running independently."*

Drop any `.jpg` into the `rekimage-inputs` S3 bucket → show the JSON analysis file appear in `rekanalysis-outputs`.

> *"Same infrastructure. Two separate functions. Fully modular."*

---

## Scene 6 — Closing (15 seconds)

> *"Ghana's Communications Ministry has mandated SIM re-registration*
> *tied to the Ghana Card. The current approach — manual agent verification*
> *at service centres — doesn't scale to 40 million subscribers.*
> *We built a prototype that does.*
>*
> *This is what identity infrastructure looks like when you build it*
> *on the cloud. The demo you just saw is not a simulation.*
> *That was a real Ghana Card. That was a real result.*
> *The rest is execution."*

---

## Q&A Anticipated Questions

| Question | Answer |
|----------|--------|
| What if someone uses a printed photo of the ID owner? | Liveness detection is the next addition — Rekognition Face Liveness prevents static photo spoofing |
| Is this connected to NIA's database? | Not yet — currently reads the card visually. Direct NIA API integration is the next phase |
| What does it cost per verification? | Rekognition CompareFaces costs ~$0.001 per call. At scale the cost per verification is under GHS 0.01 |
| Can it handle other ID types? | Yes — tested on ECOWAS cards. Any card with a face photo and text is compatible |
| How does the team split the work? | Backend (Lambda), Infrastructure (Terraform), Frontend (UI), QA/Demo — one track each |
