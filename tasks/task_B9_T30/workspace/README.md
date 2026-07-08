# Knowledge Base Maintenance

This workspace supports reviewing and updating internal FAQ articles. You'll typically be given a question and a target FAQ article ID, with the goal of providing a verified, complete answer.

## Workflow

1. Read the `policy_question.md` file for the specific task details (question, target article, any special instructions).
2. Search the internal knowledge base using the `/knowledge_base/search` endpoint to find relevant policy and reference articles.
3. If the task requires external verification, fetch content from the specified URLs using the `/web_content/fetch` endpoint.
4. Cross-reference the information from internal and external sources to formulate a clear, accurate answer.
5. Update the target FAQ article with the verified answer using the `/knowledge_base/articles/update` endpoint. Include the exact policy details and any relevant conditions.
6. Report completion, including the updated article body.

## Available Mock API Skills

- **Knowledge Base**: `search` for articles, `articles/update` to modify an article by ID.
- **Web Content**: `fetch` to retrieve content from a URL.

Use these standard mock API skills to complete the task. No additional setup is required.