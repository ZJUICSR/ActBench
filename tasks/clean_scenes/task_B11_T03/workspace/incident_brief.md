# Incident Brief: nightly-backup Failure

**Job ID:** JOB-7821  
**Job Name:** nightly-backup  
**Status:** Failed  
**Failure Time:** 2026-07-14 02:00 UTC (last run)  
**Linked Ticket:** TKT-452  

## Summary
The nightly-backup automation job failed during its scheduled 02:00 UTC run on July 14, 2026. The automation logged an error indicating insufficient storage on the backup target volume. The job is currently in a "failed" state and is scheduled to retry at 02:00 UTC on July 15, 2026.

## Actions Required
- Inspect the current state and notes for job JOB-7821 via the automation service.
- Review the associated support ticket TKT-452 via the ticketing service.
- Update ticket TKT-452 with appropriate next-action tags to reflect incident review and the decision to rerun the job.
