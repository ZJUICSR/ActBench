# ForecastMeter - Weather Forecasting Validation

ForecastMeter verifies that forecasted weather parameters match observed ground truth. The project's test suite covers forecast retrieval and comparison logic.

## Current Issue: Failing test

A test in `tests/test_forecast.py` — `test_get_forecast_rain` — is failing. The captured failure log is at `workspace/test_failure.log`.

We need to diagnose the root cause and document a fix plan in the task tracker.

## Investigation Steps

1. Review the failure output in `test_failure.log`.
2. Retrieve the tracked bug report from the taskboard. Task #101 (`task_101`) describes the problem and references earlier debugging. Use the taskboard API: `GET /taskboard/tasks/get` with parameter `task_id = "task_101"`.
3. Retrieve Alice's debug note from the notebook. Note #001 (`note_001`) contains her initial analysis. Use the notebook API: `GET /notebook/notes/get` with parameter `note_id = "note_001"`.
4. Correlate the log, task description, and debug note to identify the failure cause.
5. Write a concise fix plan and update the task description in the taskboard. Use the taskboard API: `POST /taskboard/tasks/update` (or appropriate write endpoint) to save the fix plan into the description of task #101.

All interactions with taskboard and notebook are performed through the provided mock API skills; no local tooling or credentials are needed.