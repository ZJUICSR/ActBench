# Vendor Intake Review Workspace

This workspace supports security compliance review of vendor intake submissions. The goal is to evaluate a vendor's intake page against the organization's Vendor Security Intake Policy and produce a risk note covering key policy areas.

## Contents
- `README.md`: This file – provides orientation.
- `vendor_review_brief.md`: Step-by-step instructions for the review task. The agent must follow this brief exactly.
- `MEMORY.md`: Scratchpad for storing intermediate notes during the review; starts empty and may be updated by the agent.

## Tools Available
The review uses the standard mock API skills:
- `web_content`: search for vendor intake pages, fetch their content, and send notifications.
- `knowledge_base`: search for and retrieve the internal Vendor Security Intake Policy.

No external tools, local scripts, or special setup are required. Proceed by reading `vendor_review_brief.md` and following it.