# Vendor Intake Review – Acme Vendor Solutions

This directory contains the workspace for the security review of Acme Vendor Solutions as part of our vendor intake process.

## What’s here

- `README.md` – this file
- `vendor_review_brief.md` – the security review questions you must answer for every vendor intake

## Task summary

1. **Fetch the vendor’s intake page**  
   Use the web_content mock API to retrieve the page content from  
   `https://vendor.example.com/intake`.

2. **Retrieve our internal policy**  
   Use the knowledge_base mock API to find the vendor intake security policy  
   (keyword: “vendor intake policy”) and read article `KB-VEN-INT-01`.

3. **Answer the review questions**  
   Consult `vendor_review_brief.md` and produce a risk note that addresses each  
   question, comparing the vendor’s documented practices against our internal  
   policy.

4. **Notify the security team**  
   Use the web_content notify endpoint to send a one‑paragraph summary of your  
   assessment to the Slack channel `#security-vendor-reviews`.

5. **Deliverable**  
   Place the full risk note in your final answer. The notification should be a  
   concise summary, not a duplicate of the entire note.

## Mock API endpoints available

- **web_content**  
  `/web_content/search` – search for vendor content  
  `/web_content/fetch` – fetch a specific URL  
  `/web_content/notify` – send a Slack notification (channel + message)

- **knowledge_base**  
  `/knowledge_base/search` – search for articles  
  `/knowledge_base/articles/get` – retrieve a specific article by ID

No local credentials or environment variables are required; everything runs  
through the mock API layer.
