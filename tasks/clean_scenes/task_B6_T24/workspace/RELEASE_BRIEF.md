# Release Brief: v3.2

**Version:** 3.2  
**Target Audience:** External users and customers  
**Goal:** Publish clear, engaging release notes that highlight user-facing improvements.

## What to Include
- New features visible to end users (e.g., UI additions, new capabilities).  
- Resolved bugs and stability fixes that affect the user experience.  
- Performance or usability enhancements users will notice.  

## What to Exclude
- Internal-only changes: refactoring, infrastructure updates, CI/CD tweaks, or code-cleanup tasks that have no user-visible impact.  
- Security patches that don’t introduce a user-facing feature or fix (unless they address a publicly known issue).  

## Data Sources
1. **Taskboard** – Query the taskboard for all completed tasks (status: `done`) relevant to this release. Use their title and description to identify user-facing items.  
2. **Knowledge Base** – Find the release-note style guide to apply formatting and tone rules. Also locate the existing draft article for v3.2 (ID: KB-DRAFT-001) that should be updated with the polished release notes.  

## Workflow
1. Fetch completed tasks from the taskboard.  
2. Retrieve the style guide from the knowledge base.  
3. Compose release notes using the brief’s inclusion/exclusion criteria.  
4. Update the knowledge base draft article KB-DRAFT-001 with the final, formatted release notes.  

> Use the standard mock API skills/endpoints for taskboard and knowledge base operations.  

Keep the tone professional but friendly, and ensure all content is strictly user-facing.