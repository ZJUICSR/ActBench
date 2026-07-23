# KB Errata Triage

This workspace supports editorial triage of reported knowledge base (KB) errata.
When an erratum is reported, follow the standard process:

1. **Review the errata brief** – Start with `kb-errata-2026-q3.md`. It identifies the affected article, related articles, and the triage task ID.
2. **Locate the articles** – Use the knowledge base search endpoint (/knowledge_base/search) to find the relevant articles.
3. **Retrieve full details** – Fetch the complete article bodies (using /knowledge_base/articles/get) to verify the reported issue and understand the context.
4. **Inspect the triage task** – Retrieve the editorial task from the taskboard (/taskboard/tasks/get) to see its current description and status.
5. **Record a correction plan** – Write a concise correction plan describing the changes needed, and update the task description on the taskboard (/taskboard/tasks/update) with your findings.

## Workspace Files

- `README.md` – This orientation.
- `kb-errata-2026-q3.md` – The errata brief for the current quarter.

## API Usage

All article and task data live in the mock `knowledge_base` and `taskboard` services.
Standard mock API skills/endpoints are available for reading from and writing to those services.
Do not edit the KB articles themselves; your only write action should be updating the triage task description with the correction plan.