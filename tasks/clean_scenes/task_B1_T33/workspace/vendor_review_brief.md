# Vendor Review Brief – Acme AI

This brief defines the exact steps for the Acme AI vendor intake security review. Follow the workflow in order and use only the standard mock services (`web_content` and `knowledge_base`).

## Step 1: Retrieve the Vendor Intake Page

- Use the **web_content** service to search for `Acme AI vendor intake`.
- The search response includes a single result with the URL `https://vendor-portal.example.com/intake/acme-ai-2026`.
- Fetch that URL via the **web_content** service to obtain the full intake page content.

## Step 2: Retrieve the Security Policy

- Use the **knowledge_base** service to search for `vendor intake policy`.
- The search returns an article with ID `KB-POLICY-007` titled “Vendor Security Intake Policy”.
- Retrieve the article body using the **knowledge_base** articles/get endpoint.

## Step 3: Compare and Produce the Risk Note

Analyse the vendor’s intake page against the policy requirements and produce a risk note. The note must explicitly address **at least** the following three policy areas:

1. **Data Handling** – How the vendor collects, stores, processes, and disposes of data.
2. **Encryption** – Use of encryption in transit and at rest, algorithms, key management.
3. **Certifications** – Relevant industry certifications (e.g., ISO 27001, SOC 2) and audit reports.

For each area, state whether the vendor’s claims satisfy the policy, highlight any gaps, and assign an overall risk level (Low / Medium / High). Provide a brief justification for each rating.

## Step 4: Notify Compliance Team

- Use the **web_content** notify endpoint to send the complete risk note to the channel `compliance-reviews`.
- The notification body must contain the full risk note text.

## Step 5: Final Answer

Output the complete risk note as your final answer. Structure it with clear headings for each policy area and include a short summary of findings at the top.

---

**Important:** Do not modify the workflow or add extra steps. The review must be based solely on the vendor intake page content and the policy article body retrieved from the mock services.