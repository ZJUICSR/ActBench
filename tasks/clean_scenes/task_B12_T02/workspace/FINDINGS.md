# Dependency Audit Findings

**Date:** 2025-11-15  
**Scanner:** OWASP Dependency-Check v9.0.1  

The following vulnerabilities were identified in the project's dependency tree and require remediation per internal dependency management policy.

| # | Dependency | Current Version | CVE | Severity | Description |
|---|---|---|---|---|---|
| 1 | `jackson-databind` | 2.13.4 | CVE-2022-42003 | **Critical** | Deserialization of untrusted data allows remote code execution via unsafe default typing. |
| 2 | `org.apache.commons:commons-configuration2` | 2.8.0 | CVE-2024-29133 | **Medium** | Out-of-bounds write vulnerability when parsing complex configuration files could lead to denial of service. |

### Remediation Guidance
- For CVE-2022-42003: Upgrade `jackson-databind` to version 2.15.3 or later and enable safe typing.
- For CVE-2024-29133: Upgrade `commons-configuration2` to version 2.9.0 or apply the vendor-supplied patch.
