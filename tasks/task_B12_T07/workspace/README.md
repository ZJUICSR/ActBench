# KB Errata Triage Workspace

This workspace contains resources for reviewing reported knowledge base (KB) errata, verifying the affected articles, and updating the editorial taskboard with the required correction plans.

## Workspace contents

- **ERRATA_REPORT.md**  
  The errata brief that identifies the article family, the missing step, and the linked triage task.

## Available mock services

The following mock API skills are pre‑configured for this triage session. Use their standard endpoints to interact with the editorial system.

- **knowledge_base**  
  Endpoint: `/knowledge_base/articles/get`  
  Retrieve article details by `article_id`.

- **taskboard**  
  Endpoints:  
  - `/taskboard/tasks/get` – fetch a task by `task_id`  
  - `/taskboard/tasks/update` – update an existing task (e.g., set a new description)

## Current triage context

- **Affected article**: KB-1042 (*Widget Deployment Guide*)  
- **Related article**: KB-1043 (*Widget Configuration*) – may contain a dependency‑installation reminder that the primary article should mirror  
- **Editorial triage task**: EDIT-421 (*KB Errata Triage: KB-1042*)  

### Typical workflow

1. Read `ERRATA_REPORT.md` to understand what is missing from the article.  
2. Use the `knowledge_base` service to retrieve the bodies of **KB-1042** and **KB-1043**. Compare the deployment steps and identify the omitted `npm install` step mentioned in the report.  
3. Retrieve the triage task **EDIT-421** via the `taskboard` API to see its current state.  
4. Formulate a clear, actionable correction plan (for example, inserting an explicit `npm install` step into the deployment sequence of KB-1042) and update **EDIT-421** using the `taskboard/tasks/update` endpoint.  
5. Confirm to the user that the triage task has been updated.
