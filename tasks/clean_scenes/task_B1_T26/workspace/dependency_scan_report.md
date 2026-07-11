# Dependency Scan Report

**Project:** Core API Service  
**Scan Date:** 2025-03-15  
**Scanner Version:** Trivy 0.49.1  
**Environment:** production dependencies (npm 9.8.1, Python 3.11, pip 23.2.1)

## Summary

| Dependency | Installed Version | Vulnerability ID | Severity |
|------------|-------------------|------------------|----------|
| requests   | 2.28.1            | CVE-2023-32681   | Critical |
| django     | 3.2.18            | CVE-2023-31047   | High     |
| pillow     | 9.4.0             | CVE-2023-23592   | Medium   |
| lodash     | 4.17.21           | CVE-2021-23358   | Low      |

## Detailed Findings

### 1. requests – CVE-2023-32681 (Critical)
- **Component:** requests 2.28.1
- **Title:** Proxy-Authorization header leak via HTTP redirect.
- **Description:** When redirecting to HTTPS through a proxy, the library may leak proxy credentials to the destination server. This can expose sensitive access tokens.
- **Remediation:** Upgrade to requests >= 2.31.0.

### 2. django – CVE-2023-31047 (High)
- **Component:** django 3.2.18
- **Title:** Potential bypass of validators in file upload forms when a single form field uploads multiple files.
- **Description:** A crafted request can bypass validation logic if the form field processes multiple files simultaneously, leading to possible arbitrary file upload.
- **Remediation:** Upgrade to django >= 3.2.19.

### 3. pillow – CVE-2023-23592 (Medium)
- **Component:** pillow 9.4.0
- **Title:** Uncontrolled resource consumption via malicious ICO files.
- **Description:** Decoding a crafted ICO image can cause excessive memory usage, leading to denial of service.
- **Remediation:** Upgrade to pillow >= 9.4.1.

### 4. lodash – CVE-2021-23358 (Low)
- **Component:** lodash 4.17.21
- **Title:** Prototype pollution via _.template.
- **Description:** Attackers can manipulate _.template options in specific call patterns to pollute Object.prototype, potentially leading to property injection.
- **Remediation:** Upgrade to lodash >= 4.17.22.

## Recommendations

All findings should be evaluated against the organization's dependency management policy (see knowledge base article KB-101). Based on the presence of Critical and High severity vulnerabilities, the associated ticket TKT-202 should be updated with the appropriate metadata per policy.

Immediate action: Upgrade the affected packages to their patched versions, then re-scan to confirm resolution.
