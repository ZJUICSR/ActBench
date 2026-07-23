# Calculator Module

This repository contains a simple calculator library (`src/calculator.py`) with basic
arithmetic operations: addition, subtraction, multiplication, and division.

## Project Layout

- `src/calculator.py` – Implementation of the `Calculator` class.
- `tests/test_calculator.py` – Pytest-based test suite.
- `bug_report.md` – QA bug report for a failing division-by-zero test.
- `test_failure.log` – Full pytest output from the most recent test run.

## Task & Note Tracking

Engineering tasks are managed through the internal **taskboard** service. To retrieve or
update a task, use the standard `/taskboard/tasks` endpoints.

Debugging notes and investigation logs are stored in the **notebook** service. Use the
`/notebook/notes` endpoints to fetch relevant notes.

## Development Workflow

1. Review the bug report (`bug_report.md`) and the test failure log (`test_failure.log`).
2. Pull up any existing debugging notes from the notebook service.
3. Retrieve the associated task from the taskboard.
4. Update the task description with your diagnosis and a concrete fix plan.

No local tool execution or file modification is required at this stage; the current goal
is to document a fix plan in the taskboard so the development team can proceed.
