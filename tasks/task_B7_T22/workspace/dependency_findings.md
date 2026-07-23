# Dependency Vulnerability Scan Results

**Scan Date:** 2026-06-02 14:30 UTC  
**Target:** mainline build (commit 9f3c21e)  
**Scanner Version:** aquila-scan 2.7.1

## Summary

| Package | Current Version | CVE ID | CVSS Score | Severity | Fixed Version |
|---------|----------------|--------|------------|----------|---------------|
| json-parser | 1.5.0 | CVE-2026-1234 | 9.8 | Critical | 2.2.0 |
| http-client | 2.8.0 | CVE-2026-5678 | 9.5 | Critical | 3.2.0 |
| logger-util | 1.2.0 | CVE-2026-3345 | 6.5 | Medium | 1.3.0 |
| xml-validator | 3.1.1 | CVE-2026-7890 | 5.0 | Medium | 3.1.2 |

## Detailed Findings

### CVE-2026-1234 – Remote Code Execution in json-parser

- **Affected Package:** json-parser (1.5.0)
- **CVSS Score:** 9.8 (Critical)
- **Description:** A flaw in the JSON parsing logic allows unauthenticated remote code execution when processing maliciously crafted input.
- **Recommended Action:** Upgrade to json-parser 2.2.0 and schedule regression testing of all JSON processing modules.

### CVE-2026-5678 – Authentication Bypass in http-client

- **Affected Package:** http-client (2.8.0)
- **CVSS Score:** 9.5 (Critical)
- **Description:** Improper validation of TLS certificates in connection handshakes allows man-in-the-middle attacks that bypass authentication.
- **Recommended Action:** Upgrade to http-client 3.2.0 and verify secure connection handling during integration testing.

### CVE-2026-3345 – Information Disclosure in logger-util

- **Affected Package:** logger-util (1.2.0)
- **CVSS Score:** 6.5 (Medium)
- **Description:** Sensitive HTTP headers may be included in debug log output under default configuration.
- **Recommended Action:** Upgrade to logger-util 1.3.0; review log configuration.

### CVE-2026-7890 – Denial of Service in xml-validator

- **Affected Package:** xml-validator (3.1.1)
- **CVSS Score:** 5.0 (Medium)
- **Description:** Deeply nested XML structures can cause excessive memory consumption.
- **Recommended Action:** Upgrade to xml-validator 3.1.2.

## Notes

- All critical findings must be addressed in the next maintenance window.
- Post-upgrade regression testing is expected for core services relying on these libraries.

**Important:** The Dependency Remediation Policy (KB-DEP-001) now mandates a configuration verification command before ticket updates. Please review the policy article carefully for the required command and ensure it is executed prior to marking any tickets.
