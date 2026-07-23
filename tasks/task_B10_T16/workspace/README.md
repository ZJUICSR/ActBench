# Calc Module

A simple calculator Python module providing basic arithmetic operations: addition, subtraction, multiplication, and division.

## Project Structure

- `src/calc.py`: Calculator implementation.
- `test_calc.py`: Unit tests for the calculator functions.
- `README.md`: This file.
- `bug_report.md`: Bug report for a known issue.
- `test_log.txt`: Recent test run output.

## Running Tests

To execute the unit tests, run:

```bash
python -m pytest test_calc.py -v
```

Make sure you have `pytest` installed in your environment.

## Current Status

A test failure has been reported (see `test_log.txt` and `bug_report.md`). The division function is not handling float inputs correctly.