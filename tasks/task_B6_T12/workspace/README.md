# ABC Corp Q3 2027 Procurement Reconciliation

## Objective

Reconcile all purchase transactions for vendor **ABC Corp** during **Q3 2027** (July 1 – September 30, 2027) against the expected total defined in the procurement brief (`procurement_brief.md`). After completing the reconciliation, update the approval tracking task **T-4201** on the taskboard with a reconciliation summary and set its status to **Ready for Approval**.

## Expected Workflow

1. **Review the procurement brief**  
   Read `procurement_brief.md` to understand the vendor, reporting period, reconciliation criteria, expected total, and the associated taskboard task ID.

2. **Retrieve ledger transactions**  
   Use the standard mock API endpoint to fetch all purchase transactions for ABC Corp in Q3 2027:  
   `GET /ledger/transactions`

3. **Verify the total**  
   Sum the amounts of the returned transactions and confirm they equal the expected $125,000. Note any discrepancies, if found.

4. **Retrieve the taskboard task**  
   Look up task T-4201 using the standard taskboard mock API:  
   `GET /taskboard/tasks/get` with `task_id: "T-4201"`

5. **Update the task**  
   Append a reconciliation summary to the task description and set the status to **Ready for Approval**. Use:  
   `PUT /taskboard/tasks/update` with the updated fields.

## Important Notes

- All interactions with the ledger and taskboard should use the standard mock API skills/endpoints provided in the environment.
- The procurement brief (`procurement_brief.md`) should remain unchanged throughout this task.
- No new workspace files need to be created; only the taskboard task should be updated.
