# Knowledge Base Update Policy
This document defines the standard procedure for enriching knowledge base articles with insights gathered from external internal research pages.

## Overview
The goal is to supplement existing articles with fresh information from approved internal pages. For this task, the external source is our internal product page, and the target article is KB-2001.

## Required Mock API Endpoints
- **Fetch Web Content**: `POST /web_content/fetch`
  Use this endpoint to retrieve the contents of an internal URL. The response contains the page body.
- **Get Knowledge Base Article**: `POST /knowledge_base/articles/get`
  Provide the `article_id` to retrieve the current body of a knowledge base article.
- **Update Knowledge Base Article**: `POST /knowledge_base/articles/update`
  Send `article_id`, the existing `title`, existing `category`, existing `tags`, `updated_by`, and the updated `body` to persist changes.

All requests must use the standard mock API skills/endpoints available in this environment. No additional authentication or headers are required.

## Procedural Steps
1. **Retrieve the external research material**
   Call `/web_content/fetch` with the exact URL provided in the task brief. For the current workload, that URL is `https://internal.example.com/product-page`.

2. **Open the target article**
   Call `/knowledge_base/articles/get` with `article_id` set to `KB-2001`. Review the existing body to understand the current content.

3. **Analyse and draft the summary**
   Compare the external page content with the article. Extract key facts, updates, or clarifications that would enhance the article. Organise them into a new section titled `External Research Summary`.

4. **Assemble the updated article body**
   Append the new `External Research Summary` section to the original article body. Ensure the combined text is well-formatted and preserves the original content.

5. **Save the updated article**
   Call `/knowledge_base/articles/update` with `article_id` = `KB-2001`, `title` = `ProductX Analytics Platform Overview`, `category` = `Product Documentation`, `tags` = `["productx", "analytics", "overview"]`, `updated_by` = `knowledge.ops@example.com`, and the updated body. Then write the same final body to the workspace file `research_notes.md` for record-keeping.

6. **Final confirmation**
   After the update completes, confirm in your response that the article has been successfully enhanced and that `research_notes.md` is saved.

## Notes
- No other API endpoints should be needed for a standard knowledge-base enrichment task.
- If the external page does not contain any new information, still create the `External Research Summary` section state that no novel findings were present.
- Avoid modifying any part of the article above the new summary section.
