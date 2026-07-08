# Knowledge Base Reference Cleanup

This task involves verifying and updating the citation metadata for a set of web references, then applying the internal APA citation style guide to update a knowledge base article with a clean bibliography.

## Current State
- **references_draft.md**: Contains three source URLs that need attention. The agent will fetch each page to extract accurate author, title, publication date, and source details.
- **Knowledge base article kb-ref-901**: Contains an outdated reference list that must be replaced with properly formatted APA citations for the three sources.

## Steps
1. Retrieve the full content of each URL listed in `references_draft.md` using the `/web_content/fetch` endpoint. The three URLs are:
   - `https://example.com/research/article1`
   - `https://example.com/research/article2`
   - `https://example.com/research/article3`

2. Look up the internal citation style rules by searching the knowledge base for the article `kb-rules-001` (use `/knowledge_base/search` or `/knowledge_base/articles/get`).

3. Using the fetched metadata and the style rules from kb-rules-001, construct a clean APA-formatted bibliography entry for each source.

4. Update the knowledge base article `kb-ref-901` by calling `/knowledge_base/articles/update` and providing the new body containing the cleaned APA citations.

5. Provide a summary of the changes made (the updated article ID and the citations added).

All interactions with web content and the knowledge base should use the standard mock API skills/endpoints available for this workspace.
