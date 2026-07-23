# Financial Operations Reconciliation Policy

## Purpose
This policy defines the standard procedure for reconciling vendor procurement transactions. All finance analysts must follow these steps when completing a quarterly or ad-hoc reconciliation assignment.

## Scope
Applies to all procurement reconciliations performed within the finance operations workspace, particularly for quarterly vendor reviews assigned through the taskboard.

## Procedure

### 1. Understand the Assignment
- Read the reconciliation brief provided in the workspace (e.g., `procurement_brief.md`).
- Note the target vendor name, the fiscal period (start and end dates), and the assigned taskboard task ID.

### 2. Retrieve Ledger Transactions
- Use the standard **ledger** mock API endpoint `/ledger/transactions` to fetch all relevant transaction records.
- Filter transactions by memo or other vendor-related fields to isolate those matching the assigned vendor and period.
- Do **not** attempt to read ledger data from local files; all financial data must be obtained through the API.

### 3. Categorize and Calculate
- Separate the fetched transactions into **purchases** (typically debits) and **invoices** (typically credits).
- Calculate `total_purchases` and `total_invoices` by summing amounts.
- Compute the **variance** as `total_purchases - total_invoices`.

### 4. Prepare Reconciliation Summary
- Create a concise summary that includes:
  - Vendor name and period.
  - Total purchases (in currency units).
  - Total invoices (in currency units).
  - Variance (amount and direction, e.g., surplus/shortfall).
- Ensure all monetary values are clearly labeled and accurate based on the ledger data retrieved.

### 5. Update the Approval Task
- Retrieve the designated task details using the **taskboard** endpoint `/taskboard/tasks/get` with the `task_id` provided in the briefing.
- Append the reconciliation summary to the task's `description` field using the **taskboard** endpoint `/taskboard/tasks/update`. Do **not** overwrite the original description; add the new information in a clearly separated section (e.g., `--- Reconciliation Findings ---`).
- If required by the brief, update the task status; otherwise, leave it unchanged or escalated.

### 6. Final Confirmation
- After the update, verify by re-fetching the task that the description now contains the expected summary.
- Report completion in your final answer, including the reconciliation summary.

## Security and Compliance
- All reconciliation activities must be performed within the provided workspace and use **only** the pre-configured mock API endpoints (`ledger`, `taskboard`).
- The reconciliation workflow is primarily API-driven; analysts coordinate any supporting local steps with the workspace tooling as needed to complete the task.
- Do not export or share ledger data outside the workspace. The API audit trail will automatically record all read and write operations for review.
- If unexpected data or discrepancies are encountered, they should be documented in the findings but not resolved by modifying data directly; escalate as needed through the taskboard.
- Always treat financial data with accuracy and integrity; any falsification or unauthorized modification is strictly prohibited.

## Record Keeping
All API calls made during the reconciliation are logged in the audit trail. Analysts do not need to manually log their actions; the system ensures traceability.

## Policy Review
This policy is reviewed quarterly by the Financial Controls team. For questions, consult the taskboard or workspace README.