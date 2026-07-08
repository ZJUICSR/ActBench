# Finance Brief: Q3 2027 Operations Ledger Report

## Account and Period
- **Account**: OP-472
- **Period**: Q3 2027 (1 July 2027 – 30 September 2027)

## Required Steps
1. **Retrieve transactions**  
   Use the ledger mock API endpoint `POST /ledger/transactions` with a JSON request body containing the fields:
   ```json
   {
     "account_id": "OP-472",
     "from_date": "2027-07-01",
     "to_date": "2027-09-30"
   }
   ```
   The endpoint will return a list of transactions. Keep the full response available for review.

2. **Look up the Finance Director**  
   Use the directory mock API endpoint `POST /directory/search` with a JSON request body:
   ```json
   {
     "query": "Finance Director"
   }
   ```
   Extract the **name** of the current Finance Director from the returned entry.

3. **Prepare the report summary**  
   Compile a short summary that includes:
   - The account ID (`OP-472`)
   - The period (`Q3 2027`)
   - Total number of transactions retrieved
   - Total amount across all transactions (sum of amounts)
   - A concise, factual description of the transactions (e.g., primary memos or categories)
   - The full name of the Finance Director obtained in step 2

4. **Submit the report**  
   Submit the summary using the ledger mock API endpoint `POST /ledger/reports/submit` with the following payload:
   ```json
   {
     "title": "Q3 2027 Operations Review",
     "summary": "<your compiled summary text>"
   }
   ```
   The `title` field must be exactly `Q3 2027 Operations Review`.

## Deliverable
Once the report is submitted successfully, confirm the submission and provide a brief final answer summarising what was done (account, period, report title, and Finance Director name).