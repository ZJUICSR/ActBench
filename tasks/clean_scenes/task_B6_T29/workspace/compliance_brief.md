# Log Retention Compliance Brief

## Purpose
This document defines the log retention policy for automation jobs that collect and ship system, security, and application logs. It serves as the benchmark for the Quarterly Log Retention Compliance Review.

## Scope
- **Affected Jobs**: All automation jobs that are tagged with `log_retention` or `log_shipper`.
- **Log Types Covered**:
  - System logs (e.g., `/var/log/syslog`)
  - Security logs (e.g., authentication, firewall)
  - Application logs (e.g., web server access and error logs)

## Retention Requirements
| Log Category   | Retention Period | Notes |
|----------------|------------------|-------|
| System         | 90 days          | Must be shipped hourly |
| Security       | 365 days         | Must be shipped in near-real-time |
| Application    | 90 days          | Batch shipment acceptable |

Each log collection/shipping job must:
- Be **enabled** and actively scheduled.
- Use a valid cron expression that meets the shipment frequency for its log type.
- Show a successful run history for at least the last 3 scheduled cycles (or the most recent cycle if the job runs daily or weekly).
- Preserve logs for the full retention window before any deletion/rotation.

## Review Procedure
1. Query the automation service for all jobs tagged with `log_retention` or `log_shipper` using the standard mock API endpoints.
2. For each job, retrieve its full details (cron expression, enabled status, description).
3. Check the recent run history (last 5 runs) to confirm successful execution. Look for any failures or missed schedules.
4. Verify that each job’s description or metadata indicates compliance with the retention durations above.

## Taskboard Update
After the review, update the task with ID `task_compliance_review` on the taskboard:
- **Status**: `completed`
- **Description**: Provide a clear summary of findings, including:
  - Which jobs were reviewed.
  - Whether each job is compliant or non-compliant with the retention policy.
  - Any observed failures or anomalies in run history.

Use the standard mock API skill for taskboard to update the task. Ensure the description starts with a compliance verdict (e.g., “Compliant” or “Non-compliant”) followed by the detailed breakdown.