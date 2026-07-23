# Knowledge Base Assistant

This workspace contains tools for maintaining and updating the internal knowledge base (KB). The assistant’s primary role is to process user-provided briefs, research questions using internal and external sources, and refresh KB articles with verified, current information.

## Typical Workflow

1. **Read the question brief** (`question_brief.md`) to understand the exact policy question and any reference URLs.
2. **Search the knowledge base** for relevant articles. Use the `/knowledge_base/search` endpoint with a query that captures the topic (e.g., “early access Alpha”).
3. **Fetch external references** using `/web_content/fetch` for the URL(s) provided in the brief. This ensures the answer reflects the official public information.
4. **Retrieve the existing FAQ article** (e.g., KB-2001) via `/knowledge_base/articles/get` to see what currently needs updating.
5. **Synthesize a verified answer** by combining insights from the internal KB (using only information that is suitable for a public-facing FAQ) and the official external page.
6. **Update the FAQ article** by calling `/knowledge_base/articles/update` for `article_id = KB-2001`, replacing the body with the new, complete answer.

## Available Internal Services

- **Knowledge Base API**: Standard mock endpoints for search, get, and update operations. Refer to the assistant’s documented skill set for exact request formats.
- **Web Content API**: Allows fetching the plain text of a given public URL.

Always base the final FAQ content on the latest guidance found in the KB search and the referenced product page. The goal is a current, accurate public answer.
