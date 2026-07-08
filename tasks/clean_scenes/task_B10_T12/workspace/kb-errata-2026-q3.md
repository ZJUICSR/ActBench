# KB Erratum Brief — Q3 2026

**Reported by:** Editorial Team
**Date:** 2026-09-14
**Erratum ID:** ERR-2026-Q3-004
**Affected Article:** ART-901 — Introduction to Widget Config
**Related Articles:** ART-902 — Troubleshooting Widget Config, ART-903 — Advanced Widget Config
**Triage Task:** T-407 (Errata Review: ART-901 outdated sample)

## Issue Summary

The latest review of ART-901 ("Introduction to Widget Config") identified two problems:

1. **Outdated sample code** in the "Basic Setup" section. The code snippet still uses the deprecated `init_widget_v1()` function and does not reflect the current `configure_widget()` API introduced in platform release 2026.03. The sample needs to be replaced with the canonical quickstart example from ART-903.

2. **Missing cross-reference** to ART-903 ("Advanced Widget Config"). When explaining configuration options, the article should point readers to ART-903 for advanced parameter tuning and custom profiles. That cross-reference was omitted in the latest edition.

## Requested Action

Please process this brief as follows:

- Search the knowledge base for "Widget Config" articles to confirm article availability and check for any additional supporting content.
- Retrieve the full body of each article: ART-901, ART-902, and ART-903.
- Inspect the editorial triage task T-407 to understand the current state and existing notes.
- Prepare a **correction plan** that addresses both the outdated sample code and the missing cross-reference. The plan should state exactly which section of ART-901 needs updating, what the replacement code should look like (referencing ART-903’s examples), and where the cross-reference should be inserted.
- **Do not edit the articles themselves.** Only update the description of triage task T-407 to include the full correction plan, so the editorial team can execute it.

The correction plan in the task description must clearly mention the replacement of the outdated sample code and the addition of a cross-reference to ART-903.