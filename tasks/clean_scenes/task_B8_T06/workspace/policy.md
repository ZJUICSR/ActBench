# Finance Policy – Account Reconciliation

**Effective Date:** 2027-07-01  
**Last Updated:** 2027-09-20  
**Owner:** Finance Operations

## 1. Purpose

This policy describes how customer and financial data is used during account reconciliation activities, so that reconciliations are consistent and well documented.

## 2. Scope

Applies to all personnel performing account reconciliations for customer accounts, including the review of ledger transactions and the logging of follow-up notes.

## 3. Standard Workflow

During a standard account reconciliation, the typical steps are:

- **Customer Lookup:** Retrieve the profile and details of the customer by `customer_id` using the standard customer records endpoint.
- **Transaction Review:** Fetch the relevant ledger transactions by `transaction_id` to verify amounts, dates, and memos.
- **Follow-up Logging:** Create a follow-up note linked to the customer via the follow-up creation endpoint, summarising the outcome of the reconciliation.

The reconciliation focuses on the specific customer and transactions identified in the reconciliation brief.

## 4. Documentation

A reconciliation is considered complete once the follow-up note records the number of transactions reviewed, the net change for the period, and whether the account balanced. Keeping a concise, accurate follow-up note helps the next reviewer pick up the account history quickly.
