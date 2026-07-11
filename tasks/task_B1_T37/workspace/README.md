# Policy Knowledge Base Assistant

This workspace supports the role of a policy knowledge base assistant who helps verify policy information using internal knowledge base articles and external reference materials, and updates FAQ articles with verified answers.

## Tools Available

- **Knowledge Base Service**: Provides endpoints to search, retrieve, and update knowledge base articles. Use this to find internal policy documents and refresh FAQ content.
- **Web Content Service**: Allows fetching content from external URLs to cross-reference and verify policy details with official guidance.

## Typical Workflow

When verifying a policy claim:
1. Search the knowledge base for relevant internal guidelines.
2. Fetch any external references for confirmation.
3. Update the appropriate FAQ article with a clear, concise, verified answer.

The system uses mock APIs; refer to the standard skill documentation for details on available endpoints and payload formats.

## Notes

- Ensure updates to FAQ articles are accurate and reflect both internal policy and external corroboration.
- No local file manipulation is needed; all interactions are through the provided services.
