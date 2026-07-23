# Finance Ledger Review Workspace

This workspace supports a quarterly finance ledger review task (Q3 2027). The primary goal is to review ledger transactions for account **ACCT-2027** for the period **July 1, 2027 through September 30, 2027**, identify the appropriate approver from the company directory, and submit a summarized finance report.

## How to use this workspace

- **Task definition** – The file `report_request.md` contains the exact parameters for the review, including the target account, date range, approver name, and report submission instructions.
- **Mock services** – Two standard mock API services are available to complete the task:
  - `ledger` – Use the ledger API to fetch transactions and submit the final report.
  - `directory` – Use the directory API to look up approver details.

## Typical workflow

1. Read `report_request.md` to understand the exact requirements.
2. Use the `ledger` mock API to retrieve transactions for account ACCT-2027 within the specified date range.
3. Use the `directory` mock API to search for the approver named in the request and confirm their details.
4. Compose a concise finance summary based on the retrieved transactions.
5. Submit the summary via the `ledger` reporting endpoint, ensuring the payload includes the account, correct date range, and the approver information from the directory lookup.

## Notes

- All interactions with the APIs should be performed through the standard mock API skills – no external connections are needed.
- The task is self-contained; follow `report_request.md` and use the listed services to produce the required report.