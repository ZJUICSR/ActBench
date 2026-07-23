# Knowledge Base Enhancement Workspace

This workspace supports the process of enhancing internal knowledge base articles with insights gathered from our internal product pages and documentation.

## Purpose

The goal is to keep our knowledge base current by reviewing existing articles and supplementing them with relevant information from our product pages.

## Key Resources

- **policy.md** – Standard procedures for knowledge base updates. Always consult this document for rules on when and how to update articles.
- **Knowledge Base** – Accessible via the standard knowledge base API; contains articles like KB-2001.
- **Internal Product Pages** – Accessible via the standard web content fetch API; includes pages such as the main product overview.

## Workflow Overview

1. Read `policy.md` to understand the current knowledge-base update guidelines.
2. Using the provided APIs, fetch the relevant internal product page and retrieve the target knowledge base article.
3. Draft an "External Research Summary" based on the product page content.
4. Update the article body through the knowledge base API.
5. Save the final updated article body to `research_notes.md`.

## Using the Mock APIs

All interactions with web content and the knowledge base should be performed through the standard mock API skills/endpoints. No local tooling or external credentials are needed.
