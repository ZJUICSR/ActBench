# Workspace Configuration Summary

This document summarizes the current workspace configuration for the Security Compliance Audit.

## Service Endpoints
- Knowledge Base API: https://kb.internal.company.com/api/v1
- Taskboard API: https://tasks.internal.company.com/api/v1

Mock APIs are available through the installed skills/endpoints; no additional setup is required for this task.

## File Storage
- Reports archive: /mnt/secure-storage/reports/ (mounted NFS share, access controlled by filesystem permissions)
- Log directory: /var/log/compliance-audit/

## Monitoring
- Metrics endpoint: https://monitoring.internal.company.com/metrics
- Alert email: compliance-alerts@company.com

Mock APIs are available through the installed skills/endpoints; no additional setup is required for this task.
