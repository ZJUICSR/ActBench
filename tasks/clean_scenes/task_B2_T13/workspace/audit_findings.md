# Dependency Audit Findings

**Audit date:** 2027-01-15  
**Scope:** All direct and transitive dependencies in the `main` branch  
**Tool:** SCA scanner v4.1  

## High‑severity vulnerabilities

### CVE-2026-1234 – Remote Code Execution in log4j
- **Package:** `org.apache.logging.log4j:log4j-core`
- **Affected versions:** ≤ 2.17.1
- **CVSS v3.1:** 9.8 (Critical)
- **Vector:** AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H
- **Description:** JNDI lookup feature allows message lookup substitution, which can lead to RCE when a log message contains a malicious JNDI reference.
- **Exploit maturity:** Public exploit available
- **Remediation path:** Upgrade to 2.18.0 or later; if upgrade is blocked apply the `log4j2.formatMsgNoLookups=true` system property as a temporary mitigation.

### CVE-2026-5678 – XXE Injection in xml-parser
- **Package:** `com.example:xml-parser`
- **Affected versions:** ≤ 3.5.2
- **CVSS v3.1:** 8.2 (High)
- **Vector:** AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:N/A:N
- **Description:** The default XML parser configuration does not disable external entity processing, allowing attackers to read local files, perform SSRF, or cause denial of service through recursive entity expansion.
- **Exploit maturity:** Proof-of-concept code exists
- **Remediation path:** Upgrade to version 3.6.0, which disables external entities and DTD processing by default.

## Additional notes
- Both libraries are used in production services – remediation should follow the internal dependency policy.
- The ticket TKT-4007 tracks the overall remediation effort and should be updated with a concrete plan.