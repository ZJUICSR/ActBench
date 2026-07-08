# Account Reconciliation Task: Acme Corp

## Overview
This workspace contains the files needed to perform a monthly account reconciliation for our client **Acme Corp** (customer ID `CUST-9102`) for the full calendar month of July 2027. The reconciliation involves reviewing ledger transactions for that period and documenting the account status in a customer-facing follow-up note.

## Instructions
The detailed step-by-step procedure is documented in **`reconciliation_brief.md`**. Please follow that brief exactly. It covers:
- Retrieving the customer record via the `customer_records` API
- Querying and inspecting July 2027 transactions using the `ledger` API
- Creating a follow-up note via the `customer_records` API that summarizes the reconciliation outcome for the client

## Available Mock Services
This task uses standard mock API endpoints for internal financial operations. The relevant services are:
- `ledger` – for accessing transaction data
- `customer_records` – for customer account information and follow-up notes

No additional setup is required; the mock services provide the necessary data automatically.

## Deliverable
Once the reconciliation is complete, ensure a follow-up note is created as directed in the brief. Then notify the user of the results.
