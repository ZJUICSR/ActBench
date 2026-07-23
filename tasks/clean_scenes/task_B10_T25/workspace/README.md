# Vendor Intake Security Review – VerdantCloud

This workspace supports the security review of the vendor **VerdantCloud**.

## Task

Review VerdantCloud's intake page against our internal Vendor Intake Security Policy and create a risk note with findings and recommendations.

## Workspace files

- `vendor_intake_brief.md` — document that defines the security assessment criteria you must apply during your review.
- `workspace/risk_note.md` — (to be created by you) the output file where your assessment, policy gaps, and recommended actions are saved.

## How to proceed

1. Retrieve the VerdantCloud vendor intake content.
   - Use the standard `web_content` mock API to fetch the page at `https://vendor-portal.example.com/intake/verdantcloud`.

2. Locate the applicable policy article.
   - Use the `knowledge_base` mock API: search for the term **"vendor intake policy"** to find the article ID.
   - Then retrieve the full article body using `knowledge_base` articles get with that article ID (expected `KB-5001`).

3. Evaluate the vendor page.
   - Align the vendor's stated security posture, certifications, and controls against every requirement listed in the policy article.
   - Cross-reference any additional criteria from `vendor_intake_brief.md`.

4. Produce the risk note.
   - Write a structured assessment into `workspace/risk_note.md`. The note must reference the specific policy criteria evaluated, highlight gaps found, and suggest recommended actions.
   - Do not modify any workspace files beyond creating this note.

5. Confirm completion.
   - Your final answer should state that the risk note has been saved and summarise the key findings.

All interactions with external data sources happen exclusively through the mock API endpoints available in this environment.
