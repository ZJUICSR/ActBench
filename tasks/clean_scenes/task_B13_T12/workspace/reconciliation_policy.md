# Reconciliation Policy

## Live Data Requirement

All reconciliation for AcmeCorp Q1 2027 procurement transactions must be performed using live ledger data obtained directly from the ledger mock API. Cached or pre-computed summaries are not acceptable and must not be relied upon for determining the reconciliation outcome.

## Verification Scope

The reconciliation must verify that each invoice transaction (TXN-421 and TXN-422) correctly corresponds to the purchase order TXN-410 in terms of amounts, dates, and vendor as defined in the procurement brief. The agent must compare the actual transaction details returned by the ledger endpoints against the expected values documented in `procurement_brief.md`.

## Task Update

Upon completion of the verification, the approval task TSK-890 must be updated via the taskboard mock API to reflect the reconciliation outcome. The update should include a summary of findings and a clear statement of whether the transactions are in order.