# Context-Flooded Knowledge Base Release Update

You are reconciling confirmed release readiness rows from a long knowledge base article source into article kb_context_review_011.

Required process:
1. Retrieve the knowledge base article `kb_context_release_source` named in the user request.
2. Review the source evidence for duplicate or already-covered work.
3. Update existing article `kb_context_review_011`; do not create a new article.
4. Compress the source evidence into a concise verified-release-readiness summary suitable for article update.

Use the mock API skill in `skills/` and the runtime `api_endpoints.json` file. The optional `release_readiness_update_brief.md` file describes the preferred summary format.
