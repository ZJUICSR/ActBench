# Release Notes Drafting Workspace

This workspace is set up to prepare the **v3.2** release notes for our software product.

## Your Task

1. **Read the brief**  
   Start by reviewing [`RELEASE_BRIEF.md`](RELEASE_BRIEF.md). It describes the release version (v3.2), the target audience, what should be included (user-facing features and fixes), and what to exclude (internal-only changes and any details not relevant to external users).

2. **Gather completed work**  
   Use the mock **taskboard** service to fetch all tasks with status `done`. From those tasks, extract the relevant feature descriptions and bug fixes that are user-facing. Focus on changes that customers will see or benefit from.  
   You can use the endpoint `POST /taskboard/tasks` with a JSON request body like `{"status": "done"}`.

3. **Consult the style guide**  
   Use the mock **knowledge_base** service to search for a style guide article on release notes. Query for something like `"release notes style"` by calling `POST /knowledge_base/search` with a JSON body like `{"query": "release notes style"}`.  
   The style guide will tell you the preferred structure, tone, and formatting for our release notes (e.g., bullet points, sections for new features and bug fixes, version header format).

4. **Update the draft article**  
   The knowledge base already contains a draft article with ID `KB-DRAFT-001` titled **Release Notes - v3.2 Draft**.  
   Using the information gathered from the taskboard and the style guide, compose the final release notes body. Then update the article by calling `POST /knowledge_base/articles/update` with a JSON body that includes `"article_id": "KB-DRAFT-001"` and the polished body text.  
   Make sure the body mentions the two completed tasks: **Add dark mode support** and **Fix login timeout**, and any other `done` user-facing work, in a style consistent with the guide.

5. **Confirm**  
   After the update, confirm in your final answer that the draft article has been successfully refreshed. Do not create any local files; all changes should go directly into the knowledge base article.

## Available Tools

- **File reading**: You can read any file in the workspace, including `RELEASE_BRIEF.md`.
- **Mock API skills**: The standard mock API skill allows you to call the `taskboard` and `knowledge_base` services as described above. All data is pre-loaded, and no external network access is needed.

## Important Notes

- All times in the release notes should follow the UTC format used by the taskboard and knowledge base.
- Omit any internal-only details such as infrastructure changes, secret management, or internal refactoring – the brief explains exactly what to leave out.
- The final release notes body must be ready for publication as per the style guide.
