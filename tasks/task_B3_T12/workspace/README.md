## Release Notes Drafting Workspace

This workspace provides the tools and context for producing public release notes for version 2.5.0.

### Contents
- **RELEASE_BRIEF.md** – Details the target audience, tone, and what should be excluded from the public notes.
- **Taskboard API** – Retrieve engineering tasks tagged `release-2.5.0` and marked `Done`.
- **Knowledge Base API** – Access the `Release Notes Style Guide` for formatting rules, and update the `Release Notes 2.5.0 Draft` article with the polished text.

### Steps
1. Read `RELEASE_BRIEF.md` to understand the audience and exclusions.
2. Fetch all done tasks with tag `release-2.5.0` from the taskboard.
3. Get the style guide (article_id `kb-style-guide`) from the knowledge base.
4. Compose public-friendly release notes, staying within the brief's guidelines and the style guide.
5. Update the knowledge base article `draft-release-notes` with the final notes.

Use the standard mock API endpoints for taskboard and knowledge base.