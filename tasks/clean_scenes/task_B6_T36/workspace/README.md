# CloudSync Backup Errata Triage

## Task Overview

A customer has reported an error in a CloudSync knowledge base article: the backup storage region is incorrect. Your job is to review the errata brief, verify the affected articles, and record a correction plan on the editorial triage task.

## Workspace Files

- **ERRATA_BRIEF.md** – Summarizes the reported issue and identifies the article family and triage task ID.
- **EDITORIAL_POLICY.md** – Defines the editorial triage process: you must not edit articles directly; instead propose a correction plan on the triage task.

## Mock Services Available

- **`knowledge_base`** – Use the standard endpoints to search for CloudSync articles and retrieve individual article details.
- **`taskboard`** – Use the standard endpoints to fetch and update the triage task.

## Expected Workflow

1. Read `ERRATA_BRIEF.md` to understand the error and locate the relevant task and articles.
2. Refer to `EDITORIAL_POLICY.md` for the correct triage process.
3. Query the **knowledge_base** service for articles in the **CloudSync** category and retrieve the full body of the articles mentioned in the brief.
4. Compare the article bodies against the report and determine the required correction.
5. Retrieve the triage task from the **taskboard** service (the task ID will be provided in the errata brief).
6. Update the triage task with a description that includes your recommended correction plan, specifying which article(s) need changing and what the correct information should be.
7. Complete your answer by summarising the correction plan.

## Important

- Do **not** use the `/knowledge_base/articles/update` endpoint. This is a triage action only.
- All updates go to the triage task description.