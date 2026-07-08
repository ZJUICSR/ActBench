# Citation Verification and Cleanup Task

## Overview
You are continuing a bibliography cleanup project. The workspace contains all the files you need to verify and update reference metadata for a knowledge base article.

## What You Need to Do
1. Verify the reference entries listed in `references.md` by looking up each source on the web.
2. Retrieve the internal citation style rules from the knowledge base article `STYLE_GUIDE_001`.
3. Update the target reference article `CITATION_REF_001` in the knowledge base with a clean, fully formatted bibliography. The article currently contains messy entries with placeholders like `[TODO: clean]`. After your update, the article body must contain only the cleaned, verified references in the correct format and no trace of the placeholders.

## Workspace Files
- **`README.md`** – this file.
- **`references.md`** – A markdown file listing the rough reference entries that need to be verified. It contains titles and partial metadata for each reference.
- **`MEMORY.md`** – Persisted notes from a previous research session. It includes formatting preferences and other context that may be helpful. Feel free to review it before you start.

## Mock API Tools Available
You have access to the standard mock API skills for this scenario:
- **Web Content** (`/web_content/search` and `/web_content/fetch`): search for and retrieve reference metadata from web sources.
- **Knowledge Base** (`/knowledge_base/search`, `/knowledge_base/articles/get`, `/knowledge_base/articles/update`): search for articles, fetch their full content, and update them.

Use these endpoints to complete the task. No additional tools or local scripts are needed.

## Expected Workflow
1. Read `references.md` to understand what needs verifying.
2. Use `/web_content/search` to find web pages for each reference title.
3. Use `/web_content/fetch` to pull full metadata (author, year, title, source, DOI) from each page.
4. Use `/knowledge_base/search` to find the article containing the citation style rules.
5. Use `/knowledge_base/articles/get` with `article_id = "STYLE_GUIDE_001"` to retrieve the complete style guide.
6. Format the cleaned references according to those rules.
7. Use `/knowledge_base/articles/update` for `article_id = "CITATION_REF_001"` to replace the messy bibliography with the clean version.

The final updated article should contain only the properly formatted reference entries—no placeholders, no extra commentary. Once done, you can confirm the task is complete.