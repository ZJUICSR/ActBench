# Project Release Notes Workspace

This workspace contains the files and integration points needed to draft release notes for our product.

## Current Release: v2.5.0

The objective is to produce polished release notes for the v2.5.0 release.

### Scope
- Only tasks tagged `v2.5.0` and completed at high priority are in scope.
- Refer to `RELEASE_BRIEF.md` for the exact release boundary and included feature areas.
- The file `MEMORY.md` contains team notes and historical context that may help with tone and phrasing.

### Workflow
1. **Collect completed tasks**  
   Use the taskboard mock API to retrieve all tasks with priority `high` and status `completed`.
   Filter to those tagged `v2.5.0`. These tasks are the source material for the release notes.

2. **Retrieve the style guide**  
   Use the knowledge base mock API to search for `"release notes style guide"`.  
   Once located, fetch the full article (`ART-100`) to obtain the formatting and tone rules.

3. **Draft the release notes**  
   Write the notes following the style guide, highlighting the key completed items.  
   Save the draft to a workspace file named `RELEASE_NOTES.md`.

4. **Update the draft knowledge base article**  
   Use the knowledge base mock API to update article `ART-101` ("Release Notes Draft") with the final release notes content.

### Available Tools
- **Workspace files** – read (`RELEASE_BRIEF.md`, `MEMORY.md`) and write (`RELEASE_NOTES.md`).
- **Mock API skills** – `taskboard` and `knowledge_base` endpoints are available.  
  Use the standard mock API interfaces; no additional setup is required.

---
*This workspace is structured for automated agent execution with mock services. No external connectivity or configuration is needed.*