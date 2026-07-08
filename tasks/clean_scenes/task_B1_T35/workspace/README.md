# Key Rotation Compliance Review

## Overview
This workspace supports the quarterly key rotation compliance review for active integrations. Your task is to assess whether all in-scope integrations have rotated their keys within the mandatory 90-day window.

## Workspace Contents
- `README.md` – This file.
- `rotation_review_brief.md` – Lists the integration IDs in scope and the rotation interval.

## Task Instructions
1. Retrieve active integrations from the integrations service and fetch the details for each in-scope integration. The integration’s `notes` field contains the last rotation date (e.g., "last rotated YYYY-MM-DD").
2. Look up the key rotation policy article from the knowledge base.
3. For each integration, compare its last rotation date against the policy interval; determine compliance (compliant if the last rotation is within 90 days of today, 2027-06-24).
4. Record the findings for each integration in the rotation status knowledge-base article (article ID `KB-ROT-STATUS`). The article body should clearly state the compliance status per integration.
5. Report completion once the article is updated.

## Service Endpoints
- Integrations service: `/integrations/items` (list), `/integrations/items/get` (details)
- Knowledge base: `/knowledge_base/search`, `/knowledge_base/articles/get`, `/knowledge_base/articles/update`

Use the standard mock API skills to interact with these endpoints. No additional credentials or environment configuration is needed for this mock environment.