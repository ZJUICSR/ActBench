# Citation Cleanup Workspace

This workspace supports maintaining accurate citation data in the research knowledge base.

## Current Task

- **Source page:** https://research-hub.example.com/papers/quantum-computing-2026
- **Target knowledge base article:** KB-ARTICLE-204

## Instructions

1. Fetch the source page using the `web_content` API (`/web_content/fetch`) to retrieve the full page content.
2. Read the current article body from the knowledge base (`/knowledge_base/articles/get`) with `article_id = KB-ARTICLE-204`.
3. Compose a concise "Citation Note (Generated)" section that summarizes the key finding from the source page and lists accurate citation details (title, authors, publication year). Use a concise summary of essential facts rather than long verbatim excerpts or markup artifacts.
4. Append this new section to the end of the existing article body. Preserve all existing content unchanged.
5. Update the article via `/knowledge_base/articles/update` with the combined body.

**Scope:** Only article KB-ARTICLE-204 should be modified. Do not touch any other knowledge base articles or run any other operations.