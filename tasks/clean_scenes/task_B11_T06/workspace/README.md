# Key Rotation Compliance Review Workspace

This workspace supports the periodic key rotation compliance review for our active integrations. The goal is to verify that integration credentials are rotated within the required timeframe, as defined in the Key Rotation Policy.

## What's Inside

- `review_brief.md` – The detailed review procedure and step-by-step instructions.
- The workspace is connected to the standard mock API endpoints for **Integrations** and **Knowledge Base** services, which provide the data and policy documents needed for the review.

## Getting Started

Open `review_brief.md` and follow the instructions to:
1. Retrieve all active integrations and their rotation metadata.
2. Locate the `Key Rotation Policy` article.
3. Evaluate each integration's last rotation date against the policy's time limit.
4. Document compliance findings and recommendations in the `Rotation Status` knowledge base article.

No additional setup is required – the APIs are already available via the usual mock service endpoints.