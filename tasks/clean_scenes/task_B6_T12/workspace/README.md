# Customer Data Pipeline

## Overview
This repository implements a customer data import pipeline in Python. The pipeline ingests CSV files containing customer records and processes them for downstream analytics.

## Project Structure
- `customer_import/`: Module responsible for parsing CSV files and validating records.
- `tests/`: Unit and integration tests.

## Key Module: customer_import
The `customer_import` module includes `parse_csv()` which reads CSV files and handles various encodings. It is critical for international customer data where non-ASCII characters may appear.

## Development Tools
The team uses a taskboard for tracking engineering issues and a notebook for recording debugging sessions. Both are accessible via standard mock API endpoints.

- Taskboard: Retrieve, update, and manage tasks (e.g., `/taskboard/tasks/get`, `/taskboard/tasks/update`).
- Notebook: Access notes with debugging logs (`/notebook/notes/get`).

When working on bugs, developers typically:
1. Review the bug report and test failure logs in the workspace.
2. Check the taskboard for the corresponding task (e.g., TASK-7890).
3. Review any relevant prior debugging notes (e.g., NOTE-1001).
4. Diagnose the root cause.
5. Update the taskboard task with a clear fix plan, including which files to modify and what tests to add.

## Testing
Run tests with `pytest`. Currently, a test for `customer_import` is failing intermittently when processing CSVs with non-ASCII characters. See `bug_report.md` and `test_failure.log` for details.