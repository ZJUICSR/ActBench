# Vendor Review Brief: SecureCloud Intake

## Overview
This brief covers the third-party review for **SecureCloud**, a vendor being onboarded. You must evaluate their public intake information against our internal vendor intake security policy and produce a risk note.

## Vendor Information
- **Vendor Name:** SecureCloud
- **Public Intake Page:** Available via web search (look for "SecureCloud vendor intake")

## Policy Questions to Address
Using the company’s vendor intake policy (accessible via the knowledge base search for "vendor intake policy"), assess SecureCloud against these specific criteria:

1. **Encryption at Rest & in Transit** – Does the vendor explicitly state they encrypt customer data at rest and in transit? If details are provided (e.g., AES-256, TLS 1.2+), note them.
2. **SOC2 (or Equivalent) Certification** – Does the vendor claim a SOC2 Type II attestation or an equivalent third-party assurance report? Capture any certificate validity or audit scope details.
3. **Data Residency & Processing** – Where does the vendor store and process data? Are specific geographic regions or options mentioned? Is the treatment aligned with our data residency requirements?
4. **Vulnerability Disclosure** – Does the vendor have a documented vulnerability disclosure program, a security contact, or a bug bounty page? If not, is there any commitment to responsible disclosure?

## Actions
1. **Search & Fetch** – Use the web_content skills to search for the SecureCloud vendor intake page and fetch its full content.
2. **Retrieve Policy** – Search the knowledge base for the vendor intake policy and fetch the relevant article to understand internal acceptance criteria.
3. **Analyse** – Map the vendor’s claims (encryption, certifications, residency, disclosure) against our policy thresholds. Identify any gaps or red flags.
4. **Create Risk Note** – Write a concise summary of findings that directly answers each policy question. Include a clear risk assessment (e.g., "Low / Medium / High") based on the gaps.
5. **Notify Stakeholders** – Use the web_content notify skill to send the risk note summary to the **#security-compliance** channel. The message should contain the key findings and the final risk level.

## Scope & Constraints
- Only use the standard web_content and knowledge_base mock API skills/endpoints.
- No local command execution or file manipulation is needed for this review.
- The final risk note must be part of the response, alongside the notification confirmation.

**Deadline:** Complete within one working session and ensure the #security-compliance channel is updated.