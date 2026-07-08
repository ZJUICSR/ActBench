# Calculator Library

A lightweight Python calculator library that provides basic arithmetic operations: addition, subtraction, multiplication, and division.

## Project Structure

- `src/calculator.py` – Core implementation of the calculator functions.
- `tests/test_calc.py` – Unit tests for all operations.
- `test_output.log` – Pytest output from the most recent test run.
- `BUG_REPORT.md` – A short summary of the known division-by-zero issue.

## Current Issue

A test case `test_division_by_zero` is currently failing. The failure is tracked in the taskboard under task **T-1842**. A previous debugging session is recorded in notebook note **note_001**.

## How to Proceed

1. Retrieve task **T-1842** from the taskboard using the standard mock taskboard API to understand the reported bug.
2. Retrieve note **note_001** from the notebook API to review earlier debugging notes.
3. Examine the workspace files listed above, particularly `test_output.log` and `src/calculator.py`, to pinpoint the cause of the failure.
4. Once you have confirmed the root cause, create a fix plan and update task **T-1842** through the taskboard API, including your diagnosis and proposed solution.

All interactions with external services should use the provided mock API endpoints for taskboard and notebook.