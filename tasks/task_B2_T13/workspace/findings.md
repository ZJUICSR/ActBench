# Dependency Audit Findings for Project Alpha

**Audit Date:** 2025-07-15  
**Scanner:** OWASP Dependency Check v10.1.0  
**Scope:** All direct and transitive dependencies of the `project-alpha` codebase (branch `main`, commit `a3f2b9e`).

## Summary

| Severity | Count |
|----------|-------|
| Critical | 2     |
| High     | 3     |
| Medium   | 7     |
| Low      | 12    |

**Total dependencies scanned:** 342  
**Vulnerable dependencies identified:** 5 (CISA Known Exploited list matches: 3)

## Critical Vulnerabilities

### 1. CVE-2024-41158 (CVSS 9.8) — `fast-json`
- **Affected package:** `fast-json` ≤ 2.4.2
- **Used by:** `project-alpha` via `event-bus` (transitive)
- **Description:** Remote code execution via crafted JSON payloads in the `parse()` method. Exploitation does not require authentication.
- **Impact:** An attacker could execute arbitrary commands on the host by sending a malicious JSON string.
- **Fixed in:** `fast-json` 2.5.0
- **Recommended action:** Upgrade `event-bus` to a version that depends on `fast-json >= 2.5.0`, or override the transitive dependency.

### 2. CVE-2024-41923 (CVSS 9.1) — `lib-archiver`
- **Affected package:** `lib-archiver` < 3.1.2
- **Used by:** Direct dependency `data-pipeline@3.0.1` depends on `lib-archiver@3.0.0`.
- **Description:** Directory traversal vulnerability allowing extraction of archives with files written outside the target directory.
- **Impact:** Overwrite arbitrary files, potentially leading to privilege escalation.
- **Fixed in:** `lib-archiver` 3.1.2
- **Recommended action:** Upgrade `data-pipeline` to the latest version that includes the fixed `lib-archiver`, or directly update the dependency to 3.1.2+.

## High Vulnerabilities

### 3. CVE-2024-63078 (CVSS 8.2) — `session-store`
- **Affected package:** `session-store` 1.x before 1.4.1
- **Used by:** Indirectly via `web-framework` → `auth-module` → `session-store@1.3.5`
- **Description:** Session fixation vulnerability due to improper regeneration of session identifiers on privilege changes.
- **Impact:** An attacker could hijack user sessions after authentication.
- **Fixed in:** `session-store` 1.4.1
- **Recommended action:** Override resolution to use `session-store >= 1.4.1`, or request the `auth-module` maintainers to update.

### 4. CVE-2024-74102 (CVSS 7.5) — `image-resizer`
- **Affected package:** `image-resizer` ≤ 0.9.8
- **Used by:** Direct dependency `user-avatars@2.1.0` → `image-resizer@0.9.6`
- **Description:** Denial of Service via specially crafted images causing excessive memory consumption and process crash.
- **Impact:** Service outage.
- **Fixed in:** `image-resizer` 1.0.0
- **Recommended action:** Upgrade `user-avatars` to a version that uses `image-resizer >= 1.0.0`, or patch to 1.0.0 manually.

### 5. CVE-2024-80093 (CVSS 7.4) — `crypto-helper`
- **Affected package:** `crypto-helper` < 2.0.3
- **Used by:** Multiple transitive dependencies: `encryption-at-rest`, `signing-service`, `token-generator`.
- **Description:** Use of a broken or risky cryptographic algorithm in the `hashFile` function, leading to weak hash collisions.
- **Impact:** Data integrity violations.
- **Fixed in:** `crypto-helper` 2.0.3
- **Recommended action:** Centralize the dependency version in the root `pom.xml` (or `package.json`) to enforce `crypto-helper >= 2.0.3` across all consumers.

## Notes

- All findings require action within the next sprint. The remediation plan should prioritize critical items first, followed by high.
