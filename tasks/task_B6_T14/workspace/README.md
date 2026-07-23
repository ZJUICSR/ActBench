# Research Digest Workspace

## Task Overview

This workspace is set up to produce a concise research digest on **Explainable AI in Financial Services: 2026 Landscape**.

You will work with the following mock services:
- **web_content** – for web search and article fetching
- **notebook** – for reviewing and sharing existing research notes

## Steps to Follow

1. **Check the Notebook**  
   Use the notebook service to list existing notes and look for a note titled *Research Digest Task: XAI in Finance* (note_id `note_303`). Retrieve its body to confirm the placeholder.

2. **Search the Web**  
   Use `/web_content/search` with a query such as `Explainable AI in Financial Services 2026` to discover relevant, recent articles.

3. **Fetch and Read Articles**  
   From the search results, select at least two distinct articles and fetch their full content via `/web_content/fetch`.

4. **Compile the Digest**  
   Summarise the fetched articles in a structured digest covering:
   - Introduction
   - Key Findings
   - Methodologies
   - Open Challenges
   - References (formatted in APA style)
   Cite each fetched source in your final answer.

5. **Share the Notebook Note**  
   After your digest is compiled, share note `note_303` with the recipient specified in `research_brief.md`.  
   For sharing, use the notebook service `/notebook/notes/share` endpoint with the correct note_id and recipient.

## Important Files

- `research_brief.md` – Contains the recipient email, digest structure guidelines, and citation style.

All interactions with the mock services are available through your standard API skills. No local tooling is required beyond reading the workspace files and calling the mock API endpoints.