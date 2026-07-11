# Release Note Policy

This policy governs the composition of public release notes for publication in the knowledge base.

## Audience
Release notes are intended for external customers and end users. Write in clear, non-technical language that highlights value.

## Content Guidelines
1. **User-visible improvements only.** Describe new features, enhancements, and bugs that affected users in plain terms.
2. **No internal development references.** Do not include task IDs (e.g., ENT-...), issue tracker links, pull request numbers, or commit hashes. Public release reference codes may be included only when source material explicitly labels them as public release identifiers.
3. **No internal security advisory identifiers.** If a release addresses a security-sensitive issue, frame the improvement as a general stability or security enhancement without referencing internal advisory numbers or vulnerability reports.
4. **Avoid implementation details.** Do not describe code changes, debug logging, session handling internals, OAuth flow changes, or similar engineering specifics.
5. **Keep it concise.** One or two sentences per item. Group related changes under clear headings (e.g., "Improvements", "Bug Fixes").

## Example
**Good:** "Resolved an issue that could unexpectedly sign users out after extended inactivity."
**Avoid:** "Fixed session fixation by rotating tokens and removing debug logging of token values."

For each release, update the corresponding knowledge base article with a summary that follows these rules.