# Dependency Audit Report

**Date:** 2025-12-10  
**Audit Scope:** Backend services: user-service, payment-gateway, notification-worker

## Executive Summary
This report summarizes the results of a recent dependency vulnerability scan against our production services. Several critical and high-severity vulnerabilities were identified, requiring prompt remediation according to our internal policy (see KB-101 for full criteria).

## Findings

| Package | Current Version | Vulnerable Version Range | CVE | Severity | Description | Remediation Suggestion |
|---------|----------------|--------------------------|-----|----------|-------------|------------------------|
| lodash | 4.17.15 | <4.17.21 | CVE-2020-8203 | High | Prototype pollution in lodash.merge / lodash.defaultsDeep. | Upgrade to lodash 4.17.21 or later. |
| express | 4.16.4 | <4.17.3 | CVE-2022-24999 | High | Directory traversal via unexpected characters in req.path. | Upgrade to express 4.17.3 or later. |
| jsonwebtoken | 8.5.1 | <9.0.0 | CVE-2022-23529 | High | Improper input validation allows JWT signature bypass with arbitrary public key. | Upgrade to jsonwebtoken 9.0.0 or later. |
| axios | 0.21.1 | <0.21.2 | CVE-2021-3749 | High | Regular expression denial of service (ReDoS) in axios. | Upgrade to axios 0.21.2 or later. |
| node-fetch | 2.6.1 | <2.6.7 | CVE-2022-0235 | Medium | Server-side request forgery (SSRF) via improper handling of URLs. | Upgrade to node-fetch 2.6.7 or later. |

## Detailed Descriptions

### CVE-2020-8203 (lodash)
The vulnerable functions are used in user-service for data merging operations. An attacker could potentially modify object prototypes leading to unexpected behavior and data manipulation.

### CVE-2022-24999 (express)
Applies to our API gateway built on express. The traversal could allow an attacker to serve files outside the intended static directory, potentially exposing sensitive configuration.

### CVE-2022-23529 (jsonwebtoken)
Our authentication service uses this library. The vulnerability could allow token forgery under certain conditions, posing a significant security risk to authentication integrity.

### CVE-2021-3749 (axios)
Used in payment-gateway to communicate with external payment processors. While ReDoS is less severe than remote code execution, it could be used to degrade service availability under high load scenarios.

### CVE-2022-0235 (node-fetch)
Used in notification-worker to pull data from external services. SSRF could allow an attacker to make requests to internal network resources, potentially leading to further compromise.

## Next Steps
- Review the internal dependency remediation policy (KB-101) for mandatory SLAs and risk acceptance criteria.
- Produce a concise remediation plan addressing the findings, prioritizing critical and high vulnerabilities.
- Update the tracked ticket TK-2024 with the plan and set priority and tags accordingly.
