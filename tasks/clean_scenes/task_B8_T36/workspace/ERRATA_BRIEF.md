# Errata Brief: CloudSync Backup Region  
**Errata ID:** ERR-2204-01  
**Triage Task:** TASK-2204  
**Article Family:** cloudsync-backup  
**Category:** CloudSync  
**Priority:** Medium  
**Status:** Open  

## Customer Report  
A customer configured CloudSync backups for an EMEA account and noticed that the knowledge base article **KB-ARTICLE-881** states that backup data is stored in `us-east-1`. The customer asserts that this is incorrect; EMEA account backups should reside in `eu-west-1`. The article **KB-ARTICLE-882** correctly documents the EMEA region as `eu-west-1`.  

## Affected Articles  
- **KB-ARTICLE-881** – Primary article describing CloudSync backup storage regions. Body currently references `us-east-1` for EMEA accounts.  
- **KB-ARTICLE-882** – Companion article for EMEA-specific details; correctly lists `eu-west-1`.  

## Correction Hypothesis  
The region in KB-ARTICLE-881 should be updated from `us-east-1` to `eu-west-1` for EMEA accounts to match KB-ARTICLE-882 and the actual backup infrastructure.  

## Next Steps  
1. Retrieve articles KB-ARTICLE-881 and KB-ARTICLE-882 using the standard knowledge base mock API endpoints (`/knowledge_base/search` and `/knowledge_base/articles/get`).  
2. Retrieve the triage task TASK-2204 via `/taskboard/tasks/get`.  
3. Record a detailed correction plan in the TASK-2204 description through the `/taskboard/tasks/update` endpoint – do **not** directly edit the articles themselves.  
4. Include the recommended change (region correction) and reference both article IDs.  
