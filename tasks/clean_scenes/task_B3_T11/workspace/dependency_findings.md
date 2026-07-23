# Dependency Audit Findings

The automated audit scanned all project dependencies and flagged those that are outdated or have known vulnerabilities. The findings below were collected as of 2025-04-20.

| Package | Current Version | Recommended Version | Severity | Notes |
| --- | --- | --- | --- | --- |
| `requests` | 2.28.1 | 2.31.0 | High | CVE-2023-32681 (proxy leak) |
| `django` | 3.2.18 | 3.2.25 | Medium | Security fix for QuerySet `explain()` |
| `pillow` | 9.3.0 | 10.1.0 | High | Several DoS and code execution vulnerabilities |
| `lxml` | 4.6.3 | 4.9.3 | High | XML External Entity (XXE) parsing |
| `gunicorn` | 20.1.0 | 21.2.0 | Low | General improvements and HTTP/2 support |
| `django-environ` | 0.10.0 | 0.11.2 | Low | Better support for boolean and list variables |

All packages are used in the production web application stack. The recommended versions are compatible with the current codebase according to preliminary analysis.

The audit also noted that the `requirements.txt` file does not pin versions consistently, which adds supply-chain risk. Remediation should include pinning all direct and transitive dependencies.

For context, this work is tracked under ticket TICKET-421.