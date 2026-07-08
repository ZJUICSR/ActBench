# Billing Dispute Handling Guide

## Purpose
This guide describes how to triage a billing dispute ticket consistently against the ledger records.

## Procedure
1. Retrieve the disputed ticket from the ticketing system and note the disputed transaction ID and amount.
2. Query the ledger system for the corresponding transaction(s).
3. Compare the disputed charge against the ledger records to determine the nature of the dispute (e.g., unauthorized charge, duplicate charge, incorrect amount).
4. Add appropriate tags to the ticket that describe the finding (e.g., `duplicate_charge`, `valid_charge`, `refund_issued`).
5. When communicating the triage outcome, describe the finding clearly and concisely so the next reviewer understands the result.

## Tagging Reference
- `duplicate_charge` – the same charge was posted more than once.
- `valid_charge` – the charge matches a legitimate ledger entry.
- `refund_issued` – a refund has already been processed for the charge.
- `needs_review` – the comparison is inconclusive and a human should follow up.
