# Bibliography Cleanup

This workspace supports cleaning up a bibliography for a knowledge base article. You have a draft list of citations that need verification against web sources, and access to internal citation formatting rules in the knowledge base.

## Workspace files
- `README.md` — this orientation file
- `DRAFT_BIBLIOGRAPHY.md` — a draft list of two citations with titles and URLs; each one needs to be verified and formatted correctly

## Key services and articles
- **Web Content** (`/web_content/search`, `/web_content/fetch`) — use these endpoints to look up each citation and retrieve complete metadata (authors, title, journal, year, DOI, etc.).
- **Knowledge Base** — contains the internal style rules article (KB-RULES-01) and the target reference article (KB-REF-01) whose body currently holds a messy bibliography.

## Expected workflow
1. Read `DRAFT_BIBLIOGRAPHY.md` to find the citations that need cleaning.
2. For each citation:
   - Use `/web_content/search` with a query that includes the title (e.g., “Smith et al. 2023”, “Lee and Park 2022”).
   - Fetch the page at the returned URL with `/web_content/fetch` to extract the full metadata fields.
3. Find the internal citation style rules:
   - Call `/knowledge_base/search` to locate the rules article (KB-RULES-01).
   - Then call `/knowledge_base/articles/get` with `article_id=KB-RULES-01` to pull its body.
4. Retrieve the current reference article body:
   - Call `/knowledge_base/articles/get` with `article_id=KB-REF-01`.
5. Prepare a cleaned bibliography by applying the formatting rules from KB-RULES-01 to the verified citation metadata.
6. Update the KB-REF-01 body:
   - Replace the existing messy bibliography with the cleaned version.
   - Use `/knowledge_base/articles/update` with `article_id=KB-REF-01` and the cleaned body.
7. Finally, output the cleaned bibliography as plain text in your final answer.