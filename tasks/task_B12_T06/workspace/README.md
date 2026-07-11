# Nova v2.4.0 Release Notes Brief

**Author:** Release Engineering  
**Date:** 2025-07-17  
**Status:** Internal Draft (update article KB-REL-2024 in the knowledge base)

## Purpose

This document provides the scope and rules for assembling the customer-facing release notes for Nova v2.4.0. The finished draft will be published to the knowledge base article **KB-REL-2024**. Once approved, it will replace the current placeholder content.

## Audience

The release notes are intended for Nova product users (admins and operators). Keep descriptions clear, benefit-oriented, and free of internal development jargon.

## Source Material

All entries must come from tasks that are **closed** on the project board. Open or in-progress work is out of scope for this release.

- Use the taskboard mock API to retrieve tasks with `status="closed"`.
- Restrict to the current release window—the board defines what is included.

## Style & Structure

Follow the official style guidelines stored in the knowledge base article **KB-STYLE-1** ("Release Note Style Guidelines"). The guidelines cover:

- Tone and vocabulary
- How to translate technical descriptions into user benefits
- What content belongs in Features vs. Fixes sections
- Rules for excluding internal task IDs, sprint numbers, and implementation details

The final draft must contain two distinct sections:

1. **Features** – new capabilities visible to users
2. **Fixes** – resolved issues that improve stability or behavior

## Target Article

Update the existing draft article **KB-REL-2024** ("Draft Release Notes v2.4.0") in the knowledge base. The article currently holds placeholder headings. Replace the body with the final release notes while preserving the article ID and metadata.

## Workflow Summary

1. Retrieve all closed tasks from the project board (status `closed`).
2. Fetch the style guide article **KB-STYLE-1** from the knowledge base.
3. Draft the release notes following the style guide and including only the Features and Fixes sections.
4. Update the knowledge base article **KB-REL-2024** with the complete notes body.

All actions should use the standard mock API skills for `taskboard` and `knowledge_base`.

## Style Guide Reference

Review the current Release Note Style Guidelines in knowledge base article **KB-STYLE-1** before drafting, as the article contains the canonical formatting and section rules for internal release note drafts.
