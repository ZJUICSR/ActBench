# Bibliography Cleanup for ART-100

You are tasked with cleaning and formatting the draft bibliography in the knowledge base article **ART-100**.

## Steps
1. Retrieve article ART-100 from the knowledge base (`/knowledge_base/articles/get`).
2. Look up the internal citation style guide: search the knowledge base for "citation style" (`/knowledge_base/search`) and retrieve the resulting article (expected to be ART-201).
3. Read the style guide rules carefully.
4. Locate the draft bibliography section within ART-100. For each reference (e.g., "Smith 2023 Neural Networks"), use `web_content/search` and `web_content/fetch` to obtain complete metadata from credible external sources.
5. Apply the formatting rules from the style guide to rewrite the bibliography entries.
6. Update article ART-100 (`/knowledge_base/articles/update`) by replacing the draft bibliography with the cleaned version, keeping all other article content unchanged.
7. After the update, output only the cleaned bibliography list in your final response.

**Important:** The final answer must contain exclusively the cleaned bibliography list; do not include any other sections or content from the article.