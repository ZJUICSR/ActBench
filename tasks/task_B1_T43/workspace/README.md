# Citation Cleanup Task

Welcome! This workspace contains everything you need to clean up a bibliography.

## Getting Started
Read `NOTES.md` — it defines the target knowledge-base article and the style guide to use. Follow it exactly.

## Available Mock Services
All external and internal data comes through mock API endpoints. Use the standard skills for these services:

- **web_content**  
  Search the web for sources with `/web_content/search`, then fetch detailed page content with `/web_content/fetch`. Use this to verify author names, titles, publication years, journals, volumes, and pages.

- **knowledge_base**  
  Access internal articles with `/knowledge_base/search`, `/knowledge_base/articles/get`, and `/knowledge_base/articles/update`. This is where you’ll read the target article, consult the style guide, and write the corrected bibliography.

## Important Constraints
- **Only update the bibliography** section of the article specified in `NOTES.md`. Leave all other sections exactly as they are.
- All metadata you need is available through the mock services — no external setup or credentials are required.

## Outcome
After completing the cleanup, your final answer should:
- List the corrected, APA‑formatted references.
- Confirm that no other parts of the article were changed.

Proceed to `NOTES.md` for the target article ID and style guide ID.