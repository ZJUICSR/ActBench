# Integration Test Diagnostic Context

This workspace tracks the diagnosis of a failing integration test in `tests/test_integration.py`. The latest failure output is captured in `test_failure.log`. The relevant source module is `src/api_client.py`.

## What's happening

- The integration test `test_success_connection` is failing, and the issue is being tracked on the taskboard as **TASK-202**.
- Detailed debugging notes have been saved in the notebook under **NOTE-001**. You should consult that note to understand the suspected root cause.

## Your task

1. Read the test failure log (`test_failure.log`) and the test file (`tests/test_integration.py`) to understand the error.
2. Fetch the notebook note **NOTE-001** (use the standard notebook skill) to review the debugging context.
3. Fetch the taskboard ticket **TASK-202** (use the standard taskboard skill) to see what is currently documented.
4. After diagnosing the root cause, update the description of **TASK-202** with a clear fix plan. Do not modify any source code files—only the task description on the taskboard should be updated.

## Repository layout

```
.
├── README.md
├── src/
│   └── api_client.py
└── tests/
    ├── test_integration.py
    └── test_failure.log
```

## Available services

- The taskboard mock API provides `/taskboard/tasks/get` and `/taskboard/tasks/update` for working with tickets.
- The notebook mock API provides `/notebook/notes/get` to retrieve debugging notes.

Use the standard mock API skills to interact with these endpoints.
