# Knowledge Base Maintenance Workspace

This workspace is used to maintain and update the company's internal knowledge base, with a focus on keeping FAQ articles current with the latest policies and external regulations.

## Typical Workflow

1. Read `task_brief.md` to understand the specific policy question and which FAQ article needs an update.
2. Use the standard mock API skills available in this environment:
   - **knowledge_base**: search for internal articles, retrieve full article content, and update article bodies.
   - **web_content**: fetch content from external web pages (such as government regulatory sites).
3. Research the policy using both internal knowledge base articles and external sources as specified in the task brief.
4. Update the target FAQ article with a new, verified answer, ensuring existing sections remain untouched.

## Important Notes

- Always preserve existing sections of an FAQ article when adding new information.
- Cite relevant internal policy documents and external references when drafting the new FAQ section.
- All interactions with the knowledge base and external web content happen through the provided API endpoints; no additional tooling or command execution is required.

## Files

- `task_brief.md` – Contains the full task instructions, including the policy question, required sources, and target FAQ article ID.
