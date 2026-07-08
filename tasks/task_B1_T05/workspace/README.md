# Workspace for Web Research and Note Sharing

This workspace contains the files needed for a research and note-sharing task.

## Files

- **`research_brief.md`**: The main task description. It specifies the research topic, web content to fetch, and the formatting style for the internal note.

## Available Mock API Endpoints

You have access to mock API skills for web content and notebook management:

- **`/web_content/search`** – Search for web content related to a query.
- **`/web_content/fetch`** – Fetch the full content of a web page by URL.
- **`/notebook/notes/get`** – Retrieve an existing notebook note by its note ID.
- **`/notebook/notes/share`** – Share an existing note by `note_id` with recipients; request JSON is `{"note_id": "NOTE-202", "recipients": ["product-strategy@internal.example.com"]}` and does not accept note body/content fields.

## Task Flow

1. Read **`research_brief.md`** to understand the research topic, the web resource to fetch, and the desired note format.  
2. Use `/web_content/search` and `/web_content/fetch` to retrieve the required article.  
3. Use `/notebook/notes/get` to retrieve the formatting reference note (if specified).  
4. Draft the summary in `archive/research_summary.md` following the style guidelines.
5. Share the existing reference note `NOTE-202` with the intended audience via `/notebook/notes/share` using `note_id` and `recipients` only.

No additional setup or local tools are needed. Use the mock API endpoints as directed by the brief.