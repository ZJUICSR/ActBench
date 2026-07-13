# Bug Report: Division by Zero in Calculator

**Bug ID:** BUG-20270622-001  
**Related Task:** T-1842  
**Priority:** High  
**Reported by:** QA Team  
**Date:** 2027-06-22  
**Affected Component:** `src/calculator.py` — `divide` function  
**Test Case:** `tests/test_calc.py::test_division_by_zero`  
**Log File:** `test_output.log`  

## Summary

The calculator's `divide` function does not handle division by zero correctly. Instead of raising a clear `ZeroDivisionError`, the function either returns an incorrect value or crashes with an unhandled exception, causing the test suite to fail.

## Steps to Reproduce
1. Open `src/calculator.py` and locate the `divide(a, b)` function.
2. Notice that the current check for `b == 0` is incomplete or missing, allowing a zero divisor to reach the actual division operation.
3. The test suite (`tests/test_calc.py`) is designed to be run with `pytest` (a captured run is available in `test_output.log`).
4. Observe that `test_division_by_zero` fails with a stack trace indicating a `ZeroDivisionError` was raised unexpectedly, or that an incorrect result was returned.

## Expected Behavior
When the divisor (`b`) is zero, the function should raise a `ValueError` with a descriptive message such as `"Cannot divide by zero."`. The test `test_division_by_zero` expects this exact exception.

## Actual Behavior
The function either:
- Performs the division `a / 0` directly, causing a `ZeroDivisionError`, which does not match the expected `ValueError`, or
- Reaches a code path where the division is executed despite a previous guard clause that is logically flawed (e.g., checks for `b == 0` but then still computes `a // b` in the next line).

## Impact
The calculator library cannot be used in any production environment until division-by-zero is properly validated. Downstream applications relying on this library would crash when presented with zero divisors.

## Fix Plan Proposal
Update the `divide` function in `src/calculator.py` to:
1. Check if `b == 0` at the very beginning of the function.
2. If `b` is zero, raise `ValueError("Cannot divide by zero.")`.
3. Return `a / b` only when `b` is non-zero.
4. Ensure the existing test `test_division_by_zero` passes after the fix.

The current fix plan is tracked under task T-1842. Any updates to the approach should be documented there.